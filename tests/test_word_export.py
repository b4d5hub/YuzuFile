import json
from zipfile import ZipFile

from docx import Document
import pymupdf
import pytest

from yuzufile.performance import performance_profile
from yuzufile.word_export import HTMLTables, coverage, write_word, _choose_tables, _reading_order
from yuzufile.worker import convert


def test_native_word_requires_fresh_recognition_languages(digital_pdf, tmp_path):
    root = tmp_path / 'word-job'
    from yuzufile.engines import ConversionError
    with pytest.raises(ConversionError,match='language'):
        convert({'root':str(root),'source':str(digital_pdf),'mode':'word','languages':[]})
    assert not (root/'result').exists()


def test_ruled_table_is_editable_and_not_duplicated_as_image(tmp_path):
    with pymupdf.open() as pdf:
        p = pdf.new_page()
        for x in (50,200,350):
            p.draw_line((x,100),(x,220))
        for y in (100,140,180,220):
            p.draw_line((50,y),(350,y))
        for r, row in enumerate((('Name','Value'),('Alpha','43%'),('Beta','57%'))):
            for c, text in enumerate(row):
                p.insert_text((60+c*150,125+r*40),text)
        target = tmp_path / 'table.docx'
        report = write_word(pdf,target,lambda *a,**k:None,performance_profile('low'))
    word = Document(target)
    assert len(word.tables)==1
    assert word.tables[0].cell(1,1).text == '43%'
    assert word.tables[0].cell(2,1).text == '57%'
    assert not word.inline_shapes
    assert report['editable_text_coverage']==1
    assert not report['pages'][0]['recovered_lines']


def test_html_table_spans_and_untrusted_markup():
    parser = HTMLTables()
    parser.feed('<table><tr><th colspan="2">Title &amp; more</th></tr>'
                '<tr><td rowspan="2">A</td><td>43%</td></tr><tr><td>57%</td></tr></table>')
    cells = parser.tables[0]
    assert (cells[0].cols,cells[0].text)==(2,'Title & more')
    assert (cells[1].rows,cells[3].row,cells[3].col)==(2,2,1)


def test_existing_ocr_pdf_does_not_lose_text(tmp_path):
    with pymupdf.open() as pdf:
        p=pdf.new_page()
        p.insert_text((50,70),'Existing OCR text 99.9%',render_mode=3)
        target=tmp_path/'ocr.docx'
        write_word(pdf,target,lambda *a,**k:None,performance_profile('low'))
    assert '99.9%' in '\n'.join(p.text for p in Document(target).paragraphs)


def test_pages_images_and_arabic_are_real_word_objects(tmp_path):
    with pymupdf.open() as pdf:
        p=pdf.new_page(width=600,height=800)
        p.insert_text((50,70),'Page one')
        pix=pymupdf.Pixmap(pymupdf.csRGB,pymupdf.IRect(0,0,100,60),0)
        pix.clear_with(180)
        p.insert_image(pymupdf.Rect(50,100,250,220),pixmap=pix)
        p=pdf.new_page(width=800,height=600)
        p.insert_font(fontname='Arabic',fontfile='C:/Windows/Fonts/segoeui.ttf')
        # Low-level PDF text placement uses visual glyph order for this RTL font.
        p.insert_text((400,80),'مرحبا بالعالم'[::-1]+' 123',fontname='Arabic')
        target=tmp_path/'mixed.docx'
        report=write_word(pdf,target,lambda *a,**k:None,performance_profile('balanced'))
    word=Document(target)
    assert len(word.sections)==2
    assert len(word.inline_shapes)==1
    assert word.sections[1].page_width > word.sections[1].page_height
    with ZipFile(target) as z:
        xml=z.read('word/document.xml').decode()
        assert '<w:bidi' in xml and '<w:rtl' in xml
        assert 'مرحبا' in xml
    assert report['editable_text_coverage']==1
    assert report['pages'][1]['recovered_lines']==0


def test_coverage_counts_repeated_words_and_numbers():
    assert coverage('same same 43 57','same 43') == .5


def test_uncertain_model_table_cannot_change_source_numbers(tmp_path):
    with pymupdf.open() as pdf:
        p=pdf.new_page()
        p.insert_text((50,70),'Total 43%')
        data={'width':595,'height':842,'blocks':[{'label':'Table','bbox':[40,40,300,100],
            'text':'<table><tr><td>Total</td><td>99%</td></tr></table>'}]}
        warnings=[]
        assert not _choose_tables(p,data,warnings)
        assert warnings


def test_broken_character_mapping_uses_ocr_instead_of_garbled_text(tmp_path,monkeypatch):
    with pymupdf.open() as pdf:
        p=pdf.new_page()
        p.insert_text((50,70),'Corrected words')
        original=pymupdf.Page.get_text
        def bad_text(self,option='text',*args,**kwargs):
            if option=='dict':
                return {'blocks':[{'bbox':(50,50,200,80),'lines':[{'bbox':(50,50,200,80),
                    'spans':[{'text':'Bad \ufffd mapping','size':11}]}]}]}
            if option=='text':
                return 'Bad \ufffd mapping'
            return original(self,option,*args,**kwargs)
        monkeypatch.setattr(pymupdf.Page,'get_text',bad_text)
        monkeypatch.setattr('yuzufile.indra_engine.available',lambda:True)
        def recognize(path,*args):
            target=path.with_suffix('.json')
            target.write_text(json.dumps({'width':595,'height':842,'rotation':0,'blocks':[],
                'rows':[{'box':[50,50,200,80],'text':'Corrected words','score':.99}]}))
            return target
        monkeypatch.setattr('yuzufile.indra_engine.recognize',recognize)
        target=tmp_path/'repaired.docx'
        report=write_word(pdf,target,lambda *a,**k:None,performance_profile('low'))
    text='\n'.join(p.text for p in Document(target).paragraphs)
    assert 'Corrected words' in text and '\ufffd' not in text
    assert report['warnings'] and 'indra-ocr-1.1.2' in report['engines_used']


def test_scanned_grid_geometry_wins_over_tight_model_text_bounds():
    with pymupdf.open() as native,pymupdf.open() as scan:
        p=native.new_page()
        for x in (50,200,350):p.draw_line((x,100),(x,220))
        for y in (100,140,180,220):p.draw_line((50,y),(350,y))
        values=(('Name','Value'),('Alpha','43%'),('Beta','57%'))
        for r,row in enumerate(values):
            for c,text in enumerate(row):p.insert_text((60+c*150,125+r*40),text)
        q=scan.new_page()
        q.insert_image(q.rect,pixmap=p.get_pixmap(dpi=150))
        for r,row in enumerate(values):
            for c,text in enumerate(row):q.insert_text((60+c*150,125+r*40),text,render_mode=3)
        data={'width':595,'height':842,'blocks':[{'label':'Table','bbox':[60,110,240,210],
            'text':'<table>'+''.join('<tr>'+''.join('<td>'+v+'</td>' for v in row)+'</tr>' for row in values)+'</table>'}]}
        tables=_choose_tables(q,data,[])
        assert len(tables)==1
        assert tables[0].engine=='opencv-grid+ocr'
        assert tables[0].box[2] > 345


def test_reading_order_keeps_column_paragraphs_together():
    elements=[((40,80,240,160),'text',[{'text':'Left first'}]),
              ((340,80,540,160),'text',[{'text':'Right first'}]),
              ((40,180,240,260),'text',[{'text':'Left second'}]),
              ((340,180,540,260),'text',[{'text':'Right second'}])]
    result,columns=_reading_order(elements,600)
    assert columns
    assert [e[2][0]['text'] for e in result]==['Left first','Left second','Right first','Right second']
