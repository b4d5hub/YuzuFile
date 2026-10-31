"""Recover logical Arabic text from PDF glyph geometry; keep Word text editable."""
import unicodedata
import pymupdf


def direction(character):
    bidi=unicodedata.bidirectional(character)
    if bidi in ('R','AL'):return True
    if bidi in ('L','EN','AN'):return False
    return None


def arabic(text):
    return any('ARABIC' in unicodedata.name(c,'') and unicodedata.category(c).startswith('L') for c in text)


def base_rtl(text,default=False):
    return next((direction(c) for c in text if unicodedata.bidirectional(c) in ('L','R','AL')),default)


def directional_parts(text):
    """Resolve neutrals without forcing Latin words/numbers into an RTL run."""
    directions=[direction(c) for c in text]
    previous=None
    following=[None]*len(text)
    upcoming=None
    for i in range(len(text)-1,-1,-1):
        following[i]=upcoming
        if directions[i] is not None:upcoming=directions[i]
    for i,c in enumerate(text):
        current=directions[i]
        if current is None:
            current=previous if previous is not None else following[i]
            directions[i]=bool(current)
        else:previous=current
    start=0
    for i in range(1,len(text)+1):
        if i==len(text) or directions[i]!=directions[start]:
            yield text[start:i],directions[start]
            start=i


def logical_chars(chars):
    if not chars:return ''
    text=''.join(c['c'] for c in chars)
    if not arabic(text):return text
    # Keep combining marks attached to the preceding glyph, rather than sorting
    # their independent PDF coordinates away from the letter they decorate.
    clusters=[]
    for char in chars:
        if clusters and all(unicodedata.combining(c) for c in char['c']):
            if clusters[-1]['text'].isspace() and len(clusters)>1:clusters.pop()
            clusters[-1]['text']+=char['c']
        else:clusters.append({'text':char['c'],'x':char['origin'][0]})
    combined=''.join(c['text'] for c in clusters)
    parts=[];offset=0;index=0
    for part,rtl in directional_parts(combined):
        end=offset+len(part);group=[]
        while index<len(clusters) and offset<end:
            cluster=clusters[index];group.append(cluster);offset+=len(cluster['text']);index+=1
        if group:
            group.sort(key=lambda c:c['x'],reverse=rtl)
            parts.append((min(c['x'] for c in group),max(c['x'] for c in group),''.join(c['text'] for c in group)))
    # The first strong character determines paragraph direction. Each script
    # segment retains its own direction, including dates and Latin identifiers.
    parts.sort(key=lambda p:(p[0]+p[1])/2,reverse=base_rtl(text))
    return ''.join(p[2] for p in parts)


def native_blocks(page,clip=None):
    kwargs={'clip':clip} if clip is not None else {}
    raw=page.get_text('rawdict',flags=0,sort=True,**kwargs)
    blocks=[]
    for block in raw['blocks']:
        lines=[]
        for original in block.get('lines',[]):
            line={**original,'spans':[]}
            for span in original['spans']:
                line['spans'].append({**{k:v for k,v in span.items() if k!='chars'},'text':logical_chars(span['chars'])})
            # MuPDF may split one bilingual baseline into several "lines".
            # Join only adjacent horizontal fragments, never distant columns.
            previous=lines[-1] if lines else None
            box=pymupdf.Rect(line['bbox'])
            old=pymupdf.Rect(previous['bbox']) if previous else None
            size=max((s['size'] for s in line['spans']),default=11)
            gap=max(box.x0-old.x1,old.x0-box.x1,0) if old else 0
            same=old and abs(box.y0-old.y0)<max(2,size*.2) and abs(box.y1-old.y1)<max(2,size*.2)
            horizontal=abs(line.get('dir',(1,0))[1])<.1 and (not previous or abs(previous.get('dir',(1,0))[1])<.1)
            if same and horizontal and gap<size*2:
                previous['spans'].extend(line['spans']);previous['bbox']=tuple(old|box)
            else:lines.append(line)
        blocks.append({**block,'lines':lines})
    return {**raw,'blocks':blocks}


def cell_text(page,box):
    return '\n'.join(''.join(s['text'] for s in line['spans']).strip()
        for b in native_blocks(page,pymupdf.Rect(box))['blocks'] for line in b['lines']).strip()
