"""Detect legacy Arabic glyph encodings which masquerade as valid Latin text."""
from io import BytesIO
import re
import math
import pymupdf

from yuzufile.word_rtl import arabic


def _key(name):
    name=re.sub(r'^[A-Z]{6}\+','',name)
    return re.sub(r'[^a-z0-9]','',name.lower()).removesuffix('psmt').removesuffix('mt')


def font_conflicts(page):
    """Return names of fonts whose Arabic glyph IDs decode as non-Arabic.

    An absent ToUnicode map alone is not corruption: ordinary English PDFs
    frequently omit it. The embedded glyph program is independent evidence.
    """
    from fontTools.ttLib import TTFont,TTLibError
    traces={}
    for span in page.get_texttrace():
        # Glyphless/invisible OCR fonts deliberately reuse placeholder glyphs.
        # Their IDs are not evidence of the script painted on the page.
        if span.get('type')==3 or span.get('opacity',1)<=.01:continue
        chars=span.get('chars',())
        if len(chars)>100_000:chars=chars[:100_000]
        wrong=[(u,g) for u,g,*_ in chars if 0<=u<=0x10ffff and not arabic(chr(u)) and chr(u).isalpha()]
        if len(wrong)>=4:traces.setdefault(_key(span['font']),[]).extend(wrong)
    if not traces:return set()
    conflicts=set()
    for font in page.get_fonts(full=True):
        if font[1].lower() not in ('ttf','otf') or font[0]<=0:continue
        # Font names often identify legacy script fonts even when their cmap
        # table was stripped; that case also receives a visual OCR probe below.
        buffer=None
        try:
            _,_,_,buffer=page.parent.extract_font(font[0])
            if not buffer or len(buffer)>12_000_000:continue
            with TTFont(BytesIO(buffer),lazy=True) as program:
                aliases={_key(font[3])}
                if 'name' in program:
                    for record in program['name'].names:
                        if record.nameID in (1,6):
                            try:aliases.add(_key(record.toUnicode()))
                            except UnicodeError:pass
                used=[pair for key in aliases for pair in traces.get(key,[])]
                if len(used)<4:continue
                cmap=program.getBestCmap() or {}
                glyphs={program.getGlyphID(name) for code,name in cmap.items() if code<=0x10ffff and arabic(chr(code))}
                wrong=sum(gid in glyphs for _,gid in used)
                if wrong>=4 and wrong/len(used)>=.25:conflicts.update(aliases & traces.keys())
        except (TTLibError,KeyError,ValueError,RuntimeError,IndexError,UnicodeError):
            continue
        finally:buffer=None
    return conflicts


def mapping_probe(page,blocks,languages):
    spans=[s for b in blocks['blocks'] for line in b.get('lines',[]) for s in line['spans']]
    text=''.join(s['text'] for s in spans)
    if not text.strip():return dict(required=False,strong=False,fonts=set())
    # Already logical Arabic needs no extra font parsing or recognition pass.
    if all(not c.isalpha() or arabic(c) for c in text):
        return dict(required=False,strong=False,fonts=set())
    conflicts=font_conflicts(page)
    type3=any(font[2]=='Type3' for font in page.get_fonts())
    hinted=not arabic(text) and any(re.search(r'arab|urdu|farsi|^axt|^aga',s.get('font',''),re.I)
        and sum(c.isalpha() for c in s['text'])>=4 for s in spans)
    missing_arabic='ara' in (languages or []) and not arabic(text) and any(c.isalpha() for c in text)
    return dict(required=bool(conflicts or type3 or hinted or missing_arabic),strong=bool(conflicts),fonts=conflicts,type3=type3)


def confirmed_arabic(data):
    rows=[r for r in (data or {}).get('rows',[]) if r.get('score',0)>=.75]
    text=''.join(r['text'] for r in rows)
    letters=[c for c in text if c.isalpha()]
    count=sum(arabic(c) for c in letters)
    return count>=8 and count/max(1,len(letters))>=.35


def visible_coverage(page,data):
    """Coverage of painted glyph positions, independent of broken code counts."""
    sx,sy=page.rect.width/data['width'],page.rect.height/data['height']
    step=max(12,page.rect.height/200)
    buckets={}
    for row in data.get('rows',[]):
        if not row['text'].strip():continue
        a,b,c,d=row['box'];rect=pymupdf.Rect(a*sx,b*sy,c*sx,d*sy)
        pad=max(3,rect.height*.3);rect=(rect+(-pad,-pad,pad,pad)) & page.rect
        if rect.is_empty:continue
        for key in range(int(rect.y0/step),int(rect.y1/step)+1):buckets.setdefault(key,[]).append(rect)
    spans=[s for s in page.get_texttrace() if s.get('type')!=3 and s.get('opacity',1)>.01]
    count=sum(len(s['chars']) for s in spans);stride=max(1,math.ceil(count/5000))
    covered=total=seen=0
    for span in spans:
        for code,gid,origin,*_ in span['chars']:
            seen+=1
            if seen%stride or not 32<=code<=0x10ffff or chr(code).isspace():continue
            point=pymupdf.Point(origin)*page.rotation_matrix
            if not page.rect.contains(point):continue
            total+=1
            covered+=any(rect.contains(point) for rect in buckets.get(int(point.y/step),[]))
    return covered/max(1,total) if total else 1.


