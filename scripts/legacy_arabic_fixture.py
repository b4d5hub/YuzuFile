"""A PDF that renders Arabic but exposes Latin garbage through ToUnicode."""
from pathlib import Path
import re
import unicodedata
import json
import pymupdf


def create(path):
    path=Path(path)
    with pymupdf.open() as doc:
        p=doc.new_page()
        html='''<body dir="rtl"><h1>تقرير المبيعات السنوي</h1>
        <p>مرحبا بالعالم هذا مستند عربي واضح وقابل للتحرير</p>
        <p>تحتاج هذه الصفحة إلى قراءة الحروف الظاهرة بشكل صحيح</p>
        <p>النص العربي ليس حروفا لاتينية ولا رموزا غريبة</p></body>'''
        css='''@font-face {font-family:Arabic;src:url(arial.ttf);}
        body {font:18pt Arabic;line-height:1.6;}h1{font-size:26pt;}'''
        p.insert_htmlbox(pymupdf.Rect(45,40,550,760),html,css=css,archive=pymupdf.Archive('C:/Windows/Fonts'))
        image=p.get_pixmap(dpi=100).samples
        rows=[dict(text=unicodedata.normalize('NFKC',''.join(s['text'] for s in line['spans'])),
                   box=list(line['bbox']),score=.99) for block in p.get_text('dict')['blocks'] for line in block.get('lines',[])]
        path.with_suffix('.ocr-reference.json').write_text(json.dumps(dict(width=p.rect.width,height=p.rect.height,
            rotation=0,blocks=[],rows=rows)),encoding='utf-8')
        for font in p.get_fonts():
            kind,value=doc.xref_get_key(font[0],'ToUnicode')
            if kind!='xref':continue
            xref=int(value.split()[0]);cmap=doc.xref_stream(xref).decode('ascii')
            def replace(match):
                code=int(match[2],16)
                if 'ARABIC' not in unicodedata.name(chr(code),''):return match[0]
                return f'<{match[1]}> <{65+code%26:04x}>'
            cmap=re.sub(r'(?m)^<([0-9a-fA-F]+)> <([0-9a-fA-F]{4})>$',replace,cmap)
            def replace_range(match):
                first,last,base=(int(value,16) for value in match.groups())
                if not any('ARABIC' in unicodedata.name(chr(base+n),'') for n in range(last-first+1)):return match[0]
                values=[]
                for n in range(last-first+1):
                    code=base+n
                    if 'ARABIC' in unicodedata.name(chr(code),''):code=65+code%26
                    values.append(f'<{code:04x}>')
                return f'<{first:04x}> <{last:04x}> ['+' '.join(values)+']'
            cmap=re.sub(r'(?m)^<([0-9a-fA-F]+)> <([0-9a-fA-F]+)> <([0-9a-fA-F]+)>$',replace_range,cmap)
            doc.update_stream(xref,cmap.encode('ascii'))
        doc.save(path)
    with pymupdf.open(path) as check:
        assert check[0].get_pixmap(dpi=100).samples==image,'Fixture must preserve rendered glyphs'
        assert not any('ARABIC' in unicodedata.name(c,'') for c in check[0].get_text()),'Fixture must expose Latin text'
    return path


if __name__=='__main__':
    import sys
    print(create(sys.argv[1]))
