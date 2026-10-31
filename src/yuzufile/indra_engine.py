"""Personal-build Indra adapter: pinned local weights, bounded CPU inference.

Model terms are in vendor/neural/indra/LICENSE. No automatic downloads are
permitted here; model acquisition is an explicit developer build operation.
"""
import json
import math
import subprocess
from pathlib import Path

from yuzufile.neural_text import model_root, arabic


ENGINE = 'Indra OCR 1.1.2 / models 1.1.0 / CPU'
REQUIRED = ('det.onnx', 'rec.onnx', 'order.onnx', 'meta.json', 'orient.onnx',
            'script.onnx', 'rec_rtl.onnx', 'rec_cjk.onnx', 'rec_world.onnx',
            'lm.npz', 'lm_cjk.npz', 'lm_world.npz', 'LICENSE')


class NeedsReview(RuntimeError):
    pass


def needs_review(data):
    rows = data.get('rows', [])
    return (any(b.get('label') == 'Table' for b in data.get('blocks', []))
            or '<table' in (data.get('markdown') or '').lower()
            or any(len(row['text'].strip()) > 12 and row['score'] < .7 for row in rows))


def coverage_text(text):
    import html
    import re
    return html.unescape(re.sub(r'<[^>]*>', ' ', text))


def available():
    root = model_root() / 'indra'
    return (root / 'ready.json').is_file() and all((root / n).is_file() for n in REQUIRED)


class Reader:
    def __init__(self, threads, languages=None):
        if not available():
            raise RuntimeError('The complete offline Indra model set is unavailable.')
        import indra_ocr
        import cv2
        self.threads = max(1, min(4, int(threads)))
        self.languages = languages or []
        self.arabic_reader = None
        cv2.setNumThreads(self.threads)
        self.converter = indra_ocr.load(path=model_root() / 'indra', threads=self.threads,
            providers=['CPUExecutionProvider'], mode='ocr', furniture=True, math=False)

    def read(self, path):
        import cv2
        import numpy as np
        # OpenCV's Windows filename reader cannot open non-ASCII paths.
        # NumPy opens the Unicode path; OpenCV decodes only the image bytes.
        encoded = np.fromfile(path, dtype=np.uint8)
        gray = cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)
        del encoded
        if gray is None:
            raise RuntimeError('Could not read the page image.')
        height, width = gray.shape
        page = self.converter.ocr(gray)
        if page.source == 'error':
            raise RuntimeError('Indra could not recognize this page.')
        rotation = int(page.rotation) % 360
        if rotation not in (0, 90, 180, 270):
            raise RuntimeError('Indra returned an unsupported page orientation.')
        ow, oh = (height, width) if rotation in (90, 270) else (width, height)
        rows = []
        for line in page.lines:
            box = [float(v) for v in line.box]
            if len(box) != 4 or not all(math.isfinite(v) for v in box):
                raise RuntimeError('Indra returned invalid text coordinates.')
            box = [max(0, min(ow, box[0])), max(0, min(oh, box[1])),
                   max(0, min(ow, box[2])), max(0, min(oh, box[3]))]
            if line.text.strip() and box[2] > box[0] and box[3] > box[1]:
                score = float(line.conf)
                rows.append(dict(box=box, text=line.text, score=score if math.isfinite(score) else 0))
        data = dict(width=ow, height=oh, rotation=rotation, rows=rows,
                    markdown=page.markdown or page.text, blocks=page.blocks,
                    engine=ENGINE, timings=page.timings)
        if 'ara' in getattr(self, 'languages', []):
            from yuzufile import arabic_ocr
            if arabic_ocr.available():
                try:
                    if self.arabic_reader is None:
                        self.arabic_reader = arabic_ocr.Reader(self.threads)
                    data = self.arabic_reader.refine(path, data)
                except (RuntimeError, OSError, ValueError, MemoryError) as error:
                    data['quality_warnings'] = [f'Arabic print refinement unavailable ({type(error).__name__}); check the retained OCR text.']
        return data


def recognize(image, languages, threads):
    from yuzufile.neural_task import run
    data = run('indra', [image], languages, threads)[0]
    target = image.with_suffix('.ocr.json')
    target.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    return target


def write_markdown(document, destination, notify, performance, languages, *, fresh_ocr=False):
    """One page raster at a time; reuse OCR results for image-only pages."""
    import re
    from PIL import Image
    import pymupdf
    from yuzufile.resources import page_indices
    from yuzufile.neural_markdown import missing_rows
    scratch = destination.parent / 'scratch'
    scratch.mkdir(exist_ok=True)
    used, warnings = set(), []
    with destination.open('w', encoding='utf-8') as stream:
        for index in page_indices(len(document), performance):
            page = document[index]
            notify(f'Indra Markdown · page {index + 1} of {len(document)}',
                   progress=round(83 + 12 * index / len(document)))
            image = scratch / 'indra-markdown.png'
            cached = scratch / f'indra-page-{index + 1}.json'
            result = None
            try:
                if cached.is_file():
                    data = json.loads(cached.read_text(encoding='utf-8'))
                elif fresh_ocr:
                    # Upstream recognition has already read this clean page.
                    # A fallback OCR engine needs the existing detailed-layout
                    # path, not another attempt at Indra recognition.
                    raise RuntimeError('This cleaned page used fallback OCR; continuing with its detailed layout pipeline.')
                else:
                    scale = min(220 / 72, math.sqrt(8_000_000 / max(1, page.rect.get_area())))
                    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False, annots=False)
                    pix.save(image)
                    del pix
                    result = recognize(image, languages, performance.page_workers())
                    data = json.loads(result.read_text(encoding='utf-8'))
                used.add('indra-ocr-1.1.2')
                from yuzufile.vision_runtime import available as detailed_available
                # Do not replace a specialized Arabic transcript with a less
                # accurate general VLM merely because a line needs review.
                table_review = any(b.get('label') == 'Table' for b in data.get('blocks', []))
                if needs_review(data) and detailed_available() and (not data.get('recognizer_engine') or table_review):
                    raise NeedsReview('Tables or uncertain text require detailed verification.')
                text = data['markdown'] or ''
                if data.get('recognizer_engine'):
                    used.add('kraken-ppocrv6-arabic-print')
                # Retain native / previously recognized text if layout misses it.
                for row in missing_rows(data['rows'], coverage_text(text)):
                    text += '\n\n' + row['text']
                from yuzufile.engines import _preserves_page_text
                plain = page.get_text(sort=True)
                if plain.strip() and not _preserves_page_text(plain, coverage_text(text)):
                    # Recover missing lines, rather than silently losing text.
                    recovered = missing_rows([dict(text=s, score=1) for s in plain.splitlines() if s.strip()], coverage_text(text))
                    text += ''.join('\n\n' + row['text'] for row in recovered)
                    warnings.append(f'Page {index + 1}: retained existing text omitted by Indra layout.')
                pictures = [b for b in data.get('blocks', []) if b.get('label') == 'Picture']
                if not pictures:
                    # Solid-colour plots and simple illustrations can be missed
                    # by picture detection. Retain embedded source figures too.
                    from yuzufile.engines import export_figure
                    for info in page.get_image_info(xrefs=True):
                        area = (pymupdf.Rect(info['bbox']) & page.rect).get_area()
                        if info['xref'] and 0 < area < page.rect.get_area() * .7:
                            (destination.parent / 'assets').mkdir(exist_ok=True)
                            relative = export_figure(document, info['xref'], destination.parent)
                            text += f'\n\n![Figure on page {index + 1}]({relative})'
                if pictures:
                    if not image.is_file():
                        scale = min(220 / 72, math.sqrt(8_000_000 / max(1, page.rect.get_area())))
                        pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False, annots=False)
                        pix.save(image)
                        del pix
                    with Image.open(image) as original:
                        upright = original.rotate(data['rotation'], expand=True)
                        try:
                            for n, block in enumerate(pictures):
                                relative = f'assets/indra-{index + 1}-{n}.png'
                                target = destination.parent / relative
                                target.parent.mkdir(exist_ok=True)
                                # Raster dimensions can differ by a rounding pixel.
                                sx, sy = upright.width / data['width'], upright.height / data['height']
                                x0,y0,x1,y1 = block['bbox']
                                box = (max(0, int(x0*sx)), max(0, int(y0*sy)),
                                       min(upright.width, math.ceil(x1*sx)), min(upright.height, math.ceil(y1*sy)))
                                if box[2] <= box[0] or box[3] <= box[1]:
                                    continue
                                with upright.crop(box) as crop:
                                    crop.save(target)
                                token = f'picture-{n}'
                                text = text.replace(f']({token})', f']({relative})')
                                if relative not in text:
                                    text += f'\n\n![Figure on page {index + 1}]({relative})'
                        finally:
                            upright.close()
                # Do not leave broken placeholder links in Markdown.
                text = re.sub(r'!\[([^\]]*)\]\(picture-\d+\)', r'[Figure: \1]', text)
                if fresh_ocr:
                    from yuzufile.engines import _fresh_figure_markdown
                    text=_fresh_figure_markdown(page,index+1,destination,text)
                stream.write(text.strip() + '\n\n')
                if needs_review(data):
                    warnings.append(f'Page {index + 1}: table structure or uncertain text needs review.' if data.get('recognizer_engine') else
                                    f'Page {index + 1}: table structure or uncertain text needs review; detailed models were unavailable.')
            except (RuntimeError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
                if isinstance(error, NeedsReview):
                    notify(f'Detailed layout verification · page {index + 1}', progress=round(83 + 12 * index / len(document)))
                else:
                    warnings.append(f'Page {index + 1}: Indra unavailable ({type(error).__name__}); used existing Markdown engines.')
                # A one-page copy keeps fallback inference bounded and independent.
                with pymupdf.open() as one:
                    one.insert_pdf(document, from_page=index, to_page=index)
                    if fresh_ocr:
                        # insert_pdf deliberately drops custom page keys; carry
                        # the provenance of this known fresh one-page copy.
                        one.xref_set_key(one[0].xref,'PDFaiFreshOCR','true')
                        one.xref_set_key(one[0].xref,'PDFaiOCR','true')
                    fallback = scratch / 'indra-fallback.md'
                    (fallback.parent / 'scratch').mkdir(exist_ok=True)
                    from yuzufile.engines import write_markdown as existing
                    def fallback_notify(stage, **extra):
                        fraction = max(0, min(1, (extra.get('progress', 83) - 83) / 12))
                        extra['progress'] = round(83 + 12 * (index + fraction) / len(document))
                        notify(stage, **extra)
                    options={'fresh_ocr':True} if fresh_ocr else {}
                    page_warnings = existing(one, fallback, fallback_notify, performance, languages, use_indra=False,**options)
                    warnings.extend(re.sub(r'^Page 1(?=[: ])', f'Page {index + 1}', w) for w in page_warnings)
                    used_file = fallback.parent / 'scratch/markdown-engines.json'
                    if used_file.is_file():
                        used.update(json.loads(used_file.read_text(encoding='utf-8')))
                    text = fallback.read_text(encoding='utf-8')
                    text = text.replace('<!-- Page 1, region ', f'<!-- Page {index + 1}, region ')
                    text = text.replace('![Source page 1, region ', f'![Source page {index + 1}, region ')
                    # Fallback assets live under scratch; move with unique names.
                    for asset in (scratch / 'assets').glob('*'):
                        relative = f'assets/fallback-{index + 1}-{asset.name}'
                        target = destination.parent / relative
                        target.parent.mkdir(exist_ok=True)
                        asset.replace(target)
                        text = text.replace('assets/' + asset.name, relative)
                    if fresh_ocr:
                        from yuzufile.engines import _fresh_figure_markdown
                        text=_fresh_figure_markdown(page,index+1,destination,text)
                    stream.write(text.strip() + '\n\n')
                    fallback.unlink(missing_ok=True)
                used.add('existing-page-fallback')
            finally:
                image.unlink(missing_ok=True)
                if result:
                    result.unlink(missing_ok=True)
                if fresh_ocr:
                    from yuzufile.resources import trim_cache
                    trim_cache()
            notify(f'Markdown page {index + 1} complete', progress=round(83 + 12 * (index + 1) / len(document)))
            if fresh_ocr:
                from yuzufile.resources import trim_cache
                trim_cache()
    (scratch / 'markdown-engines.json').write_text(json.dumps(sorted(used)), encoding='utf-8')
    return warnings


def output_license(directory):
    import shutil
    target = directory / 'INDRA-MODEL-LICENSE.txt'
    shutil.copyfile(model_root() / 'indra/LICENSE', target)
    (directory / 'INDRA-NOTICE.txt').write_text(
        'Personal-use build. OCR/layout by Datalab Indra OCR 1.1 (package 1.1.2).\n'
        'Models: https://huggingface.co/datalab-to/indra-ocr/tree/v1.1.0\n'
        'Weights were not modified. Model and generated outputs are subject to\n'
        'the accompanying modified OpenRAIL-M license, including section 8.\n'
        'Do not redistribute this build without reviewing the model terms.\n', encoding='utf-8')
