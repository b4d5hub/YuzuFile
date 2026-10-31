"""CPU line recognition for Arabic print, using pinned Kraken ONNX weights.

The SquiddleOCR conversion folds Kraken's preprocessing into the graph. Input
is RGB, 96 pixels high, normalized to [-1, 1]; output is CTC probabilities.
Only local files are used. One line is processed at a time, not a book batch.
"""
import math
import unicodedata

from yuzufile.neural_text import arabic, model_root, overlap

ENGINE = 'Kraken PP-OCRv6 medium / SquiddleOCR ONNX / CPU'
REQUIRED = ('inference.onnx', 'dict.txt', 'LICENSE', 'NOTICE', 'ready.json')


def available():
    root = model_root() / 'arabic-print'
    return all((root / name).is_file() for name in REQUIRED)


def decode_ctc(probabilities, characters):
    """Collapse CTC repetitions/blanks before bidirectional reordering."""
    import numpy as np
    from bidi.algorithm import get_display
    indices = probabilities.argmax(axis=1)
    keep = (indices != 0) & np.concatenate(([True], indices[1:] != indices[:-1]))
    text = ''.join(characters[int(index)] for index in indices[keep])
    if arabic(text):
        # The network reads physical left-to-right image order. Latin URLs and
        # numbers must stay intact inside the logical Arabic sentence.
        text = get_display(text, base_dir='R')
    text = unicodedata.normalize('NFC', text).strip()
    score = float(probabilities.max(axis=1)[keep].mean()) if keep.any() else 0.
    return text, score if math.isfinite(score) else 0.


class Reader:
    def __init__(self, threads):
        if not available():
            raise RuntimeError('The complete offline Arabic print recognizer is unavailable.')
        import onnxruntime as ort
        from yuzufile.neural_text import RapidReader
        self.threads = max(1, min(4, int(threads)))
        options = ort.SessionOptions()
        options.intra_op_num_threads = self.threads
        options.inter_op_num_threads = 1
        # Reuse the bounded line buffers during this page. The helper exits
        # after the page, releasing its arena before the next page is rendered.
        options.enable_cpu_mem_arena = True
        options.enable_mem_pattern = True
        options.log_severity_level = 4
        root = model_root() / 'arabic-print'
        self.session = ort.InferenceSession(str(root / 'inference.onnx'), options,
                                            providers=['CPUExecutionProvider'])
        self.input_name = self.session.get_inputs()[0].name
        self.characters = [''] + (root / 'dict.txt').read_text(encoding='utf-8').splitlines()
        # Use only RapidOCR's local detector. Its Arabic recognizer is not
        # loaded; detection must not discard lines based on its poor readings.
        self.detector = RapidReader(['ara'], self.threads).models[0][1]

    def read_line(self, image, box):
        import numpy as np
        from PIL import Image
        with image.crop(box) as crop:
            width = max(16, min(3200, round(crop.width * 96 / crop.height)))
            with crop.resize((width, 96), Image.Resampling.BICUBIC) as line:
                tensor = (np.asarray(line).astype(np.float32) / 127.5 - 1).transpose(2, 0, 1)[None]
        probabilities = self.session.run(None, {self.input_name: tensor})[0][0]
        return decode_ctc(probabilities, self.characters)

    def refine(self, path, original):
        import numpy as np
        from PIL import Image
        with Image.open(path) as opened:
            image = opened.convert('RGB').rotate(original.get('rotation', 0), expand=True)
        try:
            # RapidOCR's ndarray contract is BGR; the recognizer below is RGB.
            output = self.detector(np.asarray(image)[:, :, ::-1].copy(), use_rec=False, use_cls=False)
            boxes = output.boxes
            if boxes is None:
                return original
            rows = []
            for polygon in boxes:
                x0 = max(0, math.floor(float(polygon[:, 0].min())) - 2)
                y0 = max(0, math.floor(float(polygon[:, 1].min())) - 2)
                x1 = min(image.width, math.ceil(float(polygon[:, 0].max())) + 2)
                y1 = min(image.height, math.ceil(float(polygon[:, 1].max())) + 2)
                if x1 <= x0 or y1 <= y0:
                    continue
                box = [x0, y0, x1, y1]
                text, score = self.read_line(image, box)
                # Tall detector boxes can include vowel marks from adjacent
                # lines. Retry only uncertain, overlapping lines, at most twice.
                touching = any(abs(float(other[:, 1].mean()) - (y0+y1)/2) > (y1-y0)*.45 and
                    min(y1,float(other[:, 1].max())) > max(y0,float(other[:, 1].min())) and
                    min(x1,float(other[:, 0].max())) - max(x0,float(other[:, 0].min())) > (x1-x0)*.5
                    for other in boxes if other is not polygon)
                if score < .8 and x1-x0 > (y1-y0)*2 and touching:
                    for top, bottom in ((.10,.10),(.15,.10)):
                        candidate, confidence = self.read_line(image,
                            (x0,y0+round((y1-y0)*top),x1,y1-round((y1-y0)*bottom)))
                        if candidate and confidence > score + .025:
                            text, score = candidate, confidence
                if not arabic(text):
                    # Leave established English/French readings on their
                    # original engine; confidence scales cannot be compared.
                    previous = next((r for r in original['rows'] if
                        overlap(box, r['box']) >= .65 and not arabic(r['text'])), None)
                    if previous and (text or len(previous['text']) > 1):
                        text, score = previous['text'], previous['score']
                if text:
                    rows.append(dict(box=box, text=text, score=score))
            if not any(arabic(row['text']) for row in rows):
                return original
            # Retain separate detected Latin labels the second detector missed.
            rows.extend(row for row in original['rows'] if not arabic(row['text']) and
                        (len(row['text']) > 1 or row['text'].isdecimal()) and
                        row['score'] >= .9 and not any(overlap(row['box'], r['box']) >= .3 for r in rows))
            rows.sort(key=lambda r: (round(r['box'][1] / 12), -r['box'][0]))
            warnings = []
            vowel_marks = sum(unicodedata.category(c) == 'Mn' and 'ARABIC' in unicodedata.name(c, '')
                              for row in rows for c in row['text'])
            if vowel_marks >= 20:
                warnings.append('Vowel-marked Arabic requires review: OCR can misread letters and vowel marks even on high-confidence lines.')
            elif any(len(r['text']) > 12 and r['score'] < .8 for r in rows):
                warnings.append('Arabic print recognition contains uncertain text. Check spelling, vowel marks and numbers against the page.')
            blocks = [dict(block) for block in original.get('blocks', [])]
            for block in blocks:
                if block.get('label') == 'Table':
                    continue  # Keep structure for the separate table verifier.
                bx0,by0,bx1,by1 = block['bbox']
                contents = [r['text'] for r in rows if
                    bx0 <= (r['box'][0]+r['box'][2])/2 <= bx1 and
                    by0 <= (r['box'][1]+r['box'][3])/2 <= by1]
                block['text'] = '\n'.join(contents)
            return dict(original, rows=rows, markdown='\n\n'.join(row['text'] for row in rows),
                        blocks=blocks,
                        engine=original['engine'] + ' + ' + ENGINE,
                        recognizer_engine=ENGINE, quality_warnings=warnings)
        finally:
            image.close()
