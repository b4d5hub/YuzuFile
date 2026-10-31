import json
import sys
from pathlib import Path

import pymupdf
import pytest
from docx import Document
from yuzufile.performance import performance_profile
from yuzufile.word_export import write_word
from yuzufile.word_rtl import native_blocks
from yuzufile.word_mapping import mapping_probe,confirmed_arabic,font_conflicts

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from legacy_arabic_fixture import create


@pytest.fixture
def legacy(tmp_path):return create(tmp_path/'legacy.pdf')


def recognized(path,*args):
    target=path.with_suffix('.json')
    reference=path.parent.parent/'legacy.ocr-reference.json'
    if reference.exists():
        target.write_bytes(reference.read_bytes());return target
    target.write_text(json.dumps(dict(width=595,height=842,rotation=0,blocks=[],rows=[
        dict(box=[200,40,550,90],text='تقرير المبيعات السنوي',score=.99),
        dict(box=[80,110,550,140],text='مرحبا بالعالم هذا مستند عربي واضح وقابل للتحرير',score=.98),
        dict(box=[80,150,550,180],text='تحتاج هذه الصفحة إلى قراءة الحروف الظاهرة بشكل صحيح',score=.98),
        dict(box=[80,190,550,220],text='النص العربي ليس حروفا لاتينية ولا رموزا غريبة',score=.98)])),encoding='utf-8')
    return target


def test_font_glyph_evidence_detects_valid_ascii_corruption_without_language_selection(legacy):
    with pymupdf.open(legacy) as doc:
        assert '\ufffd' not in doc[0].get_text()
        probe=mapping_probe(doc[0],native_blocks(doc[0]),[])
        assert probe['required'] and probe['strong'] and probe['fonts']


def test_garbled_native_text_is_not_recovered_back_into_word(legacy,tmp_path,monkeypatch):
    monkeypatch.setattr('yuzufile.indra_engine.available',lambda:True)
    monkeypatch.setattr('yuzufile.indra_engine.recognize',recognized)
    with pymupdf.open(legacy) as doc:
        garbage=doc[0].get_text().strip().splitlines()[0]
        out=tmp_path/'output.docx'
        report=write_word(doc,out,lambda *a,**k:None,performance_profile('low'),[])
    text='\n'.join(p.text for p in Document(out).paragraphs)
    assert 'تقرير المبيعات السنوي' in text and garbage not in text
    assert report['pages'][0]['legacy_arabic_recovered']
    assert report['pages'][0]['recovered_lines']==0


def test_known_bad_font_fails_clearly_if_ocr_cannot_recover(legacy,tmp_path,monkeypatch):
    monkeypatch.setattr('yuzufile.indra_engine.available',lambda:False)
    def unavailable(*args):raise RuntimeError('Detailed local OCR is unavailable')
    monkeypatch.setattr('yuzufile.word_detailed_ocr.recover',unavailable)
    with pymupdf.open(legacy) as doc,pytest.raises(RuntimeError,match='Arabic OCR could not finish'):
        write_word(doc,tmp_path/'bad.docx',lambda *a,**k:None,performance_profile('low'),['ara'])
    assert not (tmp_path/'bad.docx').exists()


def test_arabic_selection_still_recovers_if_embedded_font_has_no_useful_cmap(legacy,tmp_path,monkeypatch):
    monkeypatch.setattr('yuzufile.word_mapping.font_conflicts',lambda page:set())
    monkeypatch.setattr('yuzufile.indra_engine.available',lambda:True)
    monkeypatch.setattr('yuzufile.indra_engine.recognize',recognized)
    with pymupdf.open(legacy) as doc:
        report=write_word(doc,tmp_path/'cmapless.docx',lambda *a,**k:None,performance_profile('low'),['ara'])
    assert report['pages'][0]['legacy_arabic_recovered']


def test_type3_fonts_receive_visual_check_without_arabic_selection(legacy,tmp_path,monkeypatch):
    monkeypatch.setattr('yuzufile.word_mapping.font_conflicts',lambda page:set())
    monkeypatch.setattr(pymupdf.Page,'get_fonts',lambda *a,**k:[(0,'n/a','Type3','','T0','')])
    monkeypatch.setattr('yuzufile.indra_engine.available',lambda:True)
    monkeypatch.setattr('yuzufile.indra_engine.recognize',recognized)
    with pymupdf.open(legacy) as doc:
        report=write_word(doc,tmp_path/'type3.docx',lambda *a,**k:None,performance_profile('low'),['eng'])
    assert report['pages'][0]['legacy_arabic_recovered']


def test_hybrid_ocr_marker_does_not_hide_a_native_bad_font(legacy,tmp_path,monkeypatch):
    monkeypatch.setattr('yuzufile.indra_engine.available',lambda:True)
    monkeypatch.setattr('yuzufile.indra_engine.recognize',recognized)
    with pymupdf.open(legacy) as doc:
        doc.xref_set_key(doc[0].xref,'PDFaiOCR','true')
        report=write_word(doc,tmp_path/'hybrid.docx',lambda *a,**k:None,performance_profile('low'),['ara'])
    assert report['pages'][0]['legacy_arabic_recovered']


def test_selected_arabic_probes_english_but_does_not_replace_valid_latin(digital_pdf,tmp_path,monkeypatch):
    monkeypatch.setattr('yuzufile.indra_engine.available',lambda:True)
    def english(path,*args):
        target=path.with_suffix('.json')
        target.write_text(json.dumps(dict(width=595,height=842,rotation=0,rows=[dict(box=[50,50,400,150],text='A useful document Hello world',score=.99)],blocks=[])))
        return target
    monkeypatch.setattr('yuzufile.indra_engine.recognize',english)
    with pymupdf.open(digital_pdf) as doc:
        probe=mapping_probe(doc[0],native_blocks(doc[0]),['ara','eng'])
        assert probe['required'] and not probe['strong']
        out=tmp_path/'english.docx';report=write_word(doc,out,lambda *a,**k:None,performance_profile('low'),['ara','eng'])
    assert 'Hello world.' in '\n'.join(p.text for p in Document(out).paragraphs)
    assert not report['pages'][0]['legacy_arabic_recovered']


def test_normal_arabic_does_not_require_extra_mapping_ocr():
    blocks={'blocks':[{'lines':[{'spans':[{'text':'مرحبا بالعالم'}]}]}]}
    # The short circuit must not even inspect embedded fonts.
    assert not mapping_probe(None,blocks,['ara'])['required']
    assert not confirmed_arabic(dict(rows=[dict(text='عربي',score=.4)]))


def test_invisible_glyphless_ocr_fonts_are_not_script_evidence():
    class InvisiblePage:
        def get_texttrace(self):
            return [dict(font='GlyphLessFont',type=3,chars=[(ord('A'),1,(0,0),(0,0,10,10))]*10)]
        def get_fonts(self,**kwargs):
            pytest.fail('Invisible placeholder glyphs must not trigger font inspection')
    assert not font_conflicts(InvisiblePage())


def test_recovering_only_a_heading_does_not_count_as_a_complete_export(legacy,tmp_path,monkeypatch):
    monkeypatch.setattr('yuzufile.indra_engine.available',lambda:True)
    def heading(path,*args):
        target=recognized(path)
        data=json.loads(target.read_text(encoding='utf-8'));data['rows']=data['rows'][:1]
        target.write_text(json.dumps(data),encoding='utf-8');return target
    monkeypatch.setattr('yuzufile.indra_engine.recognize',heading)
    def failed_recovery(*args):raise RuntimeError('too little text after detailed recovery')
    monkeypatch.setattr('yuzufile.word_detailed_ocr.recover',failed_recovery)
    with pymupdf.open(legacy) as doc,pytest.raises(RuntimeError,match='no incomplete Word'):
        write_word(doc,tmp_path/'incomplete.docx',lambda *a,**k:None,performance_profile('low'),['ara'])
    assert not (tmp_path/'incomplete.docx').exists()


def test_sparse_fast_ocr_uses_detailed_regions_before_export(legacy,tmp_path,monkeypatch):
    monkeypatch.setattr('yuzufile.indra_engine.available',lambda:True)
    def heading(path,*args):
        target=recognized(path);data=json.loads(target.read_text(encoding='utf-8'));data['rows']=data['rows'][:1]
        target.write_text(json.dumps(data),encoding='utf-8');return target
    monkeypatch.setattr('yuzufile.indra_engine.recognize',heading)
    calls=[]
    def detailed(page,primary,scratch,performance,notify):
        calls.append(performance.code)
        data=json.loads(legacy.with_suffix('.ocr-reference.json').read_text(encoding='utf-8'))
        return {**data,'logical_ocr':True,'detailed_ocr':True}
    monkeypatch.setattr('yuzufile.word_detailed_ocr.recover',detailed)
    with pymupdf.open(legacy) as doc:
        report=write_word(doc,tmp_path/'detailed.docx',lambda *a,**k:None,performance_profile('low'),['ara'])
    assert calls==['low'] and 'paddle-legacy-arabic-regions' in report['engines_used']
    assert report['pages'][0]['legacy_visible_text_coverage']>.9


def test_worker_surfaces_actionable_arabic_recovery_errors(monkeypatch,capsys):
    import io
    from yuzufile import worker
    monkeypatch.setattr('yuzufile.native_process.hide_helper_windows',lambda:None)
    monkeypatch.setattr(worker.logging,'disable',lambda *args:None)
    monkeypatch.setattr(worker.sys,'stdin',io.StringIO('{}\n'))
    def failed(request):raise RuntimeError('Word page 3: detailed Arabic OCR could not finish. Try High performance.')
    monkeypatch.setattr(worker,'convert',failed)
    assert worker.main()==1
    event=json.loads(capsys.readouterr().out)
    assert 'Word page 3' in event['error'] and 'High performance' in event['error']


def test_decorative_vector_cover_preserves_appearance_without_bad_hidden_text(tmp_path,monkeypatch):
    monkeypatch.setattr('yuzufile.indra_engine.recognize',lambda *a:pytest.fail('Preserve decorative artwork without inventing a transcription'))
    with pymupdf.open() as doc:
        p=doc.new_page(width=240,height=340)
        for n in range(30):p.draw_rect(pymupdf.Rect(20+n*.5,20+n*.5,220-n*.5,320-n*.5))
        p.insert_text((80,100),'2 s 3 e',render_mode=3)
        path=tmp_path/'cover.docx';report=write_word(doc,path,lambda *a,**k:None,performance_profile('low'),['ara'])
    word=Document(path)
    assert len(word.inline_shapes)==1 and '2 s 3 e' not in '\n'.join(p.text for p in word.paragraphs)
    assert report['pages'][0]['image_only'] and report['warnings']
