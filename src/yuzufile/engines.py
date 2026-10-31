"""Bounded page OCR. All MuPDF calls stay on the calling thread."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import re
import subprocess
import unicodedata

from PIL import Image, ImageDraw
from yuzufile.languages import tesseract_environment, tesseract_executable
from yuzufile.performance import Performance, performance_profile
from yuzufile.resources import page_indices, trim_cache


class ConversionError(Exception):
    pass


MAX_PIXELS = 8_000_000
OCR_DPI = 300


def page_needs_ocr(page) -> bool:
    import pymupdf
    if page.parent.xref_get_key(page.xref, 'PDFaiOCR')[1] == 'true':
        return False
    spans = [span for block in page.get_text("dict", flags=0)["blocks"]
             for line in block.get("lines", []) for span in line["spans"] if span["text"].strip()]
    if not spans:
        return bool(page.get_contents())
    if any("glyphless" in span["font"].lower() for span in spans):
        return False
    area = page.rect.width * page.rect.height
    return any((pymupdf.Rect(image["bbox"]) & page.rect).get_area() > area * 0.025
               for image in page.get_image_info())


def render_for_ocr(page, destination: Path) -> int:
    import pymupdf
    scale = min(OCR_DPI / 72, math.sqrt(MAX_PIXELS / max(1, page.rect.get_area())))
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csRGB,
                             alpha=False, annots=False)
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    del pixmap
    # Mask native text in the temporary image to avoid duplicate OCR text.
    draw = ImageDraw.Draw(image)
    for block in page.get_text("dict", flags=0)["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                box = pymupdf.Rect(span["bbox"]) & page.rect
                if box.is_empty:
                    continue
                x0, y0, x1, y1 = box
                draw.rectangle((max(0, int(x0 * scale) - 1), max(0, int(y0 * scale) - 1),
                                min(image.width, math.ceil(x1 * scale) + 1),
                                min(image.height, math.ceil(y1 * scale) + 1)), fill="white")
    dpi = max(1, round(72 * scale))
    image.save(destination, compress_level=1, dpi=(dpi, dpi))
    image.close()
    return dpi


def recognize_page(image: Path, dpi: int, languages: list[str], page_number: int) -> Path:
    """Only native Tesseract subprocesses run concurrently, never MuPDF."""
    from yuzufile import neural_text
    from yuzufile import indra_engine
    if indra_engine.available() and set(languages) <= {'eng', 'fra', 'ara'}:
        try:
            threads = max(1, min(4, int(os.environ.get('OMP_NUM_THREADS', '2'))))
            result = indra_engine.recognize(image, languages, threads)
            import json
            rows = json.loads(result.read_text(encoding='utf-8'))['rows']
            if not rows or all(row['score'] < .5 for row in rows):
                raise RuntimeError('Indra returned no reliable text; trying fallback recognition.')
            return result
        except (RuntimeError, MemoryError, OSError, ValueError, subprocess.TimeoutExpired):
            image.with_suffix('.indra-fallback.txt').write_text('Indra unavailable; used existing OCR engines.', encoding='utf-8')
    if neural_text.available() and set(languages) <= {'eng', 'fra', 'ara'}:
        try:
            return neural_text.recognize(image, languages)
        except (RuntimeError, MemoryError, subprocess.TimeoutExpired):
            image.with_suffix('.fallback.txt').write_text('RapidOCR unavailable; used bundled Tesseract.', encoding='utf-8')
    environment = tesseract_environment()
    environment["OMP_THREAD_LIMIT"] = "1"
    executable = tesseract_executable()
    for attempt in range(2):
        current, effective_dpi = image, dpi
        if attempt:
            current = image.with_name(image.stem + "-retry.png")
            with Image.open(image) as original:
                factor = min(1, 150 / dpi)
                with original.resize((max(1, round(original.width * factor)),
                                      max(1, round(original.height * factor))), Image.Resampling.LANCZOS) as resized:
                    resized.save(current, compress_level=1)
                effective_dpi = max(1, round(dpi * factor))
        base = current.with_suffix("")
        command = [executable, str(current), str(base), "-l", "+".join(languages),
                   "--dpi", str(effective_dpi), "-c", "textonly_pdf=1", "pdf"]
        try:
            result = subprocess.run(command, env=environment, capture_output=True, timeout=90,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        except subprocess.TimeoutExpired:
            if not attempt:
                continue
            raise ConversionError(f"Recognition timed out on page {page_number}, including a lower-resolution retry. Try splitting this PDF or using a clearer scan.") from None
        diagnostic = result.stderr.decode('utf-8', errors='replace') if isinstance(result.stderr, bytes) else result.stderr or ''
        if 'Failed loading language' in diagnostic or 'Error opening data file' in diagnostic:
            raise ConversionError(f'The fallback OCR engine could not load every selected language on page {page_number}. No partial-language output was accepted.')
        if result.returncode == 0 and base.with_suffix(".pdf").is_file():
            return base.with_suffix(".pdf")
        if attempt:
            raise ConversionError(f"The OCR engine could not process page {page_number} (code {result.returncode}), including a lower-resolution retry.")
    raise AssertionError("Unreachable OCR state")


def release_page_cache():
    trim_cache()


def _fresh_cache_data(data):
    """Keep logical OCR rows while mapping upright boxes to the visible sheet.

    Indra's original cache stays untouched for its upright Markdown figure crops.
    The generic cache is on the actual image-only PDF page used by Word.
    """
    data=deepcopy(data)
    data.setdefault('engine','RapidOCR 3.10')
    width,height=data['width'],data['height']
    rotation=int(data.get('rotation',0))%360
    if rotation not in (0,90,180,270):raise ConversionError('OCR returned an unsupported page orientation.')
    def box(values):
        x0,y0,x1,y1=map(float,values)
        if rotation==90:return [height-y1,x0,height-y0,x1]
        if rotation==180:return [width-x1,height-y1,width-x0,height-y0]
        if rotation==270:return [y0,width-x1,y1,width-x0]
        return [x0,y0,x1,y1]
    if rotation:
        for row in data.get('rows',[]):
            if 'box' in row:row['box']=box(row['box'])
        for block in data.get('blocks',[]):
            if 'bbox' in block:block['bbox']=box(block['bbox'])
        if rotation in (90,270):data['width'],data['height']=height,width
    data.update(rotation=0,source_rotation=rotation,logical_ocr=True,fresh_ocr=True)
    return data


def _overlay_cache(page):
    """Logical rows from this recognition result, never from the source PDF."""
    grouped={}
    for word in page.get_text('words'):
        grouped.setdefault(tuple(word[5:7]),[]).append(word)
    rows=[]
    for words in grouped.values():
        words.sort(key=lambda word:word[7])
        rows.append(dict(box=[min(w[0] for w in words),min(w[1] for w in words),
                              max(w[2] for w in words),max(w[3] for w in words)],
                         text=' '.join(w[4] for w in words),score=1.,
                         score_source='recognized-overlay-text-presence'))
    return dict(width=page.rect.width,height=page.rect.height,rotation=0,rows=rows,
                blocks=[],markdown='\n\n'.join(row['text'] for row in rows),engine='Tesseract 5')


def _source_figure_boxes(page):
    """Keep image geometry only; crops must come from the cleaned visible page."""
    import pymupdf
    boxes=[];area=page.rect.get_area()
    try:
        masks={image[1] for image in page.get_images(full=True) if image[1]}
        for info in page.get_image_info(xrefs=True):
            if info.get('xref') in masks:continue
            box=(pymupdf.Rect(info['bbox'])*page.rotation_matrix)&page.rect
            if box.is_empty or box.width<6 or box.height<6 or box.get_area()>=area*.7:continue
            if any((box&pymupdf.Rect(old)).get_area()>=min(box.get_area(),pymupdf.Rect(old).get_area())*.97 for old in boxes):continue
            boxes.append(tuple(box))
    except (RuntimeError,ValueError,TypeError):return []
    # Tiled scans/large slide decks must not generate thousands of tiny assets.
    return [list(box) for box in sorted(boxes,key=lambda value:pymupdf.Rect(value).get_area(),reverse=True)[:64]]


def _fresh_figure_markdown(page,number,destination,text):
    """Recover missed embedded figures using clean pixels and fresh OCR boxes."""
    import pymupdf
    destination=Path(destination)
    cache=destination.parent/'scratch'/f'fresh-ocr-page-{number}.json'
    if not cache.is_file():return text
    try:data=json.loads(cache.read_text(encoding='utf-8'))
    except (OSError,ValueError):return text
    if not data.get('fresh_ocr'):return text
    sx,sy=page.rect.width/max(1,data['width']),page.rect.height/max(1,data['height'])
    def physical(values):
        x0,y0,x1,y1=values
        return pymupdf.Rect(x0*sx,y0*sy,x1*sx,y1*sy)&page.rect
    model_pictures=[]
    for n,block in enumerate(b for b in data.get('blocks',[]) if b.get('label')=='Picture' and 'bbox' in b):
        relative=f'assets/indra-{number}-{n}.png'
        if relative in text and (destination.parent/relative).is_file():model_pictures.append(physical(block['bbox']))
    rows=[physical(row['box']) for row in data.get('rows',[]) if row.get('box')]
    for n,values in enumerate(data.get('source_figures',[])):
        box=pymupdf.Rect(values)&page.rect
        if box.is_empty or box.get_area()>=page.rect.get_area()*.7:continue
        if any((box&picture).get_area()>=box.get_area()*.7 for picture in model_pictures):continue
        overlaps=[(box&row).get_area() for row in rows if (box&row).get_area()>0]
        # A text-heavy panel is editable body text, not a standalone figure.
        # Only freshly recognized row geometry participates in this decision.
        if len(overlaps)>=3 and sum(overlaps)>box.get_area()*.4:continue
        relative=f'assets/fresh-figure-{number}-{n}.png'
        if relative in text:continue
        target=destination.parent/relative
        try:
            scale=min(220/72,math.sqrt(3_000_000/max(1,box.get_area())))
            pix=page.get_pixmap(clip=box,matrix=pymupdf.Matrix(scale,scale),
                                colorspace=pymupdf.csRGB,alpha=False,annots=False)
            if pix.is_unicolor and min(pix.pixel(0,0))>=250:continue
            target.parent.mkdir(exist_ok=True);pix.save(target)
            text+=f'\n\n![Figure on page {number}]({relative})'
        except (OSError,RuntimeError,ValueError):
            # Main fresh text and source page remain available if an asset fails.
            continue
    return text


def add_searchable_text(document, scratch: Path, languages: list[str], notify,
                        performance: Performance | None = None, *, force_ocr=False,
                        sequential=False, target_document=None, page_numbers=None) -> dict:
    import pymupdf
    count = len(document)
    requested=list(range(count)) if page_numbers is None else list(page_numbers)
    if any(type(index) is not int or not 0<=index<count for index in requested):
        raise ConversionError('Choose valid zero-based source page numbers for OCR.')
    if requested!=sorted(set(requested)):
        raise ConversionError('OCR pages must be unique and in source order.')
    fresh=target_document is not None
    if fresh:
        if requested and requested!=list(range(len(target_document),len(target_document)+len(requested))):
            raise ConversionError('Fresh OCR pages must append in order after the completed destination pages.')
        force_ocr=True;sequential=True
    elif force_ocr and any(page.get_text().strip() for page in document):
        raise ConversionError('Clean existing text into a separate image-only destination before forcing OCR.')
    if not fresh:
        for page in document:
            if page.rotation:page.remove_rotation()
    output=target_document if fresh else document
    candidates = requested if force_ocr else [i for i in (page_indices(count,performance) if page_numbers is None else requested)
                                             if page_needs_ocr(document[i])]
    workers = (performance or performance_profile()).page_workers()
    from yuzufile.neural_text import available as neural_available
    from yuzufile.indra_engine import available as indra_available
    if sequential or neural_available() or indra_available():
        workers = 1  # ONNX uses the preset's internal thread count; one model copy.
    recognized, completed = 0, 0
    empty_pages = []
    fallback_pages = []
    indra_pages, indra_fallback_pages = [], []
    arabic_print_pages, ocr_warnings = [], []
    source_figures={}
    parts = math.ceil(len(candidates) / workers)

    def consume(item):
        nonlocal recognized, completed
        index, future, image = item
        overlay_path = future.result()
        if image.with_suffix('.indra-fallback.txt').exists():
            indra_fallback_pages.append(index + 1)
        if image.with_suffix('.fallback.txt').exists():
            fallback_pages.append(index + 1)
        # MuPDF's graft cache can retain source-file handles even after close.
        # OCR overlays are small; an in-memory source avoids Windows file locks.
        if overlay_path.suffix == '.json':
            import shutil
            details = json.loads(overlay_path.read_text(encoding='utf-8'))
            if details.get('recognizer_engine'):
                arabic_print_pages.append(index + 1)
            ocr_warnings.extend(f'Page {index + 1}: {warning}' for warning in details.get('quality_warnings', []))
            if fresh or force_ocr:
                cached=_fresh_cache_data(details)
                cached['source_figures']=source_figures.get(index,[])
                (scratch/f'fresh-ocr-page-{index+1}.json').write_text(json.dumps(cached,ensure_ascii=False),encoding='utf-8')
            if details.get('engine', '').startswith('Indra'):
                indra_pages.append(index + 1)
                # A masked hybrid page is incomplete for Markdown; only cache
                # the OCR of pages that originally had no native text.
                if not output[index].get_text().strip():
                    shutil.copyfile(overlay_path, scratch / f'indra-page-{index + 1}.json')
            from yuzufile.neural_text import add_invisible_text
            if add_invisible_text(output[index], overlay_path):
                recognized += 1
            else:
                empty_pages.append(index + 1)
        else:
            with pymupdf.open(stream=overlay_path.read_bytes(), filetype="pdf") as overlay:
                if len(overlay)!=1:raise ConversionError(f'OCR returned an unexpected page count on page {index+1}.')
                if fresh or force_ocr:
                    cached=_fresh_cache_data(_overlay_cache(overlay[0]))
                    cached['source_figures']=source_figures.get(index,[])
                    (scratch/f'fresh-ocr-page-{index+1}.json').write_text(json.dumps(cached,ensure_ascii=False),encoding='utf-8')
                if overlay[0].get_text().strip():
                    output[index].show_pdf_page(output[index].rect, overlay, keep_proportion=False)
                    recognized += 1
                else:
                    empty_pages.append(index + 1)
        if fresh or force_ocr:
            output.xref_set_key(output[index].xref,'PDFaiOCR','true')
            output.xref_set_key(output[index].xref,'PDFaiFreshOCR','true')
            output.xref_set_key(output[index].xref,'PDFaiImageOnly','false' if output[index].get_text().strip() else 'true')
        for path in image.parent.glob(image.stem + "*"):
            path.unlink(missing_ok=True)
        completed += 1
        notify(f"Recognizing text · {completed} of {len(candidates)} pages", completed=completed,
               total=len(candidates), page=index + 1, progress=round(10 + 72 * completed / max(1, len(candidates))))

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="tesseract") as executor:
        for start in range(0, len(candidates), workers):
            # Drain and clean one part before rendering the next. Never queue
            # an entire document's rasters or let completed overlays pile up.
            pending = []
            for index in candidates[start:start + workers]:
                image = scratch / f"page-{index + 1:05d}.png"
                notify(f"Part {start // workers + 1} of {parts} · preparing page {index + 1} of {count}",
                       progress=round(10 + 72 * completed / max(1, len(candidates))))
                if fresh:
                    from yuzufile.ocr_clean import clean_page
                    source_figures[index]=_source_figure_boxes(document[index])
                    notify(f'Cleaning old text · page {index+1} of {count}',page=index+1,
                           progress=round(10+72*completed/max(1,len(candidates))))
                    clean_page(document[index],output)
                    if len(output)!=index+1:raise ConversionError('The clean OCR page sequence is invalid.')
                dpi = render_for_ocr(output[index], image)
                pending.append((index, executor.submit(recognize_page, image, dpi, languages, index + 1), image))
            for item in pending:
                consume(item)
            pending.clear()
            release_page_cache()
    return {"ocr_pages": len(candidates), "recognized_pages": recognized,
            "empty_pages": empty_pages, "reused_pages": len(requested) - len(candidates),
            "ocr_parts": parts, "page_workers": workers, "ocr_fallback_pages": fallback_pages,
            "indra_pages": indra_pages, "indra_fallback_pages": indra_fallback_pages,
            "arabic_print_pages": arabic_print_pages, "ocr_warnings": ocr_warnings,
            "fresh_ocr":fresh or force_ocr,"fresh_ocr_pages":[i+1 for i in candidates] if fresh or force_ocr else [],
            "sequential_ocr":workers==1}


def _text_characters(text: str) -> Counter:
    return Counter(character for character in unicodedata.normalize("NFKC", text).casefold()
                   if character.isalnum())


def _preserves_page_text(source: str, markdown: str) -> bool:
    # Figure captions and link targets must not disguise missing document text.
    body = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", markdown)
    body = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", body)
    if source.strip() and not body.strip():
        return False
    expected = _text_characters(source)
    missing = sum((expected - _text_characters(body)).values())
    return missing <= int(sum(expected.values()) * 0.02)


def write_markdown(document, destination: Path, notify, performance: Performance | None = None, languages=None, native_image_pages=(), use_indra=True, *, fresh_ocr=False) -> list[str]:
    from yuzufile.vision_runtime import available
    if fresh_ocr and any(document.xref_get_key(page.xref,'PDFaiFreshOCR')[1]!='true' for page in document):
        raise ConversionError('Markdown requires freshly recognized, cleaned pages for this conversion.')
    # Native digital text is already accurate and needs no visual inference.
    visual = fresh_ocr or any((index+1 not in native_image_pages and page_needs_ocr(page)) or any('glyphless' in f[3].lower() for f in page.get_fonts())
                 or page.parent.xref_get_key(page.xref, 'PDFaiOCR')[1] == 'true' for index,page in enumerate(document))
    from yuzufile import indra_engine
    if visual and use_indra and indra_engine.available():
        options={'fresh_ocr':True} if fresh_ocr else {}
        return indra_engine.write_markdown(document, destination, notify,
            performance or performance_profile(), languages or ['eng'],**options)
    if visual and available():
        from yuzufile.neural_markdown import write
        options={'sequential':True} if fresh_ocr else {}
        return write(document, destination, notify, performance or performance_profile(), languages or ['eng'],**options)
    import pymupdf
    warnings = []
    converter = None
    headers = False
    try:
        import pymupdf4llm
        pymupdf4llm.use_layout(False)
        converter = pymupdf4llm.to_markdown
    except Exception:
        warnings.append("Structured Markdown was unavailable; readable text and figure export were preserved.")
    if converter:
        try:
            headers = pymupdf4llm.IdentifyHeaders(document, pages=page_indices(
                len(document), performance, notify, "Checking Markdown headings", 83, 83))
        except Exception:
            warnings.append("Heading detection was unavailable; text extraction continued.")
    assets = destination.parent / "assets"
    seen_images = {}
    part_size = 1 if fresh_ocr else (performance or performance_profile()).page_workers()
    with destination.open("w", encoding="utf-8") as stream:
        for index, page in enumerate(document):
            if index % part_size == 0:
                release_page_cache()
            notify(f"Writing Markdown · part {index // part_size + 1} of {math.ceil(len(document) / part_size)} · page {index + 1} of {len(document)}",
                   progress=round(83 + 12 * (index + 1) / len(document)))
            plain_text = page.get_text(sort=True)
            if converter:
                try:
                    # Graphics segmentation can swallow an invisible OCR layer
                    # on slides / scans assembled from many images and paths.
                    ocr_layer = any("glyphless" in font[3].casefold() for font in page.get_fonts())
                    text = converter(document, pages=[index], hdr_info=headers,
                        ignore_images=True, ignore_code=True, ignore_alpha=True,
                        fontsize_limit=0, force_text=True, ignore_graphics=ocr_layer,
                        detect_bg_color=False, show_progress=False)
                    if not isinstance(text, str):
                        text = ""
                    if not _preserves_page_text(plain_text, text) and not ocr_layer:
                        text = converter(document, pages=[index], hdr_info=headers,
                            ignore_images=True, ignore_code=True, ignore_alpha=True,
                            fontsize_limit=0, force_text=True, ignore_graphics=True,
                            detect_bg_color=False, show_progress=False)
                        warnings.append(f"Page {index + 1}: simplified layout to preserve existing text.")
                    if not isinstance(text, str) or not _preserves_page_text(plain_text, text):
                        text = plain_text
                        warnings.append(f"Page {index + 1}: used plain-text layout because structured extraction omitted text.")
                except Exception:
                    text = plain_text
                    warnings.append(f"Page {index + 1}: used plain-text layout because structured extraction was unavailable.")
            else:
                text = plain_text
            if fresh_ocr:text=_fresh_figure_markdown(page,index+1,destination,text)
            stream.write(text.strip() + "\n\n")
            # Avoid decoding/hashing every original scan just to discover that
            # it is a full-page image which should not be exported as a figure.
            basic_images = page.get_image_info()
            if not any((pymupdf.Rect(info["bbox"]) & page.rect).get_area() < page.rect.get_area() * 0.7
                       for info in basic_images):
                continue
            for info in page.get_image_info(xrefs=True):
                rect = pymupdf.Rect(info["bbox"]) & page.rect
                if rect.get_area() >= page.rect.get_area() * 0.7 or not info["xref"]:
                    continue
                xref = info["xref"]
                try:
                    if xref not in seen_images:
                        assets.mkdir(exist_ok=True)
                        seen_images[xref] = export_figure(document, xref, destination.parent)
                    stream.write(f"![Figure on page {index + 1}]({seen_images[xref]})\n\n")
                except Exception:
                    warnings.append(f"Page {index + 1}: a figure could not be exported; its source remains in the PDF.")
    release_page_cache()
    return warnings


def export_figure(document, xref: int, directory: Path) -> str:
    """Limit encoded buffers and decoded pixmaps to a single figure's lifetime."""
    import pymupdf
    image = document.extract_image(xref)
    suffix = image["ext"] if image["ext"] in {"png", "jpeg", "jpg"} else "png"
    relative = f"assets/figure-{xref}.{suffix}"
    path = directory / relative
    if suffix == image["ext"]:
        path.write_bytes(image["image"])
    else:
        pixmap = pymupdf.Pixmap(document, xref)
        if pixmap.n > 4:
            pixmap = pymupdf.Pixmap(pymupdf.csRGB, pixmap)
        pixmap.save(path)
    return relative
