"""Word must reconstruct from the current clean-page OCR, never an older layer."""
import json
from zipfile import ZipFile

import pymupdf
import pytest
from docx import Document

from yuzufile.performance import performance_profile
from yuzufile.word_export import write_word


def mark(page):
    page.parent.xref_set_key(page.xref,'PDFaiOCR','true')
    page.parent.xref_set_key(page.xref,'PDFaiFreshOCR','true')


def cache(destination,number,rows,**extra):
    scratch=destination.parent/'scratch';scratch.mkdir(exist_ok=True)
    data=dict(width=600,height=800,rows=rows,blocks=[],rotation=0,
              fresh_ocr=True,logical_ocr=True,engine='Indra OCR 1.1.2')
    data.update(extra)
    (scratch/f'fresh-ocr-page-{number}.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')


def row(text,box=(60,70,500,95)):
    return dict(text=text,box=list(box),score=.99)


def ban_repeated_ocr(monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('Fresh Word reconstruction must not repeat full-page OCR or inspect legacy font maps')
    monkeypatch.setattr('yuzufile.indra_engine.recognize',forbidden)
    monkeypatch.setattr('yuzufile.word_export.mapping_probe',forbidden)
    monkeypatch.setattr('yuzufile.word_export.native_blocks',forbidden)
    monkeypatch.setattr('yuzufile.word_export._arabic_ocr_rows',forbidden)


def test_fresh_rows_replace_poisoned_pdf_text_in_page_order(tmp_path,monkeypatch):
    ban_repeated_ocr(monkeypatch)
    target=tmp_path/'fresh.docx';messages=[]
    with pymupdf.open() as pdf:
        for number in range(1,4):
            page=pdf.new_page(width=600,height=800)
            page.insert_text((60,85),'OLD HIDDEN TEXT 999',render_mode=3);mark(page)
            cache(target,number,[row(f'Fresh recognized page {number}')])
        report=write_word(pdf,target,lambda text,**kw:messages.append(text),performance_profile('high'),['eng'],force_visual_ocr=True)
    word=Document(target);text='\n'.join(p.text for p in word.paragraphs)
    assert 'OLD' not in text and '999' not in text
    assert text.index('page 1')<text.index('page 2')<text.index('page 3')
    assert len(word.sections)==3
    assert [p['page'] for p in report['pages']]==[1,2,3]
    assert all(p['text_source']=='fresh-ocr-cache' and p['fresh_ocr_used'] for p in report['pages'])
    assert report['text_source']=='fresh-visual-ocr' and report['editable_text_coverage']==1
    assert len(messages)==3 and all(f'page {i}' in messages[i-1] for i in range(1,4))


def test_fresh_word_requires_recognition_marker_and_rejects_old_cache(tmp_path):
    target=tmp_path/'rejected.docx'
    with pymupdf.open() as pdf:
        page=pdf.new_page();page.insert_text((50,70),'Old OCR',render_mode=3)
        cache(target,1,[row('Old cached text')])
        with pytest.raises(RuntimeError,match='fresh page OCR is required'):
            write_word(pdf,target,lambda *a,**k:None,performance_profile('low'),['eng'],force_visual_ocr=True)
        assert not target.exists()
        mark(page);cache(target,1,[row('Old cached text')],fresh_ocr=False)
        with pytest.raises(RuntimeError,match='not from the fresh-page'):
            write_word(pdf,target,lambda *a,**k:None,performance_profile('low'),['eng'],force_visual_ocr=True)
        assert not target.exists()


def test_fresh_blank_page_is_preserved_without_inventing_text(tmp_path,monkeypatch):
    ban_repeated_ocr(monkeypatch);target=tmp_path/'blank.docx'
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=600,height=800);mark(page);cache(target,1,[])
        report=write_word(pdf,target,lambda *a,**k:None,performance_profile('low'),['eng'],force_visual_ocr=True)
    assert not '\n'.join(p.text for p in Document(target).paragraphs).strip()
    assert len(Document(target).sections)==1 and report['pages'][0]['fresh_ocr_used']
    assert any('No editable text was recognized' in w for w in report['warnings'])


def test_fresh_overlay_fallback_does_not_start_another_model(tmp_path,monkeypatch):
    ban_repeated_ocr(monkeypatch);target=tmp_path/'overlay.docx'
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=600,height=800)
        page.insert_text((50,80),'Fresh recognized overlay 43%',render_mode=3);mark(page)
        report=write_word(pdf,target,lambda *a,**k:None,performance_profile('low'),['eng'],force_visual_ocr=True)
    assert 'Fresh recognized overlay 43%' in '\n'.join(p.text for p in Document(target).paragraphs)
    assert report['pages'][0]['text_source']=='fresh-pdf-overlay'
    assert report['editable_text_coverage']==1


def test_fresh_arabic_strings_stay_logical_and_figures_are_replaceable(tmp_path,monkeypatch):
    ban_repeated_ocr(monkeypatch);target=tmp_path/'arabic.docx'
    text='رقم الطلب PDF-2026 والمبلغ 12,345.67 EUR'
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=600,height=800);mark(page)
        page.draw_rect(pymupdf.Rect(70,250,250,360),fill=(.3,.3,.3))
        cache(target,1,[row(text)],blocks=[dict(label='Picture',bbox=[70,250,250,360])])
        report=write_word(pdf,target,lambda *a,**k:None,performance_profile('low'),['ara','eng'],force_visual_ocr=True)
    word=Document(target);actual='\n'.join(p.text for p in word.paragraphs)
    assert text in actual and 'بلطلا مقر' not in actual
    assert len(word.inline_shapes)==1 and report['replaceable_images']==1
    with ZipFile(target) as archive:
        xml=archive.read('word/document.xml').decode()
        assert '<w:bidi' in xml and '<w:rtl' in xml
    assert report['editable_text_coverage']==1


def test_fresh_model_table_is_editable_without_old_pdf_values(tmp_path,monkeypatch):
    ban_repeated_ocr(monkeypatch);target=tmp_path/'table.docx'
    rows=[row('Name',[60,105,120,130]),row('Value',[220,105,285,130]),
          row('Alpha',[60,145,120,170]),row('43%',[220,145,285,170]),
          row('Beta',[60,185,120,210]),row('57%',[220,185,285,210])]
    table='<table><tr><th>Name</th><th>Value</th></tr><tr><td>Alpha</td><td>43%</td></tr><tr><td>Beta</td><td>57%</td></tr></table>'
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=600,height=800);page.insert_text((50,120),'STALE 99%');mark(page)
        cache(target,1,rows,blocks=[dict(label='Table',bbox=[50,100,350,220],text=table)])
        report=write_word(pdf,target,lambda *a,**k:None,performance_profile('low'),['eng'],force_visual_ocr=True)
    word=Document(target)
    assert len(word.tables)==1
    text='\n'.join(c.text for r in word.tables[0].rows for c in r.cells)
    assert '43%' in text and '57%' in text and '99%' not in text
    assert not any('STALE' in p.text for p in word.paragraphs)
    assert report['editable_text_coverage']==1


def test_fresh_rotated_cache_keeps_text_without_reusing_old_layer(tmp_path,monkeypatch):
    ban_repeated_ocr(monkeypatch);target=tmp_path/'rotated.docx'
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=600,height=800);page.insert_text((50,70),'OLD WORDS');mark(page)
        cache(target,1,[row('Readable fresh words',[100,50,300,80])],width=800,height=600,rotation=90)
        report=write_word(pdf,target,lambda *a,**k:None,performance_profile('low'),['eng'],force_visual_ocr=True)
    word=Document(target);text='\n'.join(p.text for p in word.paragraphs)
    assert 'Readable fresh words' in text and 'OLD WORDS' not in text
    assert report['pages'][0]['fresh_ocr_used'] and any('Rotated OCR' in w for w in report['warnings'])


def test_page_sized_figure_cannot_hide_fresh_editable_text(tmp_path,monkeypatch):
    ban_repeated_ocr(monkeypatch);target=tmp_path/'slide.docx'
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=600,height=800);mark(page)
        cache(target,1,[row('Recognized slide title')],blocks=[dict(label='Picture',bbox=[0,0,600,800])])
        report=write_word(pdf,target,lambda *a,**k:None,performance_profile('low'),['eng'],force_visual_ocr=True)
    assert 'Recognized slide title' in '\n'.join(p.text for p in Document(target).paragraphs)
    assert report['editable_text_coverage']==1


def test_lazy_preparer_finishes_word_page_before_recognizing_next(tmp_path,monkeypatch):
    ban_repeated_ocr(monkeypatch);target=tmp_path/'lazy.docx';events=[]
    from yuzufile import word_export
    paragraph=word_export._paragraph
    def build_paragraph(parent,spans,*args,**kwargs):
        text=''.join(span['text'] for span in spans)
        if text.startswith('Prepared page '):events.append(('build',int(text.rsplit(' ',1)[1])-1))
        return paragraph(parent,spans,*args,**kwargs)
    monkeypatch.setattr(word_export,'_paragraph',build_paragraph)
    with pymupdf.open() as prepared:
        class LazySource:
            def __len__(self):return 3
            def __getitem__(self,index):
                assert index<len(prepared),'Word accessed a page before its fresh OCR pass'
                return prepared[index]
            def __getattr__(self,name):return getattr(prepared,name)
        def prepare(index):
            assert len(prepared)==index
            if index:assert ('build',index-1) in events
            events.append(('prepare',index))
            page=prepared.new_page(width=600,height=800);mark(page)
            cache(target,index+1,[row(f'Prepared page {index+1}')])
        report=write_word(LazySource(),target,lambda *a,**k:None,performance_profile('high'),['eng'],
                          force_visual_ocr=True,prepare_page=prepare)
    assert events==[('prepare',0),('build',0),('prepare',1),('build',1),('prepare',2),('build',2)]
    word=Document(target)
    assert len(word.sections)==3 and report['source_pages']==3
    assert report['fresh_ocr_pages']==3 and report['editable_text_coverage']==1


def test_lazy_preparation_failure_does_not_export_incomplete_word(tmp_path,monkeypatch):
    ban_repeated_ocr(monkeypatch);target=tmp_path/'incomplete.docx';called=[]
    with pymupdf.open() as prepared:
        class LazySource:
            def __len__(self):return 2
            def __getitem__(self,index):return prepared[index]
            def __getattr__(self,name):return getattr(prepared,name)
        def prepare(index):
            called.append(index)
            if index==1:raise RuntimeError('OCR failed on page 2')
            page=prepared.new_page(width=600,height=800);mark(page)
            cache(target,index+1,[row('Only page one recognized')])
        with pytest.raises(RuntimeError,match='OCR failed on page 2'):
            write_word(LazySource(),target,lambda *a,**k:None,performance_profile('low'),['eng'],
                       force_visual_ocr=True,prepare_page=prepare)
    assert called==[0,1] and not target.exists() and not target.with_suffix('.quality.json').exists()


def test_dense_framed_callout_remains_editable_beside_qr_figure(tmp_path,monkeypatch):
    ban_repeated_ocr(monkeypatch);target=tmp_path/'callout.docx'
    lines=['This framed callout is editable document text, not a picture.',
           'Its recognized paragraphs must remain available for changes.',
           'Keep the nearby QR code as a separate replaceable image.',
           'Preserve all four source lines in their current reading order.']
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=600,height=800);mark(page)
        page.draw_rect(pymupdf.Rect(50,100,550,300))
        page.draw_rect(pymupdf.Rect(400,500,520,620),fill=(0,0,0))
        cache(target,1,[row(text,[70,125+i*40,520,155+i*40]) for i,text in enumerate(lines)],
              blocks=[dict(label='Picture',bbox=[50,100,550,300]),
                      dict(label='Picture',bbox=[400,500,520,620])])
        report=write_word(pdf,target,lambda *a,**k:None,performance_profile('low'),['eng'],force_visual_ocr=True)
    word=Document(target);text='\n'.join(p.text for p in word.paragraphs)
    assert all(line in text for line in lines)
    assert len(word.inline_shapes)==1 and report['replaceable_images']==1
    assert report['editable_text_coverage']==1
    assert any('framed region was kept editable' in warning for warning in report['warnings'])


def test_sparse_diagram_labels_do_not_remove_replaceable_figure(tmp_path,monkeypatch):
    ban_repeated_ocr(monkeypatch);target=tmp_path/'diagram.docx'
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=600,height=800);mark(page)
        page.draw_rect(pymupdf.Rect(50,100,550,400),fill=(.8,.8,.8))
        rows=[row('Diagram label with enough letters for a real process step',[100,130+i*80,190,145+i*80]) for i in range(3)]
        cache(target,1,rows,blocks=[dict(label='Picture',bbox=[50,100,550,400])])
        report=write_word(pdf,target,lambda *a,**k:None,performance_profile('low'),['eng'],force_visual_ocr=True)
    assert len(Document(target).inline_shapes)==1 and report['replaceable_images']==1
    assert not any('framed region was kept editable' in warning for warning in report['warnings'])
