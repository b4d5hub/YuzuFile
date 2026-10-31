"""Disk-backed, bounded batches of visual OCR with coordinate-aware recovery."""
import gc
import json
import math
from pathlib import Path
import re
import unicodedata
from contextlib import contextmanager
from difflib import SequenceMatcher

from yuzufile import neural_text
from yuzufile.vision_runtime import VisionRuntime


MARKER = re.compile(r'!\[([\w+]+)\]\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)')


@contextmanager
def optional_runtime(engine, scratch, threads, warnings, used):
    runtime = VisionRuntime(engine, scratch, threads)
    try:
        runtime.__enter__()
    except Exception as error:
        warnings.append(f'{engine}: local model could not load ({type(error).__name__}); retained other OCR results.')
        import logging
        logging.getLogger(__name__).error('%s', error)
        yield None
    else:
        used.add(engine)
        try:
            yield runtime
        finally:
            runtime.__exit__(None, None, None)


def layout_reader(threads):
    from rapid_layout import RapidLayout, ModelType, RapidLayoutInput
    from rapid_layout.inference_engine.onnxruntime.main import OrtInferSession
    from rapid_layout.model_handler import ModelHandler
    from rapid_layout.utils.load_image import LoadImage
    import onnxruntime as ort
    class BoundedSession(OrtInferSession):
        @staticmethod
        def _init_sess_opts(cfg):
            options = OrtInferSession._init_sess_opts(cfg)
            options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
            options.enable_mem_pattern = False
            return options
    cfg = RapidLayoutInput(model_type=ModelType.PP_DOC_LAYOUTV3,
        model_dir_or_path=str(neural_text.model_root() / 'layout/pp_doc_layoutv3.onnx'),
        engine_cfg={'intra_op_num_threads': threads, 'inter_op_num_threads': 1, 'enable_cpu_mem_arena': False})
    reader = RapidLayout.__new__(RapidLayout)
    reader.session = BoundedSession(cfg)
    reader.model_handler = ModelHandler(cfg, reader.session)
    reader.load_img = LoadImage()
    return reader


def blocks(text):
    matches = list(MARKER.finditer(text))
    return [dict(kind=m[1].rstrip('+'), box=[min(1000, int(m[i])) / 1000 for i in range(2, 6)],
                 text=text[m.end():matches[i + 1].start() if i + 1 < len(matches) else len(text)].strip())
            for i, m in enumerate(matches)]


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKC', text).casefold() if c.isalnum())


def missing_rows(rows, text):
    body = normalized(text)
    lines = [(normalized(line), re.findall(r'\d+', line)) for line in text.splitlines() if normalized(line)]
    return [r for r in rows if r['score'] >= .65 and len(normalized(r['text'])) > 2
            and normalized(r['text']) not in body
            and not any(re.findall(r'\d+', r['text']) == digits and
                        SequenceMatcher(None, normalized(r['text']), line, autojunk=False).ratio() >= .90
                        for line,digits in lines)]


def slide_regions(page):
    """Recognize four-up handouts from their drawn slide frames, retaining source order."""
    import pymupdf
    result = []
    for drawing in page.get_drawings():
        for item in drawing['items']:
            if item[0] != 're':
                continue
            rect = pymupdf.Rect(item[1]) & page.rect
            if (rect.height > 0 and 1.72 < rect.width / rect.height < 1.83
                    and .15 < rect.get_area() / page.rect.get_area() < .30
                    and not any(abs(rect.x0 - old.x0) < 2 and abs(rect.y0 - old.y0) < 2 for old in result)):
                result.append(rect)
    if len(result) == 4 and all((a & b).get_area() < 4 for i, a in enumerate(result) for b in result[i+1:]):
        return result
    return [page.rect]


def prepare(page, rect, target, details=None):
    import pymupdf
    from PIL import Image, ImageChops
    scale = min(400 / 72, 2048 / max(rect.width, rect.height))
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=rect,
                         colorspace=pymupdf.csRGB, alpha=False, annots=False)
    image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
    # Blank scan margins consume vision tokens without adding information.
    # Trim only when a substantial uniform border surrounds the content.
    background = Image.new('RGB', image.size, image.getpixel((0, 0)))
    difference = ImageChops.difference(image, background).convert('L').point(lambda value: 255 if value > 2 else 0)
    bounds = difference.getbbox()
    offset = (0, 0)
    difference.close()
    background.close()
    if bounds and (bounds[2]-bounds[0]) * (bounds[3]-bounds[1]) < image.width * image.height * .70:
        x0,y0,x1,y1 = bounds
        offset = (max(0,x0-16), max(0,y0-16))
        cropped = image.crop((*offset, min(image.width,x1+16), min(image.height,y1+16)))
        image.close()
        image = cropped
    image.save(target, compress_level=1)
    size = image.size
    image.close()
    if details is not None:
        details.update(scale=scale, offset=offset, origin=(rect.x0, rect.y0))
    return size


def render_detail(document, item, box, target):
    """Rerender just a difficult figure from PDF vectors, rather than enlarging pixels."""
    import pymupdf
    transform = item['transform']
    scale = transform['scale']
    ox, oy = transform['offset']
    px, py = transform['origin']
    x0,y0,x1,y1 = box
    page = document[item['page']-1]
    clip = pymupdf.Rect(px+(x0+ox)/scale, py+(y0+oy)/scale,
                        px+(x1+ox)/scale, py+(y1+oy)/scale)
    clip = (clip + (-2,-2,2,2)) & page.rect
    if clip.is_empty:
        raise ValueError('Empty figure region')
    zoom = min(8, 2048 / max(clip.width, clip.height))
    page.get_pixmap(clip=clip, matrix=pymupdf.Matrix(zoom,zoom), colorspace=pymupdf.csRGB,
                   alpha=False, annots=False).save(target)


def write(document, destination, notify, performance, languages, *, sequential=False):
    from yuzufile.neural_task import run
    from PIL import Image, ImageStat
    scratch = destination.parent / 'scratch'
    assets = destination.parent / 'assets'
    warnings = []
    used = {'rapidocr'}
    threads = performance.page_workers()
    part_size = 1 if sequential else threads
    neural_text.release()
    with destination.open('w', encoding='utf-8') as stream:
        for start in range(0, len(document), part_size):
            items = []
            for index in range(start, min(start + part_size, len(document))):
                for region, rect in enumerate(slide_regions(document[index])):
                    name = f'page-{index+1:04d}-region-{region+1}'
                    image = scratch / (name + '.png')
                    notify(f'Reading page {index+1} · region {region+1}', progress=83 + 12 * index / len(document))
                    transform = {}
                    width, height = prepare(document[index], rect, image, transform)
                    items.append(dict(page=index+1, region=region+1, name=name, image=image,
                                      width=width, height=height, rows=[], tables=[],
                                      native=document[index].get_text(clip=rect, sort=True), transform=transform))
            try:
                rows = run('rapid', [item['image'] for item in items], languages or ['eng'], threads)
            except Exception:
                rows = [[dict(text=item['native'], score=1., box=[0,0,item['width'],item['height']])]
                        for item in items]
                description='earlier fresh OCR text' if sequential else 'the existing PDF text layer'
                warnings.append(f'Pages {start+1}–{min(start+part_size,len(document))}: layout OCR failed; preserved {description}. Review the source images.')
                used.discard('rapidocr')
            for item, recognized in zip(items, rows):
                item['rows'] = recognized
            gc.collect()
            # Layout is optional: grounded VLM blocks also identify tables.
            # Never retain both ONNX model families in memory together.
            try:
                detected = run('layout', [item['image'] for item in items], [], threads)
                for item, tables in zip(items, detected):
                    item['tables'] = tables
                used.add('pp-doclayoutv3')
            except Exception:
                warnings.append(f'Pages {start+1}–{min(start+part_size,len(document))}: layout model was unavailable; used grounded visual structure instead.')
            gc.collect()
            with optional_runtime('lighton', scratch, threads, warnings, used) as runtime:
                for item in items:
                    notify(f'Structuring page {item["page"]} · region {item["region"]}', progress=83 + 12 * start / len(document))
                    try:
                        if runtime is None:
                            raise RuntimeError('Model unavailable')
                        raw = runtime.recognize(item['image'], 'grounding')
                        item['blocks'] = blocks(raw)
                        if not item['tables']:
                            item['tables'] = [[b['box'][0]*item['width'], b['box'][1]*item['height'],
                                               b['box'][2]*item['width'], b['box'][3]*item['height']]
                                              for b in item['blocks'] if b['kind'] == 'table']
                        item['text'] = '\n\n'.join(b['text'] for b in item['blocks']
                            if b['kind'] not in {'image', 'chart', 'header_image', 'footer_image'})
                        if not item['blocks']:
                            item['text'] = raw.strip()
                            warnings.append(f'Page {item["page"]}: structure coordinates were unavailable.')
                    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
                        item['text'], item['blocks'] = '', []
                        warnings.append(f'Page {item["page"]}: structure recognition failed; OCR text was retained ({type(error).__name__}).')
                    item['missing'] = missing_rows(item['rows'], item['text'])
                    item['graphics'] = [b for b in item['blocks'] if b['kind'] in {'image', 'chart'}]
                    targets = item['tables'] + [[b['box'][0]*item['width'],b['box'][1]*item['height'],
                                                b['box'][2]*item['width'],b['box'][3]*item['height']]
                                               for b in item['graphics']]
                    # Figure/table labels are already scheduled for targeted
                    # high-resolution OCR. Do not also reread the whole page.
                    item['missing'] = [row for row in item['missing']
                                       if not any(neural_text.overlap(row['box'],box) > .5 for box in targets)]
            reviews = [item for item in items if item['missing'] or item['tables'] or item['graphics']]
            if reviews:
                with optional_runtime('paddle', scratch, threads, warnings, used) as runtime:
                    for item in reviews:
                        notify(f'Verifying page {item["page"]} · region {item["region"]}', progress=83 + 12 * start / len(document))
                        if item['missing']:
                            try:
                                if runtime is None:
                                    raise RuntimeError('Model unavailable')
                                alternative = runtime.recognize(item['image'], 'OCR:')
                                if len(missing_rows(item['rows'], alternative)) < len(item['missing']):
                                    item['text'] = alternative
                            except (OSError, RuntimeError, ValueError, KeyError, TypeError):
                                warnings.append(f'Page {item["page"]}: secondary text verification was unavailable.')
                        for number, box in enumerate(item['tables']):
                            with Image.open(item['image']) as original:
                                x0,y0,x1,y1 = box
                                box = (max(0,int(x0)), max(0,int(y0)), min(original.width,math.ceil(x1)), min(original.height,math.ceil(y1)))
                                if box[2] <= box[0] or box[3] <= box[1]:
                                    continue
                                crop = scratch / f'{item["name"]}-table-{number}.png'
                                render_detail(document, item, box, crop)
                            try:
                                if runtime is None:
                                    raise RuntimeError('Model unavailable')
                                table = runtime.recognize(crop, 'Table Recognition:')
                                # Keep the table as a separate verified region instead of
                                # overwriting adjacent text based on incompatible scores.
                                item.setdefault('verified_tables', []).append(table)
                            except (OSError, RuntimeError, ValueError, KeyError, TypeError):
                                warnings.append(f'Page {item["page"]}: table transcription was unavailable; its image was preserved.')
                            finally:
                                crop.unlink(missing_ok=True)
                        for number, block in enumerate(item['graphics']):
                            with Image.open(item['image']) as original:
                                x0,y0,x1,y1 = block['box']
                                box = (int(x0*original.width),int(y0*original.height),int(x1*original.width),int(y1*original.height))
                                if box[2]-box[0] < 25 or box[3]-box[1] < 25:
                                    continue
                                has_text = any(neural_text.overlap(row['box'],box) > .5 for row in item['rows'])
                                if not has_text:
                                    inset = max(2,min(box[2]-box[0],box[3]-box[1])//6)
                                    with original.crop((box[0]+inset,box[1]+inset,box[2]-inset,box[3]-inset)) as interior:
                                        if max(ImageStat.Stat(interior).stddev) < 1:
                                            continue  # A flat fill has no figure labels to read.
                                crop = scratch / f'{item["name"]}-figure-{number}.png'
                                render_detail(document, item, box, crop)
                            try:
                                if runtime is None:
                                    raise RuntimeError('Model unavailable')
                                labels = runtime.recognize(crop, 'OCR:', max_tokens=768).strip()
                                if labels and normalized(labels) not in normalized(item['text']):
                                    item.setdefault('figure_text', []).append(labels)
                            except (OSError,RuntimeError,ValueError,KeyError,TypeError):
                                warnings.append(f'Page {item["page"]}: figure text verification was unavailable; review the source image.')
                            finally:
                                crop.unlink(missing_ok=True)
            for item in items:
                stream.write(f'<!-- Page {item["page"]}, region {item["region"]} -->\n\n')
                stream.write(item['text'].strip() + '\n\n')
                verified = '\n'.join(item.get('verified_tables', []) + item.get('figure_text', []))
                remaining = missing_rows(item['rows'], item['text'] + '\n' + verified)
                if remaining:
                    stream.write('Additional recognized text:\n\n')
                    stream.write('\n\n'.join(r['text'] for r in remaining) + '\n\n')
                    warnings.append(f'Page {item["page"]}: retained {len(remaining)} OCR lines that structured extraction did not reproduce. Review against the page image.')
                for table in item.get('verified_tables', []):
                    if normalized(table) not in normalized(item['text']):
                        stream.write('Table transcription (secondary OCR):\n\n' + table.strip() + '\n\n')
                for labels in item.get('figure_text', []):
                    stream.write('Figure text:\n\n' + labels + '\n\n')
                # A complete region image preserves vector labels, diagrams, and
                # uncertain transcriptions without hundreds of fragment assets.
                assets.mkdir(exist_ok=True)
                target = assets / item['image'].name
                item['image'].replace(target)
                stream.write(f'![Source page {item["page"]}, region {item["region"]}](assets/{target.name})\n\n')
            if sequential:
                from yuzufile.engines import _fresh_figure_markdown
                figures=_fresh_figure_markdown(document[start],start+1,destination,'')
                if figures:stream.write(figures.strip()+'\n\n')
            notify(f'Completed Markdown through page {min(start+part_size,len(document))}',
                   progress=83 + 12 * min(start+part_size,len(document)) / len(document))
            from yuzufile.resources import trim_cache
            trim_cache()
    (scratch / 'markdown-engines.json').write_text(json.dumps(sorted(used)), encoding='utf-8')
    return warnings
