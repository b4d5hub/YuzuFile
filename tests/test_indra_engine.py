"""Indra boundary, orientation, preservation and failure contracts."""
import json
from types import SimpleNamespace

import pymupdf
import pytest
from yuzufile import indra_engine
from yuzufile.performance import performance_profile


def test_tables_and_uncertain_lines_request_detailed_review():
    assert indra_engine.needs_review(dict(blocks=[dict(label='Table')]))
    assert indra_engine.needs_review(dict(markdown='<table>data</table>'))
    assert indra_engine.needs_review(dict(rows=[dict(text='Uncertain diagram labels',score=.4)]))
    assert not indra_engine.needs_review(dict(rows=[dict(text='Reliable ordinary text',score=.99)]))


def test_html_table_cells_do_not_trigger_duplicate_text_recovery():
    from yuzufile.neural_markdown import missing_rows
    rows=[dict(text='Books 12 57.00',score=.99)]
    html='<table><tr><td>Books</td><td>12</td><td>57.00</td></tr></table>'
    assert missing_rows(rows,indra_engine.coverage_text(html)) == []


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_arabic_overlay_uses_standard_unicode_and_is_searchable(tmp_path,rotation):
    from yuzufile.neural_text import add_invisible_text
    path=tmp_path/'arabic.json'
    text='مرحبا بالعالم'
    path.write_text(json.dumps(dict(width=400,height=100,rotation=rotation,
        rows=[dict(box=[10,10,350,50],text=text,score=1)])))
    with pymupdf.open() as doc:
        page=doc.new_page(width=400 if rotation in (0,180) else 100,
                          height=100 if rotation in (0,180) else 400)
        before=page.get_pixmap().samples
        add_invisible_text(page,path)
        with pymupdf.open(stream=doc.tobytes(),filetype='pdf') as saved:
            assert text in saved[0].get_text()
            assert saved[0].search_for(text)
            assert saved[0].get_pixmap().samples==before


def test_arabic_cmap_normalization_keeps_ids_latin_and_is_idempotent():
    from yuzufile.unicode_overlay import normalize_cmap
    original='''1 beginbfrange
<0003> <0004> <fe8d>
endbfrange
2 beginbfchar
<0005> <FEFB>
<0006> <00e7>
endbfchar'''
    result=normalize_cmap(original)
    assert '<0003> <0004> [<0627> <0627>]' in result
    assert '<0005> <06440627>' in result
    assert '<0006> <00e7>' in result
    assert normalize_cmap(result)==result


def test_arabic_vowels_and_mixed_latin_survive_searchable_pdf(tmp_path):
    from yuzufile.neural_text import add_invisible_text
    from pathlib import Path
    import os
    if not (Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts/arial.ttf').is_file():
        pytest.skip('Windows Arabic font integration')
    text='الْعَقِيدَةُ الْوَاسِطِيَّةُ'
    latin='French: élève - https://example.org/a-b'
    path=tmp_path/'vowelled.json'
    path.write_text(json.dumps(dict(width=500,height=160,rows=[
        dict(box=[30,10,460,55],text=text),
        dict(box=[30,90,460,120],text=latin)])))
    with pymupdf.open() as doc:
        page=doc.new_page(width=500,height=160)
        before=page.get_pixmap().samples
        assert add_invisible_text(page,path)
        with pymupdf.open(stream=doc.tobytes(),filetype='pdf') as saved:
            extracted=saved[0].get_text()
            assert '\x00' not in extracted
            assert text in extracted
            assert latin in extracted
            assert saved[0].search_for(text)
            assert saved[0].get_pixmap().samples==before


def test_incomplete_models_never_trigger_download(tmp_path, monkeypatch):
    monkeypatch.setattr(indra_engine, 'model_root', lambda: tmp_path)
    (tmp_path/'indra').mkdir()
    (tmp_path/'indra/ready.json').write_text('{}')
    assert not indra_engine.available()
    with pytest.raises(RuntimeError, match='complete offline'):
        indra_engine.Reader(1)


def test_cpu_only_explicit_local_path_and_bounded_threads(monkeypatch):
    import indra_ocr
    calls=[]
    monkeypatch.setattr(indra_engine, 'available', lambda: True)
    monkeypatch.setattr(indra_ocr, 'load', lambda **kw: calls.append(kw))
    indra_engine.Reader(100)
    assert calls[0]['threads'] == 4
    assert calls[0]['providers'] == ['CPUExecutionProvider']
    assert calls[0]['path'] == indra_engine.model_root()/'indra'
    assert calls[0]['furniture'] is True


@pytest.mark.parametrize('rotation', [0,90,180,270])
def test_overlay_rotation_preserves_pixels_and_text(tmp_path, rotation):
    from yuzufile.neural_text import add_invisible_text
    path=tmp_path/'ocr.json'
    width,height=(120,200) if rotation in (90,270) else (200,120)
    path.write_text(json.dumps(dict(width=width,height=height,rotation=rotation,
        rows=[dict(box=[10,10,100,30],text='Exact text',score=.99)])))
    with pymupdf.open() as doc:
        page=doc.new_page(width=200,height=120)
        before=page.get_pixmap().samples
        assert add_invisible_text(page,path)
        assert 'Exact text' in page.get_text()
        assert page.get_pixmap().samples == before
        word=page.search_for('Exact text')[0]
        if rotation==0: assert word.x0<20 and word.y0<20
        if rotation==90: assert word.x0>160 and word.y0<20
        if rotation==180: assert word.x0>90 and word.y0>80
        if rotation==270: assert word.x0<30 and word.y0>10
    assert not path.with_suffix('.upright.json').exists()


def test_reader_preserves_mixed_scripts_and_upright_dimensions(tmp_path):
    from PIL import Image
    folder=tmp_path/'français مرحبا';folder.mkdir()
    path=folder/'page.png'
    Image.new('RGB',(200,120),'white').save(path)
    reader=indra_engine.Reader.__new__(indra_engine.Reader)
    line=SimpleNamespace(box=[1,2,110,30],text='Hello français مرحبا',conf=.98)
    result=SimpleNamespace(rotation=90,lines=[line],source='ocr',markdown='# Title',blocks=[],timings={})
    reader.converter=SimpleNamespace(ocr=lambda gray:result)
    data=reader.read(path)
    assert (data['width'],data['height']) == (120,200)
    assert data['rows'][0]['text'] == line.text


def test_markdown_reuses_ocr_and_keeps_missing_text_and_figures(tmp_path, monkeypatch):
    scratch=tmp_path/'scratch';scratch.mkdir()
    data=dict(width=200,height=120,rotation=0,engine=indra_engine.ENGINE,
        markdown='# Report\n\n![](picture-0)', rows=[dict(text='Missing label 57%',score=.99)],
        blocks=[dict(label='Picture',bbox=[20,40,80,90])])
    (scratch/'indra-page-1.json').write_text(json.dumps(data))
    monkeypatch.setattr(indra_engine,'recognize',lambda *args:pytest.fail('Should reuse OCR'))
    target=tmp_path/'out.md'
    with pymupdf.open() as doc:
        page=doc.new_page(width=200,height=120)
        page.insert_text((20,20),'Existing native text')
        page.draw_rect(pymupdf.Rect(20,40,80,90),fill=(1,0,0))
        warnings=indra_engine.write_markdown(doc,target,lambda *a,**kw:None,performance_profile('low'),['eng'])
    text=target.read_text()
    assert 'Missing label 57%' in text and 'Existing native text' in text
    assert '(assets/indra-1-0.png)' in text and '(picture-' not in text
    assert (tmp_path/'assets/indra-1-0.png').is_file()
    assert warnings


def test_failed_indra_markdown_uses_existing_engine_and_moves_assets(tmp_path, monkeypatch):
    monkeypatch.setattr(indra_engine,'recognize',lambda *a: (_ for _ in ()).throw(RuntimeError('offline failure')))
    def existing(doc,path,*args,**kw):
        assert kw['use_indra'] is False
        assert (path.parent/'scratch').is_dir()
        assets=path.parent/'assets';assets.mkdir()
        (assets/'figure.png').write_bytes(b'figure')
        path.write_text('Fallback text\n![](assets/figure.png)')
        return []
    monkeypatch.setattr('yuzufile.engines.write_markdown',existing)
    with pymupdf.open() as doc:
        doc.new_page()
        warnings=indra_engine.write_markdown(doc,tmp_path/'out.md',lambda *a,**kw:None,performance_profile('low'),['eng'])
    text=(tmp_path/'out.md').read_text()
    assert 'Fallback text' in text and '(assets/fallback-1-figure.png)' in text
    assert (tmp_path/'assets/fallback-1-figure.png').is_file()
    assert len(warnings)==1


def test_failed_indra_ocr_retains_rapid_fallback(tmp_path,monkeypatch):
    from yuzufile import engines
    monkeypatch.setattr(indra_engine,'available',lambda:True)
    monkeypatch.setattr(indra_engine,'recognize',lambda *a:(_ for _ in ()).throw(RuntimeError('failed')))
    monkeypatch.setattr('yuzufile.neural_text.available',lambda:True)
    expected=tmp_path/'ocr.json'
    monkeypatch.setattr('yuzufile.neural_text.recognize',lambda *a:expected)
    image=tmp_path/'page.png'
    assert engines.recognize_page(image,220,['eng'],1)==expected
    assert image.with_suffix('.indra-fallback.txt').exists()


def test_table_page_routes_to_detailed_pipeline(tmp_path,monkeypatch):
    scratch=tmp_path/'scratch';scratch.mkdir()
    data=dict(width=200,height=120,rotation=0,engine=indra_engine.ENGINE,
        markdown='<table>Uncertain columns</table>',rows=[],blocks=[dict(label='Table')])
    (scratch/'indra-page-1.json').write_text(json.dumps(data))
    monkeypatch.setattr('yuzufile.vision_runtime.available',lambda:True)
    calls=[]
    def detailed(doc,path,*args,**kw):
        assert (path.parent/'scratch').is_dir()
        calls.append(kw['use_indra'])
        path.write_text('Verified table columns')
        (path.parent/'scratch/markdown-engines.json').write_text('["lighton", "paddle"]')
        return []
    monkeypatch.setattr('yuzufile.engines.write_markdown',detailed)
    with pymupdf.open() as doc:
        doc.new_page()
        indra_engine.write_markdown(doc,tmp_path/'out.md',lambda *a,**kw:None,performance_profile('low'),['eng'])
    assert calls == [False]
    assert (tmp_path/'out.md').read_text().strip() == 'Verified table columns'
    used=json.loads((scratch/'markdown-engines.json').read_text())
    assert {'indra-ocr-1.1.2','lighton','paddle'} <= set(used)
