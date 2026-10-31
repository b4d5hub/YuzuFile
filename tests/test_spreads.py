import json

import pymupdf
import pytest

from yuzufile.spreads import DIRECTIONS, halves, selected_pages, settings, split_document
from yuzufile.worker import convert
from artifact_helpers import artifact_path


@pytest.fixture
def spread_pdf(tmp_path):
    path = tmp_path / 'spread.pdf'
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=400)
        for point, text in [((40,70),'LEFT TOP'), ((340,70),'RIGHT TOP'),
                            ((40,270),'LEFT BOTTOM'), ((340,270),'RIGHT BOTTOM')]:
            page.insert_text(point, text)
        page.insert_text((40,110), 'HIDDEN LEFT', render_mode=3)
        page.insert_text((340,110), 'HIDDEN RIGHT', render_mode=3)
        document.save(path)
    return path


@pytest.mark.parametrize('direction,first,excluded', [
    ('rl','RIGHT','LEFT'), ('lr','LEFT','RIGHT'),
    ('tb','TOP','BOTTOM'), ('bt','BOTTOM','TOP')])
def test_order_and_opposite_half_text_removal(spread_pdf, direction, first, excluded):
    with pymupdf.open(spread_pdf) as source:
        output, info, warnings = split_document(source, {'direction':direction})
        with output:
            assert len(output)==2
            assert first in output[0].get_text()
            assert excluded not in output[0].get_text()
            assert first not in output[1].get_text() if direction in {'lr','rl'} else excluded in output[1].get_text()
            assert info['output_pages']==2
            if direction in {'lr','rl'}:
                assert 'HIDDEN '+excluded not in output[0].get_text()


@pytest.mark.parametrize('rotation', [0,90,180,270])
@pytest.mark.parametrize('direction', list(DIRECTIONS))
def test_visual_equivalence_with_rotation_and_crop(spread_pdf, rotation, direction):
    with pymupdf.open(spread_pdf) as source:
        source[0].set_cropbox(pymupdf.Rect(20,20,580,380))
        source[0].set_rotation(rotation)
        config=settings({'direction':direction})
        clips=halves(source[0].rect,config)
        expected=[source[0].get_pixmap(clip=clip).samples for clip in clips]
        output,_,_=split_document(source,config)
        with output:
            assert [page.get_pixmap().samples for page in output]==expected


def test_ranges_keep_cover_and_adjust_position(spread_pdf):
    with pymupdf.open(spread_pdf) as source, pymupdf.open() as document:
        for _ in range(3):
            document.insert_pdf(source)
        output, info, _=split_document(document,{'direction':'lr','position':40,'pages':'2-3'})
        with output:
            assert len(output)==5
            assert output[0].rect==document[0].rect
            assert output[1].rect.width==240
            assert output[2].rect.width==360
            assert info['split_pages']==2


def test_scan_pixels_are_preserved(tmp_path):
    from PIL import Image
    import io
    image=Image.effect_noise((600,400),50).convert('RGB')
    stream=io.BytesIO();image.save(stream,format='PNG')
    with pymupdf.open() as source:
        page=source.new_page(width=600,height=400)
        page.insert_image(page.rect,stream=stream.getvalue())
        clips=halves(page.rect,settings({'direction':'rl'}))
        expected=[page.get_pixmap(clip=rect).samples for rect in clips]
        output,_,_=split_document(source,{'direction':'rl'})
        with output:
            assert [p.get_pixmap().samples for p in output]==expected
            assert all(p.get_images() for p in output)


def test_links_bookmarks_and_annotations(spread_pdf):
    with pymupdf.open(spread_pdf) as source:
        source[0].insert_link({'kind':pymupdf.LINK_URI,'from':pymupdf.Rect(20,20,80,40),'uri':'https://example.com'})
        source[0].insert_link({'kind':pymupdf.LINK_GOTO,'from':pymupdf.Rect(350,20,400,40),'page':0,'to':pymupdf.Point(40,60)})
        source[0].add_rect_annot(pymupdf.Rect(30,50,130,80))
        source.set_toc([[1,'Chapter',1]])
        output,_,_=split_document(source,{'direction':'rl'})
        with output:
            # Reopen so inserted links are resolved by the PDF reader.
            with pymupdf.open(stream=output.tobytes(),filetype='pdf') as checked:
                assert checked[0].get_links()[0]['page']==1
                assert checked[1].get_links()[0]['uri']=='https://example.com'
                assert len(list(checked[0].annots() or []))==0
                assert len(list(checked[1].annots() or []))==1
                assert checked.get_toc()==[[1,'Chapter',1]]


@pytest.mark.parametrize('mode', ['split','split_markdown','split_pdf','split_compress','split_all'])
def test_worker_combinations_keep_split_page_count(spread_pdf,tmp_path,mode):
    root=tmp_path/mode
    original=spread_pdf.read_bytes()
    convert({'root':str(root),'source':str(spread_pdf),'mode':mode,'languages':['eng'],
             'compression':'lossless','split_settings':{'direction':'rl'}})
    manifest=json.loads((root/'result/manifest.json').read_text())
    pdf=next(a for a in manifest['artifacts'] if a['kind']=='pdf')
    with pymupdf.open(root/pdf['path']) as document:
        assert len(document)==2
        assert 'RIGHT' in document[0].get_text()
        assert 'LEFT' not in document[0].get_text()
    assert manifest['metadata']['split']['direction']=='rl'
    assert manifest['metadata']['pages']==2
    assert spread_pdf.read_bytes()==original
    if 'markdown' in mode or mode=='split_all':
        markdown=artifact_path(root,'markdown').read_text(encoding='utf-8')
        assert markdown.count('RIGHT TOP')==1
        assert markdown.count('LEFT TOP')==1


@pytest.mark.parametrize('pages', ['0','3-2','1,','-1','1-999999999','1, 2001','hello'])
def test_invalid_ranges(pages):
    with pytest.raises(ValueError):
        selected_pages(pages,5)


@pytest.mark.parametrize('parts',[3,4,12])
@pytest.mark.parametrize('direction',list(DIRECTIONS))
@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_multiple_parts_preserve_pixels_and_order(parts,direction,rotation):
    with pymupdf.open() as source:
        page=source.new_page(width=600,height=600)
        for y in range(0,600,50):
            for x in range(0,600,50):
                page.draw_rect(pymupdf.Rect(x,y,x+50,y+50),fill=(x/600,y/600,.3),color=None)
        page.insert_text((60,60),'Native searchable text')
        page.set_cropbox(pymupdf.Rect(24,24,576,576))
        page.set_rotation(rotation)
        config=settings(dict(direction=direction,parts=parts))
        expected=[page.get_pixmap(clip=clip).samples for clip in halves(page.rect,config)]
        result,info,_=split_document(source,config)
        with result:
            assert len(result)==parts
            assert [p.get_pixmap().samples for p in result]==expected
            assert info['parts']==parts and info['output_pages']==parts


@pytest.mark.parametrize('direction,expected',[('lr',['A','B','C']),('rl',['C','B','A']),
                                             ('tb',['A','B','C']),('bt',['C','B','A'])])
def test_three_parts_remove_other_sections_hidden_text(direction,expected):
    with pymupdf.open() as source:
        page=source.new_page(width=600,height=600)
        for n,text in enumerate(['A','B','C']):
            point=(n*200+40,70) if direction in {'lr','rl'} else (40,n*200+70)
            page.insert_text(point,'HIDDEN SECTION '+text,render_mode=3)
        output,_,_=split_document(source,dict(direction=direction,parts=3))
        with output:
            assert [p.get_text().strip() for p in output]==['HIDDEN SECTION '+s for s in expected]


@pytest.mark.parametrize('parts',[0,1,13,2.5,'3',True,None])
def test_invalid_part_counts(parts):
    with pytest.raises(ValueError,match='parts per page'):
        settings(dict(parts=parts))


def test_multiple_parts_only_apply_to_selected_pages(spread_pdf):
    with pymupdf.open(spread_pdf) as original,pymupdf.open() as source:
        for _ in range(3):source.insert_pdf(original)
        output,info,_=split_document(source,dict(parts=3,pages='2'))
        with output:
            assert len(output)==5 and info['split_pages']==1
            assert output[0].rect==source[0].rect and output[-1].rect==source[-1].rect


def test_output_limit_checked_before_copying():
    with pymupdf.open() as source:
        for _ in range(334):source.new_page()
        with pytest.raises(ValueError,match='4,000'):
            split_document(source,dict(parts=12))


def test_multi_part_preview_count_and_equal_dividers(spread_pdf,store):
    from PySide6.QtWidgets import QApplication
    from yuzufile.ui import Window,CompressionBox
    from yuzufile.spread_preview import SpreadPreview
    app=QApplication.instance() or QApplication([])
    parent=Window(store);parent.timer.stop()
    dialog=SpreadPreview(parent,[spread_pdf],settings(dict(parts=3,direction='rl')),CompressionBox)
    dialog.show();app.processEvents()
    assert '3 output pages' in dialog.status.text()
    assert dialog.canvas.config['parts']==3
    assert not dialog.position.isVisible()
    assert dialog.cut_selector.count()==2
    dialog.parts.setValue(4);app.processEvents()
    assert '4 output pages' in dialog.status.text()
    assert dialog.config()['parts']==4
    dialog.parts.setValue(2);app.processEvents()
    assert not dialog.position.isVisible()
    dialog.reject();parent.deleteLater()


def test_multi_part_history_retry_restores_count(spread_pdf,store):
    from PySide6.QtWidgets import QApplication
    from yuzufile.ui import Window
    app=QApplication.instance() or QApplication([])
    window=Window(store);window.timer.stop()
    job=store.create(spread_pdf,'split',[],split_settings=dict(parts=4,direction='bt'))
    window.retry_job(job)
    assert window.split_parts.value()==4
    assert window.current_split_settings()['parts']==4
    window.deleteLater()


@pytest.mark.parametrize('mode',['split','split_markdown','split_all'])
def test_worker_three_sections_then_markdown_and_compression(tmp_path,mode,monkeypatch):
    # Exercise fresh OCR with the bundled lightweight fallback; this test checks
    # split ordering and outputs, independently of neural model initialization.
    monkeypatch.setattr('yuzufile.indra_engine.available',lambda:False)
    monkeypatch.setattr('yuzufile.neural_text.available',lambda:False)
    monkeypatch.setattr('yuzufile.vision_runtime.available',lambda:False)
    source=tmp_path/'three sections.pdf'
    with pymupdf.open() as doc:
        page=doc.new_page(width=900,height=300)
        for n,text in enumerate(['FIRST SECTION','SECOND SECTION','THIRD SECTION']):
            page.insert_text((40+300*n,80),text,fontsize=16)
        doc.save(source)
    original=source.read_bytes()
    root=tmp_path/mode
    convert(dict(root=str(root),source=str(source),mode=mode,languages=[] if mode=='split' else ['eng'],compression='lossless',
                 split_settings=dict(direction='rl',parts=3)))
    manifest=json.loads((root/'result/manifest.json').read_text())
    artifact=next(a for a in manifest['artifacts'] if a['kind']=='pdf')
    with pymupdf.open(root/artifact['path']) as doc:
        assert [p.get_text().strip() for p in doc]==['THIRD SECTION','SECOND SECTION','FIRST SECTION']
    assert manifest['metadata']['split']['parts']==3
    if mode!='split':
        text=artifact_path(root,'markdown').read_text(encoding='utf-8')
        assert text.index('THIRD SECTION')<text.index('SECOND SECTION')<text.index('FIRST SECTION')
    assert source.read_bytes()==original


def test_preview_line_and_count(spread_pdf,store):
    from PySide6.QtCore import Qt,QPoint
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from yuzufile.ui import Window,CompressionBox
    from yuzufile.spread_preview import SpreadPreview
    app=QApplication.instance() or QApplication([])
    parent=Window(store);parent.timer.stop()
    dialog=SpreadPreview(parent,[spread_pdf],settings({'direction':'rl'}),CompressionBox)
    dialog.show();app.processEvents()
    assert dialog.position.isHidden()
    assert dialog.page.lineEdit().width()>30
    assert '2 output pages' in dialog.status.text()
    rect=dialog.canvas.page_rect
    start=dialog.canvas.handle_rects()[0].center().toPoint()
    target=QPoint(int(rect.left()+rect.width()*.75),start.y())
    QTest.mousePress(dialog.canvas,Qt.MouseButton.LeftButton,pos=start)
    QTest.mouseMove(dialog.canvas,target)
    QTest.mouseRelease(dialog.canvas,Qt.MouseButton.LeftButton,pos=target)
    assert abs(dialog.position.value()-75)<1
    dialog.ranges.setText('2')
    assert not dialog.apply.isEnabled()
    dialog.reject()
    assert dialog.document is None
    parent.deleteLater()


def test_scan_split_then_real_ocr_preserves_order(spread_pdf,tmp_path,store):
    import time
    from yuzufile.supervisor import Supervisor
    scanned=tmp_path/'scanned spread.pdf'
    with pymupdf.open(spread_pdf) as original, pymupdf.open() as document:
        image=original[0].get_pixmap(matrix=pymupdf.Matrix(2,2))
        page=document.new_page(width=600,height=400)
        page.insert_image(page.rect,pixmap=image)
        document.save(scanned)
    job=store.create(scanned,'split_pdf',['eng'],split_settings={'direction':'rl'})
    supervisor=Supervisor(store)
    deadline=time.monotonic()+120
    try:
        while store.get(job)['state'] in {'queued','running'}:
            supervisor.tick()
            assert time.monotonic()<deadline
            time.sleep(.05)
        assert store.get(job)['state']=='succeeded',store.get(job)['error']
        with pymupdf.open(artifact_path(store.job_dir(job),'pdf')) as document:
            assert len(document)==2
            assert 'RIGHT' in document[0].get_text().upper()
            assert 'LEFT' not in document[0].get_text().upper()
            assert 'LEFT' in document[1].get_text().upper()
    finally:
        supervisor.shutdown()
