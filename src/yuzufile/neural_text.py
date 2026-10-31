"""Offline RapidOCR recognition. MuPDF calls remain on the conversion thread."""
from pathlib import Path
import json
import os
import sys
import threading
import unicodedata


def model_root() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / 'neural'
    return Path(__file__).resolve().parents[2] / 'vendor/neural'


def available() -> bool:
    return (model_root() / 'rapid/ready.json').is_file() and all((model_root() / 'rapid' / name).is_file() for name in (
        'PP-OCRv6_det_small.onnx', 'PP-OCRv6_rec_medium.onnx', 'arabic_PP-OCRv5_rec_mobile.onnx'))


def arabic(text: str) -> bool:
    return any('ARABIC' in unicodedata.name(char, '') for char in text)


def overlap(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    area = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return intersection / max(1, area)


class RapidReader:
    def __init__(self, languages, threads):
        from rapidocr import RapidOCR, ModelType, LangRec, OCRVersion
        import cv2
        cv2.setNumThreads(threads)
        from rapidocr.inference_engine.onnxruntime.main import OrtInferSession
        import onnxruntime as ort
        def bounded_options(cfg):
            options = ort.SessionOptions()
            options.log_severity_level = 4
            options.enable_cpu_mem_arena = False
            options.enable_mem_pattern = False
            options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
            options.intra_op_num_threads = threads
            options.inter_op_num_threads = 1
            return options
        OrtInferSession._init_sess_opts = staticmethod(bounded_options)
        # Keep RapidOCR's RTL correction: the Arabic recognizer's visual
        # character sequence needs its bidi conversion before text export.
        self.models = []
        root = model_root() / 'rapid'
        scripts = ['latin'] if set(languages) & {'eng', 'fra'} else []
        if 'ara' in languages:
            scripts.append('arabic')
        for script in scripts:
            latin = script == 'latin'
            params = {
                'Global.use_cls': False, 'Global.log_level': 'error',
                'Global.max_side_len': 4096, 'Global.text_score': 0.3,
                'Det.model_path': str(root / 'PP-OCRv6_det_small.onnx'),
                'Det.model_type': ModelType.SMALL, 'Det.ocr_version': OCRVersion.PPOCRV6,
                'Det.limit_side_len': 1280, 'Det.limit_type': 'max',
                'Rec.model_path': str(root / ('PP-OCRv6_rec_medium.onnx' if latin else 'arabic_PP-OCRv5_rec_mobile.onnx')),
                'Rec.model_type': ModelType.MEDIUM if latin else ModelType.MOBILE,
                'Rec.ocr_version': OCRVersion.PPOCRV6 if latin else OCRVersion.PPOCRV5,
                'Rec.lang_type': LangRec.EN if latin else LangRec.ARABIC,
                'Rec.rec_batch_num': threads,
                'EngineConfig.onnxruntime.intra_op_num_threads': threads,
                'EngineConfig.onnxruntime.inter_op_num_threads': 1,
                'EngineConfig.onnxruntime.enable_cpu_mem_arena': False,
            }
            self.models.append((script, RapidOCR(params=params)))

    def read(self, image):
        results = []
        for script, model in self.models:
            output = model(image)
            if output.boxes is None or output.txts is None:
                continue
            for polygon, text, score in zip(output.boxes, output.txts, output.scores):
                if not text.strip():
                    continue
                box = [float(polygon[:, 0].min()), float(polygon[:, 1].min()),
                       float(polygon[:, 0].max()), float(polygon[:, 1].max())]
                candidate = dict(box=box, text=text.strip(), score=float(score), script=script)
                matched = next((i for i, old in enumerate(results) if overlap(box, old['box']) >= 0.65), None)
                if matched is None:
                    results.append(candidate)
                elif (script == 'arabic' and arabic(text)) or (not arabic(results[matched]['text']) and score > results[matched]['score']):
                    results[matched] = candidate
        return sorted(results, key=lambda row: (round(row['box'][1] / 8), row['box'][0]))


_readers = {}
_lock = threading.Lock()


def release():
    import gc
    with _lock:
        _readers.clear()
    gc.collect()


def recognize(image: Path, languages: list[str]) -> Path:
    from PIL import Image
    threads = max(1, min(4, int(os.environ.get('OMP_NUM_THREADS', '2'))))
    key = (tuple(sorted(languages)), threads)
    # Keep one ORT reader active at a time; its internal threads follow the
    # preset. Loading one copy per page would multiply model memory use.
    with _lock:
        from yuzufile.neural_task import run
        rows = run('rapid', [image], languages, threads)[0]
    with Image.open(image) as opened:
        size = opened.size
    target = image.with_suffix('.ocr.json')
    target.write_text(json.dumps(dict(width=size[0], height=size[1], rows=rows), ensure_ascii=False), encoding='utf-8')
    return target


def add_invisible_text(page, result: Path) -> bool:
    import pymupdf
    data = json.loads(result.read_text(encoding='utf-8'))
    if data.get('rotation', 0):
        # Indra boxes are on the counter-clockwise upright page. Build the
        # invisible overlay there, then rotate it back onto the source page.
        rotation = int(data['rotation'])
        if rotation not in (90, 180, 270):
            raise ValueError('Invalid OCR overlay orientation.')
        upright = dict(data, rotation=0)
        temporary = result.with_suffix('.upright.json')
        temporary.write_text(json.dumps(upright, ensure_ascii=False), encoding='utf-8')
        try:
            with pymupdf.open() as overlay:
                width, height = (page.rect.height, page.rect.width) if rotation in (90, 270) else (page.rect.width, page.rect.height)
                target = overlay.new_page(width=width, height=height)
                added = add_invisible_text(target, temporary)
                if added:
                    page.show_pdf_page(page.rect, overlay, rotate=-rotation)
                    page.parent.xref_set_key(page.xref, 'PDFaiOCR', 'true')
                return added
        finally:
            temporary.unlink(missing_ok=True)
    sx, sy = page.rect.width / data['width'], page.rect.height / data['height']
    writer = pymupdf.TextWriter(page.rect)
    latin_font = pymupdf.Font('helv')
    # MuPDF's automatic Arabic fallback drops combining vowel marks from its
    # ToUnicode map. Use Windows' Arabic-capable font explicitly for those rows.
    # Keep Latin rows on Helvetica so URLs/hyphens retain their exact mapping.
    arabic_font = latin_font
    if any(arabic(row['text']) for row in data['rows']):
        path = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/arial.ttf'
        if path.is_file():
            arabic_font = pymupdf.Font(fontfile=str(path))
    added = False
    for row in data['rows']:
        x0, y0, x1, y1 = row['box']
        text = row['text']
        font = arabic_font if arabic(text) else latin_font
        height, width = max(1, (y1 - y0) * sy), max(1, (x1 - x0) * sx)
        size = min(height / (font.ascender - font.descender), width / max(0.01, font.text_length(text, fontsize=1)))
        # An explicit RTL boundary stops the extractor moving a final combining
        # vowel to the beginning of the line. The logical OCR cache stays exact.
        overlay_text = text + '\u200f' if arabic(text) else text
        writer.append((x0 * sx, y1 * sy - height * 0.15), overlay_text, font=font, fontsize=max(0.5, size),
                      right_to_left=arabic(text))
        added = True
    if added:
        writer.write_text(page, render_mode=3, overlay=True)
        if any(arabic(row['text']) for row in data['rows']):
            from yuzufile.unicode_overlay import normalize_arabic_fonts
            normalize_arabic_fonts(page)
        page.parent.xref_set_key(page.xref, 'PDFaiOCR', 'true')
    return added
