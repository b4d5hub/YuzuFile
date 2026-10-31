import json
from pathlib import Path

import pymupdf
import pytest
from docx import Document
from docx.oxml.ns import qn
from docx.enum.table import WD_TABLE_DIRECTION

from yuzufile.performance import performance_profile
from yuzufile.word_export import _paragraph,_write_table,Cell,Table,_arabic_ocr_rows,_repair_native_lines,write_word
from yuzufile.word_rtl import logical_chars,directional_parts,base_rtl,native_blocks


def test_visual_arabic_character_order_becomes_logical_without_reversing_digits():
    text='ريرقتلا خيرات'
    chars=[dict(c=c,origin=(100+i*8,20)) for i,c in enumerate(text)]
    assert logical_chars(chars)=='تاريخ التقرير'
    text='مرحبا 12,345.67 EUR'
    chars=[dict(c=c,origin=(400-i*8,20)) for i,c in enumerate('مرحبا ')]+[
        dict(c=c,origin=(100+i*8,20)) for i,c in enumerate('12,345.67 EUR')]
    assert logical_chars(chars)==text


def test_combining_marks_stay_attached_to_letters():
    text='عَرَبِيَّة'
    chars=[];x=300
    import unicodedata
    for c in text:
        chars.append(dict(c=c,origin=(x,20)))
        if not unicodedata.combining(c):x-=10
    assert logical_chars(chars)==text


def test_mixed_script_word_runs_define_complex_formatting_and_keep_latin_order():
    doc=Document()
    p=_paragraph(doc,[dict(text='رقم الطلب PDF-2026 والمبلغ 12,345.67 EUR',size=14,flags=18)])
    assert p.text=='رقم الطلب PDF-2026 والمبلغ 12,345.67 EUR'
    assert p._p.pPr.find(qn('w:bidi')) is not None
    assert p._p.pPr.find(qn('w:jc')).get(qn('w:val'))=='start'
    arabic_runs=[r for r in p.runs if 'الطلب' in r.text]
    assert arabic_runs
    for run in arabic_runs:
        assert run.font.cs_bold and run.font.cs_italic
        assert run._r.rPr.find(qn('w:rtl')).get(qn('w:val'))=='1'
        assert run._r.rPr.find(qn('w:lang')).get(qn('w:bidi'))=='ar-SA'
        assert run._r.rPr.find(qn('w:szCs')).get(qn('w:val'))=='28'
    latin=next(r for r in p.runs if 'PDF-2026' in r.text)
    assert latin._r.rPr.find(qn('w:rtl')).get(qn('w:val'))=='0'


def test_english_paragraph_with_arabic_insertion_stays_ltr():
    doc=Document();p=_paragraph(doc,[dict(text='Reference: تقرير المبيعات')])
    assert p._p.pPr.find(qn('w:bidi')) is None
    assert not base_rtl(p.text)


def test_rtl_table_retains_physical_columns_and_merged_cells():
    doc=Document()
    candidate=Table((0,0,300,100),[
        Cell('عنوان',0,0,cols=2),Cell('٤٣',1,0),Cell('المبيعات',1,1)],2,2,'test',[100,200])
    table=_write_table(doc,candidate,300)
    assert table.table_direction==WD_TABLE_DIRECTION.RTL
    assert table.cell(0,0).text=='عنوان' and table.cell(0,1).text=='عنوان'
    assert table.cell(1,0).text=='المبيعات'
    assert table.cell(1,1).text=='٤٣'
    assert table.columns[0].width.pt==pytest.approx(200)
    assert table.cell(1,1).paragraphs[0]._p.pPr.find(qn('w:bidi')) is not None


def test_native_bilingual_pdf_lines_and_tables_are_readable(tmp_path):
    source=tmp_path/'arabic.pdf'
    with pymupdf.open() as pdf:
        p=pdf.new_page()
        html='''<body dir="rtl"><h1>تقرير المبيعات</h1>
        <p>رقم الطلب <span dir="ltr">PDF-2026</span> والمبلغ <span dir="ltr">12,345.67 EUR</span>.</p>
        <table><tr><td>الفئة</td><td>القيمة</td></tr>
        <tr><td>الشركات الصغيرة</td><td>٤٣</td></tr>
        <tr><td>الشركات الكبيرة</td><td>٥٧</td></tr></table></body>'''
        css='''@font-face{font-family:Arabic;src:url(arial.ttf);} body{font:15pt Arabic;}
        table{width:100%;border-collapse:collapse;}td{border:1pt solid black;padding:10pt;}'''
        p.insert_htmlbox(pymupdf.Rect(40,40,550,790),html,css=css,archive=pymupdf.Archive('C:/Windows/Fonts'))
        pdf.save(source)
        target=tmp_path/'arabic.docx'
        report=write_word(pdf,target,lambda *a,**k:None,performance_profile('low'),['ara','eng'])
    word=Document(target)
    paragraphs=[p.text for p in word.paragraphs]
    line=next(p for p in paragraphs if 'PDF' in p)
    assert '\n' not in line and 'المبلغ' in line and '12,345.67 EUR' in line
    table_text='\n'.join(c.text for t in word.tables for r in t.rows for c in r.cells)
    assert 'الفئة' in table_text and 'الشركات الصغيرة' in table_text
    assert 'ةئفلا' not in table_text
    assert report['pages'][0]['recovered_lines']==0
    assert report['editable_text_coverage']==1


def test_arabic_numeric_verification_keeps_mixed_sentences(tmp_path,monkeypatch):
    monkeypatch.setattr('yuzufile.neural_text.available',lambda:True)
    called=[]
    def recognize(path,languages):
        called.append(languages)
        result=path.with_suffix('.json')
        result.write_text(json.dumps(dict(width=600,height=800,rows=[
            dict(box=[400,100,500,130],text='٥٧',score=.6),
            dict(box=[400,150,500,180],text='٤٣',score=.96),
            dict(box=[50,200,550,230],text='رقمالطلب',score=.9)])),encoding='utf-8')
        return result
    monkeypatch.setattr('yuzufile.neural_text.recognize',recognize)
    data=dict(width=600,height=800,rows=[
        dict(box=[400,100,500,130],text='7.04',score=.6),
        dict(box=[50,200,550,230],text='رقم الطلب PDF-2026',score=.8)])
    warnings=[];engines=set()
    with pymupdf.open() as doc:
        p=doc.new_page(width=600,height=800)
        result=_arabic_ocr_rows(p,data,tmp_path,performance_profile('low'),warnings,engines)
    assert called==[['ara']]
    assert [r['text'] for r in result['rows']]==['٥٧','٤٣','رقم الطلب PDF-2026']
    assert data['rows'][0]['text']=='7.04'
    assert warnings and 'rapidocr-arabic-verification' in engines
    assert not list(tmp_path.glob('word-arabic-check*'))


def test_confident_arabic_does_not_load_second_model(tmp_path,monkeypatch):
    monkeypatch.setattr('yuzufile.neural_text.available',lambda:pytest.fail('No second OCR engine needed'))
    data=dict(width=600,height=800,rows=[dict(box=[50,50,500,100],text='مرحبا بالعالم',score=.99)])
    with pymupdf.open() as doc:
        page=doc.new_page()
        result=_arabic_ocr_rows(page,data,tmp_path,performance_profile('low'),[],set())
        assert result['logical_ocr'] and result['rows']==data['rows']


def test_one_damaged_diacritic_does_not_replace_undamaged_native_text():
    source={'blocks':[{'lines':[
        {'bbox':(50,40,500,60),'spans':[dict(text='تقرير المبيعات',size=22)]},
        {'bbox':(50,80,500,100),'spans':[dict(text='كلمة مائ\ufffdة ورقم 43',size=12)]}]}]}
    model=dict(width=600,height=800,rows=[
        dict(box=[50,40,500,60],text='An incorrect model heading'),
        dict(box=[50,80,500,100],text='كلمة مائلة ورقم 57')])
    with pymupdf.open() as doc:
        p=doc.new_page(width=600,height=800)
        _repair_native_lines(p,source,model)
    lines=source['blocks'][0]['lines']
    assert lines[0]['spans'][0]['text']=='تقرير المبيعات'
    assert lines[1]['spans'][0]['text']=='كلمة مائلة ورقم 43'
