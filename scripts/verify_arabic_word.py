"""Real Arabic and bilingual PDF/scan fixtures for export and visual QA."""
import json
from pathlib import Path
import sys
import pymupdf
from docx import Document
from yuzufile.worker import convert

ROOT=Path(sys.argv[1] if len(sys.argv)>1 else 'tmp/arabic-word-qa').absolute()
ROOT.mkdir(exist_ok=True,parents=True)
native=ROOT/'arabic-native.pdf'
scan=ROOT/'arabic-scan.pdf'
html='''<html><body dir="rtl">
<h1>تقرير المبيعات السنوي</h1>
<p>مرحبا بالعالم. هذا مستند عربي قابل للتحرير.</p>
<p>هذا <b>نص عربي عريض</b> مع كلمة <i>مائلة</i> وتشكيل: العَرَبِيَّة.</p>
<p>رقم الطلب <span dir="ltr">PDF-2026</span> والمبلغ <span dir="ltr">12,345.67 EUR</span> والنسبة ٤٣٪.</p>
<p>تاريخ التقرير: ٢٥/١٠/٢٠٢٦. البريد: <span dir="ltr">info@example.com</span></p>
<table><tr><th>الفئة</th><th>القيمة</th></tr>
<tr><td>الشركات الصغيرة</td><td>٤٣٪</td></tr>
<tr><td>الشركات الكبيرة</td><td>٥٧٪</td></tr></table>
<p>English summary: Arabic text, editable tables and replaceable figures.</p>
<p>النهاية — مجموع النسب ١٠٠٪.</p>
</body></html>'''
css='''@font-face {font-family: Arabic;src: url(arial.ttf);}
@font-face {font-family: Arabic;src: url(arialbd.ttf);font-weight:bold;}
@font-face {font-family: Arabic;src: url(ariali.ttf);font-style:italic;}
body {font-family:Arabic;font-size:15pt;line-height:1.5;color:black;}
h1 {font-size:24pt;} p {margin:12pt 0;}
table {border-collapse:collapse;width:100%;} td,th {border:1pt solid #888;padding:10pt;text-align:right;}
'''
with pymupdf.open() as doc:
    page=doc.new_page(width=595,height=842)
    spare,scale=page.insert_htmlbox(pymupdf.Rect(42,35,553,800),html,css=css,archive=pymupdf.Archive('C:/Windows/Fonts'))
    assert spare>=0 and scale==1
    page.draw_rect(pymupdf.Rect(410,695,550,750),fill=(.85,.92,.98),color=(.2,.4,.6))
    page.draw_circle((480,722),18,fill=(.2,.4,.6))
    doc.save(native)
    (ROOT/'native-extraction.txt').write_text(page.get_text(sort=True),encoding='utf-8')
    with pymupdf.open() as scanned:
        target=scanned.new_page(width=595,height=842)
        target.insert_image(target.rect,pixmap=page.get_pixmap(dpi=220))
        scanned.save(scan)
names=sys.argv[2:] or ['native','scanned','mixed']
results={}
for name in names:
    path=scan if name!='native' else native
    languages=['ara','eng'] if name=='mixed' else ['ara']
    target=ROOT/name
    convert(dict(root=str(target),source=str(path),mode='word',languages=languages,performance='balanced'))
    output=target/'result/document.docx'
    doc=Document(output)
    text='\n'.join(p.text for p in doc.paragraphs)+'\n'+'\n'.join(c.text for t in doc.tables for row in t.rows for c in row.cells)
    (ROOT/f'{name}-word-text.txt').write_text(text,encoding='utf-8')
    assert any('\u0600'<=c<='\u06ff' for c in text),(name,text)
    assert 'تقرير المبيعات السنوي' in text and 'مرحبا بالعالم' in text,(name,text)
    assert doc.tables and len(doc.inline_shapes)==1,(name,'Expected editable table and one replaceable figure')
    assert 'PDF' in text and '12,345.67' in text,(name,'Mixed Latin text was lost')
    if name=='native':
        assert 'العَرَبِيَّة' in text,(name,'Undamaged vowel marks changed during repair')
        assert 'ةئفلا' not in text and 'الفئة' in text
    results[name]=json.loads(output.with_suffix('.quality.json').read_text(encoding='utf-8'))
(ROOT/'verification.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print(ROOT)
