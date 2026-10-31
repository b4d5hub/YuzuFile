"""Editable, local PDF to DOCX reconstruction, with per-page coverage checks.

PDF coordinates are evidence, not Word semantics. Keep uncertain content as
editable paragraphs instead of guessing a table, and disclose layout limits.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from html.parser import HTMLParser
from io import BytesIO
import json
import math
import re
import subprocess
import unicodedata
from zipfile import ZipFile

import pymupdf
from docx import Document
from docx.enum.section import WD_SECTION_START
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_TABLE_DIRECTION
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

from yuzufile.resources import page_indices
from yuzufile.word_rtl import arabic,base_rtl,directional_parts,native_blocks,cell_text
from yuzufile.word_mapping import mapping_probe,confirmed_arabic,visible_coverage


def clean(text):
    return ''.join(c for c in unicodedata.normalize('NFKC', str(text))
                   if c in '\n\t' or ord(c) >= 32 and not 0xD800 <= ord(c) <= 0xDFFF
                   and ord(c) not in (0xFFFE, 0xFFFF))


def tokens(text):
    # PDF extractors disagree about spaces inside shaped RTL glyph runs. Compare
    # their letters independently so spacing differences do not duplicate lines.
    normalized=''.join(' '+c+' ' if unicodedata.bidirectional(c) in ('R','AL') else c
                       for c in clean(text).casefold())
    return Counter(re.findall(r'\w+', normalized))


def coverage(source, output):
    expected, actual = tokens(source), tokens(output)
    return sum((expected & actual).values()) / max(1, sum(expected.values()))


@dataclass
class Cell:
    text: str
    row: int
    col: int
    rows: int = 1
    cols: int = 1


@dataclass
class Table:
    box: tuple
    cells: list[Cell]
    rows: int
    cols: int
    engine: str
    widths: list[float] = field(default_factory=list)

    @property
    def text(self):
        return '\n'.join(c.text for c in self.cells)


class HTMLTables(HTMLParser):
    """Read model-produced HTML without executing it or fetching resources."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self.cells, self.current = [], None, None
        self.row, self.col, self.occupied = -1, 0, set()

    def handle_starttag(self, tag, attrs):
        if tag == 'table' and self.cells is None:
            self.cells, self.row, self.occupied = [], -1, set()
        elif tag == 'tr' and self.cells is not None:
            self.row += 1
            self.col = 0
        elif tag in ('td', 'th') and self.cells is not None and self.row >= 0:
            while (self.row, self.col) in self.occupied:
                self.col += 1
            attributes = dict(attrs)
            try:
                rs, cs = (max(1, min(100, int(attributes.get(k, 1)))) for k in ('rowspan', 'colspan'))
            except (TypeError, ValueError):
                rs, cs = 1, 1
            if self.row + rs <= 500 and self.col + cs <= 50:
                self.current = Cell('', self.row, self.col, rs, cs)
        elif tag == 'br' and self.current:
            self.current.text += '\n'

    def handle_data(self, data):
        if self.current:
            self.current.text += data

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.current:
            c = self.current
            self.cells.append(c)
            self.occupied.update((r, col) for r in range(c.row, c.row+c.rows)
                                 for col in range(c.col, c.col+c.cols))
            self.col += c.cols
            self.current = None
        elif tag == 'table' and self.cells is not None:
            if self.cells:
                self.tables.append(self.cells)
            self.cells, self.current = None, None


def _native_tables(page, warnings,data=None):
    candidates = []
    for strategy in (('lines',) if data and data.get('detailed_ocr') else ('lines', 'text')):
        # Borderless detection is a fallback, not a second copy of a ruled table.
        if candidates:
            break
        try:
            found = page.find_tables(strategy=strategy).tables
            for table in found:
                matrix = table.extract()
                rows, cols = len(matrix), max(map(len, matrix), default=0)
                nonempty = sum(bool(c and c.strip()) for row in matrix for c in row)
                if not 2 <= cols <= 50 or not 2 <= rows <= 500:
                    continue
                if strategy == 'text' and (rows < 3 or nonempty < rows*cols*.65):
                    continue
                if strategy == 'text':
                    values=[str(v) for row in matrix for v in row if v]
                    average=sum(map(len,values))/max(1,len(values))
                    if average > 80 or average > 30 and not any(re.search(r'\d',v) for v in values):
                        continue
                box = tuple(table.bbox)
                cells = [Cell(clean(value or ''), r, c) for r, row in enumerate(matrix)
                         for c, value in enumerate(row) if value is not None]
                for cell in cells:
                    rect=table.rows[cell.row].cells[cell.col]
                    if rect and data and data.get('logical_ocr'):
                        cell.text=clean(_ocr_text_in(page,pymupdf.Rect(rect),data))
                    elif rect and arabic(cell.text):
                        recovered=cell_text(page,rect)
                        if '\ufffd' in recovered and data:
                            recovered=_ocr_text_in(page,pymupdf.Rect(rect),data) or recovered
                        if recovered:cell.text=clean(recovered)
                # Geometry identifies real spans; empty cells alone do not.
                edges = sorted({round(v, 2) for rect in table.cells if rect for v in (rect[0], rect[2])})
                row_edges = sorted({round(v, 2) for rect in table.cells if rect for v in (rect[1],rect[3])})
                widths = [b-a for a, b in zip(edges, edges[1:])]
                if len(widths) == cols:
                    for cell in cells:
                        rect = table.rows[cell.row].cells[cell.col]
                        if rect:
                            cell.cols = max(1, sum(rect[0]-.1 <= x < rect[2]-.1 for x in edges[:-1]))
                            cell.cols = min(cell.cols, cols-cell.col)
                            if len(row_edges)==rows+1:
                                cell.rows = min(rows-cell.row,max(1,sum(rect[1]-.1 <= y < rect[3]-.1 for y in row_edges[:-1])))
                candidates.append(Table(box, cells, rows, cols, 'pymupdf-'+strategy, widths))
        except (ValueError, RuntimeError, IndexError, TypeError):
            warnings.append('Table detection could not finish; retained editable text.')
    return candidates


def _model_tables(data, page):
    if not data:
        return []
    sx, sy = page.rect.width/data['width'], page.rect.height/data['height']
    table_blocks = [b for b in data.get('blocks', []) if b.get('label') == 'Table']
    parser = HTMLTables()
    parser.feed(data.get('markdown', ''))
    candidates = []
    for i, block in enumerate(table_blocks):
        local = HTMLTables()
        local.feed(block.get('text', ''))
        cells = local.tables[0] if local.tables else parser.tables[i] if i < len(parser.tables) else []
        if not cells:
            continue
        x0, y0, x1, y1 = block['bbox']
        rows, cols = max(c.row+c.rows for c in cells), max(c.col+c.cols for c in cells)
        candidates.append(Table((x0*sx,y0*sy,x1*sx,y1*sy), cells, rows, cols, 'indra-html'))
    return candidates


def _text_in(page, box):
    return '\n'.join(w[4] for w in page.get_text('words')
                     if box.contains(pymupdf.Point((w[0]+w[2])/2, (w[1]+w[3])/2)))


def _ocr_text_in(page,box,data):
    sx,sy=page.rect.width/data['width'],page.rect.height/data['height']
    return '\n'.join(r['text'] for r in data.get('rows',[]) if box.contains(pymupdf.Point((r['box'][0]+r['box'][2])*sx/2,(r['box'][1]+r['box'][3])*sy/2)))


def _repair_native_lines(page,source_dict,data):
    """A damaged diacritic must not replace the rest of a native PDF with OCR."""
    if not data or not data.get('rows'):return
    sx,sy=page.rect.width/data['width'],page.rect.height/data['height']
    for block in source_dict['blocks']:
        for line in block.get('lines',[]):
            if not any('\ufffd' in s['text'] for s in line['spans']):continue
            box=pymupdf.Rect(line['bbox'])
            matches=[]
            for row in data['rows']:
                r=pymupdf.Rect(row['box'][0]*sx,row['box'][1]*sy,row['box'][2]*sx,row['box'][3]*sy)
                overlap=(box&r).get_area()/max(1,min(box.get_area(),r.get_area()))
                if overlap>.55:matches.append((overlap,row))
            if matches:
                row=max(matches,key=lambda item:item[0])[1]
                words=clean(row['text']).split()
                updates=[]
                for span in line['spans']:
                    def replace_word(match):
                        pattern=re.escape(clean(match[0])).replace('\ufffd','.{1,4}')
                        candidates={w for w in words if re.fullmatch(pattern,w)}
                        return next(iter(candidates)) if len(candidates)==1 else match[0]
                    updates.append(re.sub(r'\S*\ufffd\S*',replace_word,span['text']))
                if not any('\ufffd' in text for text in updates):
                    for span,text in zip(line['spans'],updates):span['text']=text
                    continue
                style=max(line['spans'],key=lambda s:len(s['text']))
                line['spans']=[{**style,'text':row['text']}]


def _grid_tables(page,data=None):
    """Recover ruled scanned tables using lines, filling cells from OCR words."""
    import cv2
    import numpy as np
    scale = min(2, math.sqrt(4_000_000/max(1,page.rect.get_area())))
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),colorspace=pymupdf.csGRAY,alpha=False,annots=False)
    gray = np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width)
    binary = cv2.threshold(gray,0,255,cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    horizontal = cv2.morphologyEx(binary,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(max(25,pix.width//25),1)))
    vertical = cv2.morphologyEx(binary,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(1,max(25,pix.height//25))))
    joined = cv2.bitwise_or(horizontal,vertical)
    contours = cv2.findContours(joined,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]
    candidates = []
    def centers(values):
        groups = []
        for value in values:
            if not groups or value > groups[-1][-1]+2:
                groups.append([])
            groups[-1].append(value)
        return [sum(g)/len(g) for g in groups]
    words = page.get_text('words')
    if data and data.get('logical_ocr'):
        sx,sy=page.rect.width/data['width'],page.rect.height/data['height']
        words=[(r['box'][0]*sx,r['box'][1]*sy,r['box'][2]*sx,r['box'][3]*sy,r['text'],i,0,0)
               for i,r in enumerate(data['rows'])]
    for contour in contours:
        x,y,w,h = cv2.boundingRect(contour)
        if w < 80*scale or h < 35*scale:
            continue
        xs = centers(np.flatnonzero(np.count_nonzero(vertical[y:y+h,x:x+w],axis=0) > h*.8))
        ys = centers(np.flatnonzero(np.count_nonzero(horizontal[y:y+h,x:x+w],axis=1) > w*.8))
        rows,cols = len(ys)-1,len(xs)-1
        if not 2 <= rows <= 500 or not 2 <= cols <= 50 or rows*cols > 5000:
            continue
        xs,ys = [(x+v)/scale for v in xs],[(y+v)/scale for v in ys]
        cells=[]
        for r in range(rows):
            for c in range(cols):
                content = [word for word in words if xs[c] <= (word[0]+word[2])/2 < xs[c+1]
                           and ys[r] <= (word[1]+word[3])/2 < ys[r+1]]
                content.sort(key=lambda v:(v[5],v[6],v[7]))
                text=' '.join(v[4] for v in content)
                cells.append(Cell(text,r,c))
        if sum(bool(c.text) for c in cells) >= rows*cols*.4:
            candidates.append(Table((xs[0],ys[0],xs[-1],ys[-1]),cells,rows,cols,'opencv-grid+ocr',[b-a for a,b in zip(xs,xs[1:])]))
    return candidates


def _choose_tables(page, data, warnings, extra=()):
    chosen = []
    candidates = _native_tables(page, warnings,data) + _model_tables(data, page) + list(extra)
    if any(pymupdf.Rect(i['bbox']).get_area() > page.rect.get_area()*.7 for i in page.get_image_info()):
        candidates += _grid_tables(page,data)
    # Prefer the candidate which preserves the source text and numbers. Model
    # output can improve structure, but never silently replace native wording.
    scored = []
    for candidate in candidates:
        region = pymupdf.Rect(candidate.box) & page.rect
        if data and data.get('logical_ocr'):
            source=_ocr_text_in(page,region,data)
        else:source = _text_in(page, region)
        score = coverage(source, candidate.text)
        numbers = Counter(re.findall(r'\d+(?:[.,]\d+)*', source))
        present = Counter(re.findall(r'\d+(?:[.,]\d+)*', candidate.text))
        if score >= .95 and not numbers-present and candidate.cells and candidate.rows*candidate.cols <= 5000:
            scored.append((score, candidate))
        else:
            warnings.append('An uncertain table was kept as editable text instead of guessing its cells.')
    for _, candidate in sorted(scored, key=lambda pair: (pair[0],pair[1].engine in ('pymupdf-lines','opencv-grid+ocr')), reverse=True):
        rect = pymupdf.Rect(candidate.box)
        if not any((rect & pymupdf.Rect(t.box)).get_area() > .3*min(rect.get_area(), pymupdf.Rect(t.box).get_area()) for t in chosen):
            chosen.append(candidate)
    return chosen


def _verify_uncertain_tables(page, data, tables, scratch, performance, warnings, engines):
    if not data:
        return tables
    unresolved = []
    for block in data.get('blocks',[]):
        if block.get('label') != 'Table':
            continue
        x0,y0,x1,y1=block['bbox']
        box=pymupdf.Rect(x0*page.rect.width/data['width'],y0*page.rect.height/data['height'],
                         x1*page.rect.width/data['width'],y1*page.rect.height/data['height']) & page.rect
        if box.is_empty or any((box & pymupdf.Rect(t.box)).get_area() > .6*box.get_area() for t in tables):
            continue
        unresolved.append(box)
    if not unresolved:
        return tables
    from yuzufile.neural_markdown import optional_runtime
    with optional_runtime('paddle',scratch,performance.page_workers(),warnings,engines) as runtime:
        if runtime is None:
            return tables
        for box in unresolved:
            crop=scratch/'word-table.png'
            try:
                scale=min(3,2048/max(box.width,box.height))
                pix=page.get_pixmap(clip=box,matrix=pymupdf.Matrix(scale,scale),alpha=False,annots=False)
                pix.save(crop)
                del pix
                parser=HTMLTables()
                parser.feed(runtime.recognize(crop,'Table Recognition:'))
                alternatives=[Table(tuple(box),cells,max(c.row+c.rows for c in cells),
                                    max(c.col+c.cols for c in cells),'paddle-html') for cells in parser.tables]
                accepted=_choose_tables(page,None,warnings,alternatives)
                for candidate in accepted:
                    if not any((pymupdf.Rect(candidate.box)&pymupdf.Rect(t.box)).get_area() > .3*pymupdf.Rect(candidate.box).get_area() for t in tables):
                        tables.append(candidate)
            except (OSError,RuntimeError,ValueError,KeyError,TypeError) as error:
                warnings.append(f'Table verification was unavailable ({type(error).__name__}); retained editable text.')
            finally:
                crop.unlink(missing_ok=True)
    return tables


def _rtl(text):
    return sum(unicodedata.bidirectional(c) in ('R','AL') for c in text) > sum(c.isalpha() and unicodedata.bidirectional(c)=='L' for c in text)


def _reading_order(elements, width):
    """Read clear two-column bands together, respecting spanning headings."""
    middle=width/2
    ordered=sorted(elements,key=lambda e:(round(e[0][1]/4),e[0][0]))
    result,band,changed=[],[],False
    def flush():
        nonlocal changed
        left=[e for e in band if e[0][2] <= middle-6]
        right=[e for e in band if e[0][0] >= middle+6]
        if left and right and len(left)+len(right)==len(band):
            overlap=min(max(e[0][3] for e in left),max(e[0][3] for e in right))-max(min(e[0][1] for e in left),min(e[0][1] for e in right))
            if overlap > 40:
                rtl=_rtl(' '.join(''.join(s['text'] for s in e[2]) for e in band if e[1]=='text'))
                result.extend((right+left) if rtl else (left+right))
                changed=True
                return
        result.extend(band)
    for item in ordered:
        if item[0][0] < middle-6 and item[0][2] > middle+6:
            flush()
            band=[]
            result.append(item)
        else:
            band.append(item)
    flush()
    return result,changed


def _paragraph(parent, spans, box=None, left=36, width=523,rtl_context=False):
    p = parent.add_paragraph()
    text = ''.join(s['text'] for s in spans)
    fmt = p.paragraph_format
    fmt.space_after, fmt.space_before = Pt(3), Pt(0)
    fmt.line_spacing = 1.0
    if box:
        fmt.left_indent = Pt(max(0, min(width*.65, box[0]-left)))
    if base_rtl(text,rtl_context):
        bidi = OxmlElement('w:bidi')
        p._p.get_or_add_pPr().append(bidi)
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p._p.get_or_add_pPr().find(qn('w:jc')).set(qn('w:val'),'start')
        if box:
            fmt.left_indent = Pt(0)
            fmt.right_indent = Pt(max(0,min(width*.65,left+width-box[2])))
    for span in spans:
        for part,rtl in directional_parts(clean(span['text'])):
            run = p.add_run(part)
            font = span.get('font', '')
            # PDF subset names are not usable installed font names.
            family = re.sub(r'^[A-Z]{6}\+', '', font).split(',')[0]
            if not family or any(k in family.lower() for k in ('glyphless','tesseract','yuzufile','ocr')):
                family = 'Arial'
            run.font.name = family
            run.font.size = Pt(max(7, min(72, span.get('size', 11))))
            run.bold = bool(span.get('flags', 0) & 16)
            run.italic = bool(span.get('flags', 0) & 2)
            if rtl:
                run.font.cs_bold=run.bold
                run.font.cs_italic=run.italic
            color = max(0, min(0xFFFFFF, int(span.get('color', 0))))
            # Word has a white page; white PDF text may have sat on a dark panel.
            if min((color>>16)&255,(color>>8)&255,color&255) > 210:
                color = 0
            run.font.color.rgb = RGBColor.from_string(f'{color:06X}')
            props = run._r.get_or_add_rPr()
            fonts = props.find(qn('w:rFonts'))
            fonts.set(qn('w:cs'), 'Arial')
            rtl_node=OxmlElement('w:rtl');rtl_node.set(qn('w:val'),'1' if rtl else '0');props.append(rtl_node)
            if rtl:
                language=OxmlElement('w:lang');language.set(qn('w:bidi'),'ar-SA');props.append(language)
                fonts.set(qn('w:hint'),'cs')
                size = OxmlElement('w:szCs')
                size.set(qn('w:val'), str(round(max(7,min(72,span.get('size',11)))*2)))
                props.append(size)
    return p


def _write_table(document, candidate, usable, indent=0, right_indent=0):
    table = document.add_table(rows=candidate.rows, cols=candidate.cols)
    table.style = 'Table Grid'
    table.autofit = False
    widths = candidate.widths if len(candidate.widths)==candidate.cols else [1]*candidate.cols
    rtl=_rtl(candidate.text)
    if rtl:
        table.table_direction=WD_TABLE_DIRECTION.RTL
        table.alignment=WD_TABLE_ALIGNMENT.RIGHT
        widths=widths[::-1]
    total = sum(widths)
    for col, width in zip(table.columns, widths):
        col.width = Pt(usable*width/total)
    for row in table.rows:
        for cell,width in zip(row.cells,widths):
            cell.width=Pt(usable*width/total)
    position=OxmlElement('w:tblInd')
    position.set(qn('w:w'),str(round(max(0,right_indent if rtl else indent)*20)))
    position.set(qn('w:type'),'dxa')
    table._tbl.tblPr.append(position)
    for cell in candidate.cells:
        col=candidate.cols-cell.col-cell.cols if rtl else cell.col
        target = table.cell(cell.row, col)
        if cell.rows > 1 or cell.cols > 1:
            target = target.merge(table.cell(cell.row+cell.rows-1, col+cell.cols-1))
        target.text = ''
        # Keep Word's mandatory cell paragraph, removing the empty placeholder.
        placeholder = target.paragraphs[0]._p
        _paragraph(target, [dict(text=cell.text, size=10)],rtl_context=rtl)
        placeholder.getparent().remove(placeholder)
    # Rows may flow across pages; never force an overlarge row off the page.
    return table


def _scan_figures(page,tables):
    """Retain unlabelled scan illustrations after masking recognized text/grid."""
    import cv2
    import numpy as np
    scale=min(2,math.sqrt(3_000_000/max(1,page.rect.get_area())))
    pix=page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),colorspace=pymupdf.csGRAY,alpha=False,annots=False)
    gray=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width)
    binary=cv2.threshold(gray,242,255,cv2.THRESH_BINARY_INV)[1]
    for rect in [pymupdf.Rect(w[:4])+(-2,-2,2,2) for w in page.get_text('words')]+[pymupdf.Rect(t.box)+(-3,-3,3,3) for t in tables]:
        rect=rect & page.rect
        if not rect.is_empty:
            cv2.rectangle(binary,(max(0,int(rect.x0*scale)),max(0,int(rect.y0*scale))),
                          (min(pix.width-1,math.ceil(rect.x1*scale)),min(pix.height-1,math.ceil(rect.y1*scale))),0,-1)
    binary=cv2.morphologyEx(binary,cv2.MORPH_CLOSE,np.ones((5,5),dtype=np.uint8))
    contours=cv2.findContours(binary,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]
    boxes=[]
    for contour in contours:
        x,y,w,h=cv2.boundingRect(contour)
        if w/scale > 30 and h/scale > 25 and w*h < pix.width*pix.height*.7:
            boxes.append(pymupdf.Rect(x/scale,y/scale,(x+w)/scale,(y+h)/scale))
    return boxes


def _figures(page, data, tables=()):
    boxes = []
    if data:
        sx, sy = page.rect.width/data['width'], page.rect.height/data['height']
        boxes += [pymupdf.Rect(b['bbox'][0]*sx,b['bbox'][1]*sy,b['bbox'][2]*sx,b['bbox'][3]*sy)
                  for b in data.get('blocks', []) if b.get('label') == 'Picture']
    for info in page.get_image_info():
        rect = pymupdf.Rect(info['bbox']) & page.rect
        if 16 < rect.get_area() < page.rect.get_area()*.7:
            boxes.append(rect)
    if any(pymupdf.Rect(i['bbox']).get_area() > page.rect.get_area()*.7 for i in page.get_image_info()):
        boxes += _scan_figures(page,tables)
    # Vector illustrations are not embedded images. Cluster their drawing paths.
    for rect in page.cluster_drawings():
        rect = pymupdf.Rect(rect) & page.rect
        if rect.width > 30 and rect.height > 30 and rect.get_area() < page.rect.get_area()*.7:
            boxes.append(rect)
    unique = []
    for rect in sorted(boxes, key=lambda r:r.get_area(), reverse=True):
        if rect.is_empty or any((rect & previous).get_area() >= rect.get_area()*.85 for previous in unique):
            continue
        unique.append(rect)
    return unique


def _arabic_ocr_rows(page,data,scratch,performance,warnings,engines):
    """Retain logical OCR strings; selectively recover uncertain numeric rows."""
    if not data or not any(arabic(r['text']) for r in data.get('rows',[])):return data
    data={**data,'rows':[dict(r) for r in data['rows']],'logical_ocr':True}
    if not any(r.get('score',1)<.7 for r in data['rows']):return data
    from yuzufile import neural_text
    if not neural_text.available():return data
    image=scratch/'word-arabic-check.png';result=None
    try:
        scale=min(220/72,math.sqrt(8_000_000/max(1,page.rect.get_area())))
        pix=page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),alpha=False,annots=False);pix.save(image);del pix
        result=neural_text.recognize(image,['ara'])
        extra=json.loads(result.read_text(encoding='utf-8'))
        used=False
        for row in extra['rows']:
            text=clean(row['text']).strip()
            # Never replace a mixed sentence with a recognizer that missed its
            # Latin words. Only standalone numeric cells are eligible here.
            if not any(c.isdecimal() and ord(c)>127 for c in text) or any(c.isalpha() for c in text) or row['score']<.45:continue
            x0,y0,x1,y1=row['box'];box=[x0*data['width']/extra['width'],y0*data['height']/extra['height'],x1*data['width']/extra['width'],y1*data['height']/extra['height']]
            match=next((i for i,r in enumerate(data['rows']) if neural_text.overlap(box,r['box'])>=.65),None)
            candidate=dict(row,text=text,box=box)
            if match is None:data['rows'].append(candidate);used=True
            elif data['rows'][match].get('score',1)<.7 and not any(c.isalpha() for c in data['rows'][match]['text']):
                data['rows'][match]=candidate;used=True
        engines.add('rapidocr-arabic-verification')
        if used:warnings.append('Additional Arabic numeric cells were recovered with a second OCR engine; review numbers against the PDF.')
        data['rows'].sort(key=lambda r:(round(r['box'][1]/8),-r['box'][0]))
    except (OSError,RuntimeError,ValueError,KeyError,MemoryError,subprocess.TimeoutExpired) as error:
        warnings.append(f'Arabic numeric verification unavailable ({type(error).__name__}); retained existing OCR text.')
    finally:
        image.unlink(missing_ok=True)
        if result:result.unlink(missing_ok=True)
    return data


def _detailed_recovery(page,data,scratch,performance,notify,index):
    from yuzufile.word_detailed_ocr import recover
    try:return recover(page,data,scratch,performance,notify)
    except (OSError,RuntimeError,ValueError,KeyError,TypeError,subprocess.TimeoutExpired) as error:
        raise RuntimeError(f'Word page {index+1}: detailed Arabic OCR could not finish. Try High performance or smaller page crops; no incomplete Word file was exported.') from error


def _vector_art_page(page,text):
    if sum(c.isalpha() for c in text)>=40:return False
    if any(s.get('type')!=3 and s.get('opacity',1)>.01 for s in page.get_texttrace()):return False
    return len(page.get_drawings())>=25


def _in_figure(box,figures):
    box=pymupdf.Rect(box);center=pymupdf.Point((box.x0+box.x1)/2,(box.y0+box.y1)/2)
    return any(r.contains(center) for r in figures)


def _editable_text_panel(rect,page,data):
    """A framed callout with dense OCR text is text, not a page illustration."""
    sx,sy=page.rect.width/data['width'],page.rect.height/data['height']
    rows=[];covered=0
    for row in data.get('rows',[]):
        box=pymupdf.Rect(row['box'][0]*sx,row['box'][1]*sy,row['box'][2]*sx,row['box'][3]*sy)
        if not rect.contains(pymupdf.Point((box.x0+box.x1)/2,(box.y0+box.y1)/2)):continue
        overlap=(box&rect).get_area()
        if overlap<box.get_area()*.6:continue
        rows.append(row);covered+=overlap
    letters=sum(c.isalpha() for row in rows for c in row['text'])
    return len(rows)>=3 and letters>=60 and covered/max(1,rect.get_area())>=.35


def _fresh_page_ocr(page,scratch,index):
    """Use this run's logical OCR, never the input PDF's embedded text layer."""
    if page.parent.xref_get_key(page.xref,'PDFaiFreshOCR')[1]!='true':
        raise RuntimeError(f'Word page {index+1}: fresh page OCR is required before Word reconstruction.')
    cache=scratch/f'fresh-ocr-page-{index+1}.json'
    if cache.is_file():
        data=json.loads(cache.read_text(encoding='utf-8'))
        if not isinstance(data,dict) or data.get('fresh_ocr') is not True:
            raise RuntimeError(f'Word page {index+1}: the OCR cache is not from the fresh-page recognition pass.')
        origin='fresh-ocr-cache'
    else:
        # Tesseract/searchable-PDF fallback is safe only with the fresh marker.
        # Preserve the new Unicode strings directly, without legacy glyph sorting
        # or another OCR call. The ordinary pipeline also caches these rows.
        rows=[]
        for block in page.get_text('dict',flags=0,sort=False)['blocks']:
            for line in block.get('lines',[]):
                text=clean(''.join(span['text'] for span in line['spans'])).strip()
                if text:rows.append(dict(box=list(line['bbox']),text=text,score=1.))
        data=dict(width=page.rect.width,height=page.rect.height,rows=rows,blocks=[],
                  rotation=0,fresh_ocr=True)
        origin='fresh-pdf-overlay'
    if (not isinstance(data,dict) or not isinstance(data.get('rows'),list)
            or any(not isinstance(data.get(key),(int,float)) or not math.isfinite(data[key]) or data[key]<=0
                   for key in ('width','height'))):
        raise RuntimeError(f'Word page {index+1}: fresh OCR coordinates are invalid.')
    if any(not isinstance(row,dict) or not isinstance(row.get('text'),str)
           or not isinstance(row.get('box'),(list,tuple)) or len(row['box'])!=4
           or any(not isinstance(value,(int,float)) or not math.isfinite(value) for value in row['box'])
           or row['box'][2]<row['box'][0] or row['box'][3]<row['box'][1] for row in data['rows']):
        raise RuntimeError(f'Word page {index+1}: fresh OCR rows are invalid.')
    data={**data,'logical_ocr':True}
    if data.get('source_rotation') in (90,270) and not data.get('rotation'):
        # The shared cache has already remapped sideways rows. Their short
        # horizontal edge, rather than their long vertical extent, is the font
        # height; otherwise a single sideways line becomes enormous in Word.
        data={**data,'remapped_rotation':data['source_rotation'],
              'rows':[{**r,'font_size':r.get('font_size',min(26,max(8,
                        (r['box'][2]-r['box'][0])*page.rect.width/data['width']*.75)))}
                      for r in data['rows']]}
    if data.get('rotation'):
        # An OCR model may report upright raster coordinates. Do not discard its
        # logical strings or re-run full-page OCR when remapping that layout.
        rotation=data['rotation']%360
        if rotation not in (90,180,270):
            raise RuntimeError(f'Word page {index+1}: unsupported fresh OCR orientation.')
        width,height=data['width'],data['height'];pw,ph=page.rect.width,page.rect.height
        def box(values):
            x0,y0,x1,y1=values;x0/=width;x1/=width;y0/=height;y1/=height
            if rotation==90:values=(1-y1,x0,1-y0,x1)
            elif rotation==180:values=(1-x1,1-y1,1-x0,1-y0)
            else:values=(y0,1-x1,y1,1-x0)
            return [values[0]*pw,values[1]*ph,values[2]*pw,values[3]*ph]
        data={**data,'width':pw,'height':ph,'rotation':0,
              'rows':[{**r,'box':box(r['box']),
                       'font_size':min(26,max(8,(r['box'][3]-r['box'][1])*(pw/height if rotation in (90,270) else ph/height)*.75))}
                      for r in data['rows']],
              'blocks':[{**b,'bbox':box(b['bbox'])} for b in data.get('blocks',[]) if 'bbox' in b]}
        data['remapped_rotation']=rotation
    return data,origin


def write_word(source, destination, notify, performance, languages=None, *, force_visual_ocr=False,
               prepare_page=None):
    """Build Word objects, recover omissions, then re-open and validate the ZIP.

    In fresh mode, the common pipeline has already cleaned and recognized every
    page. Reuse its logical rows and layout, with no original PDF text fallback
    or repeated full-page model call. An optional page preparer can clean and
    recognize the current page immediately before its Word objects are built,
    so the next page is not recognized early. Direct callers retain native mode.
    """
    document = Document()
    normal = document.styles['Normal']
    normal.font.name, normal.font.size = 'Arial', Pt(11)
    normal.paragraph_format.space_after = Pt(3)
    scratch = destination.parent / 'scratch'
    scratch.mkdir(exist_ok=True)
    report = {'version':1, 'source_pages':len(source), 'pages':[],
              'text_source':'fresh-visual-ocr' if force_visual_ocr else 'pdf-text-and-selective-ocr',
              'fresh_ocr_pages':len(source) if force_visual_ocr else 0,
              'page_processing':'sequential',
              'validation':'Extracted-text coverage and DOCX structure; not a visual or OCR accuracy guarantee.'}
    warnings, engines = [], {'pymupdf','python-docx'}
    source_texts = []
    for index in page_indices(len(source), performance):
        if prepare_page is not None:prepare_page(index)
        notify(f'Building editable Word · page {index+1} of {len(source)}',
               progress=round(65+27*index/len(source)))
        page = source[index]
        section = document.sections[0] if index==0 else document.add_section(WD_SECTION_START.NEW_PAGE)
        section.page_width, section.page_height = Pt(page.rect.width), Pt(page.rect.height)
        margin = min(36, page.rect.width*.08, page.rect.height*.08)
        section.left_margin = section.right_margin = section.top_margin = section.bottom_margin = Pt(margin)
        section.header_distance = section.footer_distance = Pt(0)
        usable = page.rect.width-2*margin
        page_warnings = []
        data = None;fresh_origin=None
        if force_visual_ocr:
            data,fresh_origin=_fresh_page_ocr(page,scratch,index)
            source_dict={'blocks':[]};source_plain='';damaged_mapping=False
            engines.add(fresh_origin)
            if data.get('engine','').startswith('Indra'):engines.add('indra-ocr-1.1.2')
            if data.get('remapped_rotation'):
                page_warnings.append('Rotated OCR coordinates were remapped to the source page; review Word reading order and spacing.')
        else:
            source_dict=native_blocks(page)
            extracted_plain=clean(page.get_text(sort=True))
            source_plain=clean('\n'.join(''.join(s['text'] for s in line['spans'])
                for b in source_dict['blocks'] for line in b.get('lines',[])))
            damaged_mapping='\ufffd' in extracted_plain or any('\ufffd' in s['text']
                for b in source_dict['blocks'] for line in b.get('lines',[]) for s in line['spans'])
        if not force_visual_ocr and _vector_art_page(page,source_plain):
            scale=min(3,math.sqrt(4_000_000/max(1,page.rect.get_area())))
            pix=page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),alpha=False,annots=False)
            p=document.add_paragraph();p.paragraph_format.space_after=Pt(0)
            p.alignment=WD_ALIGN_PARAGRAPH.CENTER
            width=min(usable,(page.rect.height-2*margin-24)*page.rect.width/page.rect.height)
            p.add_run().add_picture(BytesIO(pix.tobytes('png')),width=Pt(width));del pix
            warning='Decorative vector artwork was preserved as a replaceable page image; its sparse hidden OCR layer was not reused.'
            source_texts.append('');warnings.append(f'Word page {index+1}: {warning}')
            report['pages'].append(dict(page=index+1,tables=0,figures=1,legacy_arabic_recovered=False,
                legacy_visible_text_coverage=None,table_engines=[],recovered_lines=0,editable_text_coverage=0,
                image_only=True,warnings=[warning]))
            continue
        already_ocr=source.xref_get_key(page.xref,'PDFaiOCR')[1]=='true'
        cache = scratch / f'indra-page-{index+1}.json'
        probe=mapping_probe(page,source_dict,languages) if not force_visual_ocr and not (already_ocr and cache.is_file()) else dict(required=False,strong=False,fonts=set())
        if not force_visual_ocr and cache.is_file():
            data = json.loads(cache.read_text(encoding='utf-8'))
            engines.add('indra-ocr-1.1.2')
        elif not force_visual_ocr and (damaged_mapping or probe['required'] or any(pymupdf.Rect(i['bbox']).get_area() > page.rect.get_area()*.7 for i in page.get_image_info())):
            from yuzufile import indra_engine
            if indra_engine.available():
                raster=scratch/'word-layout.png'
                result=None
                try:
                    scale=min((360 if probe['required'] else 220)/72,math.sqrt(8_000_000/max(1,page.rect.get_area())))
                    pix=page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),alpha=False,annots=False)
                    pix.save(raster)
                    del pix
                    result=indra_engine.recognize(raster,languages or ['eng'],performance.page_workers())
                    data=json.loads(result.read_text(encoding='utf-8'))
                    engines.add('indra-ocr-1.1.2')
                except (OSError,RuntimeError,ValueError,KeyError,TypeError,subprocess.TimeoutExpired) as error:
                    page_warnings.append(f'OCR layout unavailable ({type(error).__name__}); reused extracted text and table lines.')
                finally:
                    raster.unlink(missing_ok=True)
                    if result:
                        result.unlink(missing_ok=True)
        if data and data.get('rotation'):
            # Cached boxes refer to the upright raster, not original PDF axes.
            # Keep text editable and avoid assigning incorrect cells/figures.
            if probe['strong'] or probe.get('type3') and 'ara' in (languages or []):
                raise RuntimeError(f'Word page {index+1}: an unreadable font map and rotated OCR prevent a reliable export. Rotate this page upright and retry.')
            page_warnings.append('Rotated scan layout requires review; kept source text without model table coordinates.')
            data=None
        fallback_required=probe['required'] and not confirmed_arabic(data) and (
            probe['strong'] or probe.get('type3') and ('ara' in (languages or []) or any(arabic(r['text']) for r in (data or {}).get('rows',[]))))
        if fallback_required:
            data=_detailed_recovery(page,data,scratch,performance,notify,index)
            engines.add('paddle-legacy-arabic-regions')
            page_warnings.append('Legacy font required detailed Arabic OCR. Review wording, vowel marks and numbers against the PDF.')
        reencoded=probe['required'] and confirmed_arabic(data)
        legacy_coverage=None
        if reencoded:
            legacy_coverage=visible_coverage(page,data)
            if legacy_coverage<.65:
                data=_detailed_recovery(page,data,scratch,performance,notify,index)
                legacy_coverage=visible_coverage(page,data)
                if legacy_coverage<.65:
                    raise RuntimeError(f'Word page {index+1}: visual OCR recovered too little of the legacy-encoded page. No incomplete Word document was exported.')
                engines.add('paddle-legacy-arabic-regions')
                page_warnings.append('Dense Arabic required detailed OCR in sections. Review wording, vowel marks and numbers against the PDF.')
        if probe['strong'] and not reencoded:
            raise RuntimeError(f'Word page {index+1}: Arabic glyphs have an unreadable text map and OCR could not recover reliable Arabic. No garbled Word file was exported.')
        if reencoded:
            data={**data,'logical_ocr':True}
            page_warnings.append('Legacy Arabic font encoding was replaced with visually recognized text. Review OCR spelling and numbers.')
        elif probe['required']:
            page_warnings.append('Checked the page for a legacy Arabic font; retained native text because Arabic OCR was not confirmed.')
        if not force_visual_ocr and data and source.xref_get_key(page.xref,'PDFaiOCR')[1]=='true':
            data=_arabic_ocr_rows(page,data,scratch,performance,page_warnings,engines)
        if damaged_mapping:
            page_warnings.append('PDF character mappings are damaged; OCR text was used where available. Review spelling and numbers.')
            if data and not data.get('logical_ocr'):
                _repair_native_lines(page,source_dict,data)
                source_plain=clean('\n'.join(''.join(s['text'] for s in line['spans'])
                    for b in source_dict['blocks'] for line in b.get('lines',[])))
        repair_mapping=data and data.get('logical_ocr') and bool(data.get('rows'))
        tables = [] if repair_mapping and not data.get('logical_ocr') else _choose_tables(page, data, page_warnings)
        if not repair_mapping and not force_visual_ocr:
            tables = _verify_uncertain_tables(page,data,tables,scratch,performance,page_warnings,engines)
        figures = [r for r in _figures(page, data, tables) if not any((r & pymupdf.Rect(t.box)).get_area() > .5*r.get_area() for t in tables)]
        if force_visual_ocr:
            # A whole-page Picture classification must not swallow all freshly
            # recognized text on scanned slides or illustrated documents.
            figures=[r for r in figures if r.get_area()<page.rect.get_area()*.7]
            editable_panels=[r for r in figures if _editable_text_panel(r,page,data)]
            if editable_panels:
                figures=[r for r in figures if r not in editable_panels]
                page_warnings.append('A text-heavy framed region was kept editable; its border may need adjustment.')
        if figures:
            page_warnings.append('Text inside figures stays in the replaceable images.')
            if not repair_mapping:
                source_plain=clean('\n'.join(''.join(s['text'] for s in line['spans'])
                    for b in source_dict['blocks'] for line in b.get('lines',[]) if not _in_figure(line['bbox'],figures)))
        elements = [(t.box, 'table', t) for t in tables] + [(tuple(r), 'figure', r) for r in figures]
        if repair_mapping:
            source_dict={'blocks':[]}
            source_plain='\n'.join(row['text'] for row in data['rows'] if not _in_figure(
                (row['box'][0]*page.rect.width/data['width'],row['box'][1]*page.rect.height/data['height'],
                 row['box'][2]*page.rect.width/data['width'],row['box'][3]*page.rect.height/data['height']),figures))
            for row in data['rows']:
                x0,y0,x1,y1=row['box']
                box=(x0*page.rect.width/data['width'],y0*page.rect.height/data['height'],
                     x1*page.rect.width/data['width'],y1*page.rect.height/data['height'])
                if any(pymupdf.Rect(t.box).contains(pymupdf.Point((box[0]+box[2])/2,(box[1]+box[3])/2)) for t in tables):continue
                if _in_figure(box,figures):continue
                elements.append((box,'text',[dict(text=row['text'],size=row.get('font_size',max(7 if data.get('detailed_ocr') else 9,(box[3]-box[1])*.75/max(1,row.get('line_count',1)))))]))
        for block in source_dict['blocks']:
            lines = []
            for line in block.get('lines', []):
                spans = [s for s in line['spans'] if s['text']]
                if not ''.join(s['text'] for s in spans).strip():
                    continue
                box = pymupdf.Rect(line['bbox'])
                if _in_figure(box,figures):continue
                if any(pymupdf.Rect(t.box).contains(pymupdf.Point((box.x0+box.x1)/2,(box.y0+box.y1)/2)) for t in tables):
                    continue
                if lines:
                    lines.append(dict(text='\n',size=spans[0]['size']))
                lines.extend(spans)
            if lines:
                elements.append((tuple(block['bbox']), 'text', lines))
        elements,columns=_reading_order(elements,page.rect.width)
        if columns:
            page_warnings.append('Multiple columns were converted into an editable reading sequence. Column layout may need adjustment.')
        emitted, previous_bottom = [], margin
        for box, kind, value in elements:
            gap=max(0,min(page.rect.height*.2,box[1]-previous_bottom))
            if kind=='text':
                p=_paragraph(document, value, box, margin, usable)
                p.paragraph_format.space_before=Pt(gap)
                emitted.append(''.join(s['text'] for s in value))
            elif kind=='table':
                if gap > 6:
                    spacer=document.add_paragraph()
                    spacer.paragraph_format.space_after=Pt(0)
                    spacer.paragraph_format.line_spacing=Pt(gap)
                    spacer.add_run().font.size=Pt(1)
                _write_table(document,value, min(usable, max(72,box[2]-box[0])),box[0]-margin,margin+usable-box[2])
                emitted.append(value.text)
            else:
                scale = min(2, math.sqrt(4_000_000/max(1,value.get_area())))
                pix = page.get_pixmap(clip=value,matrix=pymupdf.Matrix(scale,scale),alpha=False,annots=False)
                p = document.add_paragraph()
                p.paragraph_format.space_after = Pt(3)
                p.paragraph_format.space_before = Pt(gap)
                p.paragraph_format.left_indent=Pt(max(0,min(usable*.65,box[0]-margin)))
                width = min(usable,value.width,(page.rect.height-2*margin-20)*value.width/max(1,value.height))
                p.add_run().add_picture(BytesIO(pix.tobytes('png')),width=Pt(width))
                del pix
            previous_bottom=max(previous_bottom,box[3])
        text = source_plain
        source_texts.append(text)
        recovered = 0
        # Counter-based recovery catches missing repeated words and numbers.
        available = tokens('\n'.join(emitted))
        for line in text.splitlines():
            wanted = tokens(line)
            if not wanted:
                continue
            if wanted-available:
                _paragraph(document,[dict(text=line,size=11)])
                emitted.append(line)
                recovered += 1
            else:
                available.subtract(wanted)
        if recovered:
            page_warnings.append('Recovered omitted text at the end of this source page; its position may need adjustment.')
        if not text.strip():
            # A picture/blank page must not masquerade as editable text.
            if page.get_contents() and not figures:
                pix = page.get_pixmap(matrix=pymupdf.Matrix(1,1),alpha=False)
                document.add_picture(BytesIO(pix.tobytes('png')),width=Pt(usable))
                del pix
            page_warnings.append('No editable text was recognized on this page. Check the scan and selected languages.')
        page_report = {'page':index+1,'tables':len(tables),'figures':len(figures),
                       'text_source':fresh_origin if force_visual_ocr else 'pdf-text-and-selective-ocr',
                       'fresh_ocr_used':force_visual_ocr,
                       'ocr_source_rotation':data.get('source_rotation',data.get('remapped_rotation',0)) if force_visual_ocr else 0,
                       'legacy_arabic_recovered':bool(reencoded),
                       'legacy_visible_text_coverage':round(legacy_coverage,4) if legacy_coverage is not None else None,
                       'table_engines':sorted({t.engine for t in tables}),
                       'recovered_lines':recovered,'editable_text_coverage':round(coverage(text,'\n'.join(emitted)),4),
                       'warnings':page_warnings}
        report['pages'].append(page_report)
        engines.update(t.engine for t in tables)
        warnings += [f'Word page {index+1}: {w}' for w in dict.fromkeys(page_warnings)]
    document.core_properties.title = ''
    document.core_properties.author = ''
    document.core_properties.comments = 'Converted locally by yuzufile. Layout reconstruction is approximate.'
    document.save(destination)
    # Reopen actual output, rather than trusting the in-memory writer.
    with ZipFile(destination) as archive:
        if archive.testzip():
            raise RuntimeError('Word output archive validation failed.')
    verified = Document(destination)
    editable = '\n'.join(p.text for p in verified.paragraphs) + '\n' + '\n'.join(
        c.text for t in verified.tables for r in t.rows for c in r.cells)
    report['editable_text_coverage'] = round(coverage('\n'.join(source_texts),editable),4)
    if any(tokens(t) for t in source_texts) and report['editable_text_coverage'] < .99:
        raise RuntimeError('Word output validation found missing extracted text.')
    report['editable_tables'] = len(verified.tables)
    report['replaceable_images'] = len(verified.inline_shapes)
    report['warnings'] = list(dict.fromkeys(warnings))
    report['engines_used'] = sorted(engines)
    destination.with_suffix('.quality.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report
