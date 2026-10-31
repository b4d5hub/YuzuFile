import json
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

import pymupdf
import pytest
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from yuzufile.cleanup import settings,transform_page,clean_document,edit_for
from yuzufile.cleanup_preview import CleanupPreview
from yuzufile.spreads import settings as split_settings,halves,split_document
from yuzufile.spread_preview import SpreadPreview
from yuzufile.ui import Window,CompressionBox
from yuzufile.worker import convert
from artifact_helpers import artifact_path


@pytest.fixture
def view(store,monkeypatch):
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr('yuzufile.ui.installed_languages',lambda:['eng'])
    window=Window(store);window.timer.stop()
    yield window
    window.supervisor.shutdown();window.deleteLater();app.processEvents()


def manual(path,edit,**kw):
    return settings(dict(straighten=False,trim=True,visual={'files':{str(path):{'edits':{'1':edit}}}},**kw))


def test_manual_crop_removes_intended_text_and_matches_preview(tmp_path):
    source=tmp_path/'source.pdf'
    with pymupdf.open() as doc:
        page=doc.new_page(width=600,height=800)
        page.insert_text((100,160),'KEEP THIS TEXT')
        page.insert_text((100,720),'REMOVE THIS FOOTER')
        doc.save(source)
    original=source.read_bytes()
    config=manual(source,{'crop':[.1,.1,.9,.7]})
    with pymupdf.open(source) as doc:
        preview,detail,_=transform_page(doc,0,config,preview_uncropped=True)
        actual,export,_=transform_page(doc,0,config)
        with preview,actual:
            assert 'REMOVE' in preview[0].get_text()
            assert 'REMOVE' not in actual[0].get_text()
            assert 'KEEP THIS TEXT' in actual[0].get_text()
            assert export['output_size']==pytest.approx((480,480))
            assert detail['crop']==pytest.approx((.1,.1,.9,.7))
            assert actual[0].rect.width==pytest.approx(detail['output_size'][0])
    assert source.read_bytes()==original


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_visual_rotation_preserves_native_text_and_geometry(digital_pdf,rotation):
    config=manual(digital_pdf,{'rotation':rotation,'crop':[0,0,1,1]})
    with pymupdf.open(digital_pdf) as source:
        out,detail,_=transform_page(source,0,config)
        with out:
            expected=(source[0].rect.height,source[0].rect.width) if rotation%180 else (source[0].rect.width,source[0].rect.height)
            assert (out[0].rect.width,out[0].rect.height)==pytest.approx(expected)
            assert 'Hello world' in out[0].get_text()
            assert not out[0].get_images()


@pytest.mark.parametrize('initial',[0,90,180,270])
@pytest.mark.parametrize('extra',[0,90,180,270])
def test_combined_visual_geometry_retains_link_positions(tmp_path,initial,extra):
    source=tmp_path/'linked.pdf'
    with pymupdf.open() as doc:
        p=doc.new_page(width=600,height=800);p.insert_text((150,200),'LINKED TEXT')
        p.insert_link({'kind':pymupdf.LINK_URI,'uri':'https://example.org','from':p.search_for('LINKED TEXT')[0]})
        p.set_cropbox(pymupdf.Rect(30,40,570,760));p.set_rotation(initial);doc.save(source)
    config=manual(source,dict(rotation=extra,angle=3,crop=[.05,.05,.95,.95]))
    with pymupdf.open(source) as doc:
        output,_,warnings=clean_document(doc,config,tmp_path)
        with output:
            text=output[0].search_for('LINKED TEXT')[0]
            link=output[0].get_links()[0]['from']
            assert (text & link).get_area()/text.get_area()>.98
            assert not warnings


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_bookmark_and_internal_link_share_exact_cropped_destination(tmp_path,rotation):
    source=tmp_path/'navigation.pdf'
    with pymupdf.open() as doc:
        for _ in range(2):
            p=doc.new_page(width=600,height=800);p.insert_text((150,200),'DESTINATION')
            p.set_cropbox(pymupdf.Rect(30,40,570,760))
        doc[0].insert_link({'kind':pymupdf.LINK_GOTO,'from':pymupdf.Rect(80,100,180,130),
                            'page':1,'to':pymupdf.Point(120,160)})
        link=doc.reload_page(doc[0]).get_links()[0]
        doc.set_toc([[1,'Destination',2]])
        # Give the input outline and link identical PDF-space destinations.
        action=doc.xref_get_key(link['xref'],'A')[1]
        doc.xref_set_key(doc.get_outline_xrefs()[0],'A',action)
        doc[0].set_rotation(270);doc[1].set_rotation(rotation);doc.save(source)
    config=settings(dict(straighten=False,visual={'files':{str(source):{
        'pages':'2','edits':{'2':dict(rotation=90,angle=3,crop=[.05,.05,.95,.95])}}}}))
    with pymupdf.open(source) as doc:
        old=doc[0].get_links()[0]
        assert old['to'].distance_to(doc.get_toc(False)[0][3]['to'])<.01
        result,_,warnings=clean_document(doc,config,tmp_path)
        with result:result.save(tmp_path/'result.pdf')
    with pymupdf.open(tmp_path/'result.pdf') as result:
        link=result[0].get_links()[0]
        assert link['to'].distance_to(result.get_toc(False)[0][3]['to'])<.01
        assert tuple(link['from'])==pytest.approx(tuple(old['from']),abs=.01)
        assert result[0].rotation==270
        assert not warnings


def test_visual_file_scope_and_worker_original_path(tmp_path):
    source=tmp_path/'original.pdf'
    with pymupdf.open() as doc:
        for _ in range(2):
            p=doc.new_page(width=600,height=800);p.insert_text((100,200),'KEEP')
        doc.save(source)
    config=manual(source,{'crop':[.1,.1,.9,.9]})
    config['visual']['files'][str(source)]['pages']='1'
    convert(dict(root=str(tmp_path/'job'),source=str(source),mode='cleanup',languages=[],cleanup_settings=config))
    with pymupdf.open(artifact_path(tmp_path/'job','pdf')) as doc:
        assert doc[0].rect.width==pytest.approx(480)
        assert doc[1].rect.width==pytest.approx(600)
    assert edit_for(config,tmp_path/'other.pdf',0)=={}


@pytest.mark.parametrize('edit',[{'crop':[-.1,0,1,1]},{'crop':[.5,0,.4,1]}, {'crop':[0,0,float('nan'),1]},
                                  {'angle':46},{'angle':True},{'rotation':45}])
def test_invalid_visual_edits_rejected(digital_pdf,edit):
    with pytest.raises(ValueError):manual(digital_pdf,edit)


def test_drag_crop_undo_redo_and_history(view,digital_pdf):
    preview=CleanupPreview(view,[digital_pdf],settings({'straighten':False}),CompressionBox)
    preview.show();QApplication.processEvents()
    try:
        preview.edit_view.fit_page();QApplication.processEvents()
        original=preview.before.crop[:]
        x,y=preview.before.handles()['se']
        target=QPoint(int(x-35),int(y-18))
        QTest.mousePress(preview.before,Qt.MouseButton.LeftButton,pos=QPoint(round(x),round(y)))
        QTest.mouseMove(preview.before,target)
        QTest.mouseRelease(preview.before,Qt.MouseButton.LeftButton,pos=target)
        preview.render_page()
        crop=preview.before.crop[:]
        assert crop[2]<original[2] and crop[3]<original[3]
        assert preview.detail['manual_crop']
        preview.undo();assert preview.before.crop==pytest.approx(original)
        preview.redo();assert preview.before.crop==pytest.approx(crop)
        config=preview.config()
        job=view.store.create(digital_pdf,'cleanup',[],cleanup_settings=config)
        view.retry_job(job)
        assert view.current_cleanup_settings()['visual']==config['visual']
        assert view.cleanup_padding.isHidden() and view.cleanup_ranges.isHidden()
    finally:preview.reject()


def test_alignment_guide_rotation_and_batch_copy(view,digital_pdf,tmp_path):
    second=tmp_path/'second.pdf';second.write_bytes(digital_pdf.read_bytes())
    preview=CleanupPreview(view,[digital_pdf,second],settings({'straighten':False}),CompressionBox)
    preview.show();QApplication.processEvents()
    try:
        preview.tool('straighten');r=preview.before.fit_rect()
        start=QPoint(int(r.left()+r.width()*.15),int(r.top()+r.height()*.4))
        end=QPoint(start.x()+180,start.y()+12)
        QTest.mousePress(preview.before,Qt.MouseButton.LeftButton,pos=start)
        QTest.mouseMove(preview.before,end)
        QTest.mouseRelease(preview.before,Qt.MouseButton.LeftButton,pos=end)
        preview.render_page()
        assert 3<preview.detail['angle_degrees']<5
        assert not preview.config()['straighten']  # a manual page edit must not enable auto deskew globally
        preview.rotate(90);preview.render_page();assert preview.detail['rotation']==90
        preview.apply_edit_to('batch');preview.render_page()
        config=preview.config();assert config['visual']['default']['rotation']==90
        preview.files.setCurrentIndex(1)
        assert preview.detail['rotation']==90
    finally:preview.reject()


def test_zoom_pan_keeps_crop_geometry_and_fit_resets_view(view,digital_pdf):
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QWheelEvent
    preview=CleanupPreview(view,[digital_pdf],settings({'straighten':False}),CompressionBox)
    preview.show();QApplication.processEvents()
    try:
        canvas=preview.before;viewport=preview.edit_view;crop=canvas.crop[:];original=canvas.fit_rect()
        point=canvas.mapFrom(viewport.viewport(),viewport.viewport().rect().center())
        event=QWheelEvent(QPointF(point),QPointF(point),QPoint(),QPoint(0,120),Qt.MouseButton.NoButton,
                          Qt.KeyboardModifier.ControlModifier,Qt.ScrollPhase.NoScrollPhase,False)
        QApplication.sendEvent(canvas,event)
        assert viewport.mode=='manual' and canvas.fit_rect().width()>original.width()
        initial=viewport.horizontalScrollBar().value()
        QTest.keyPress(canvas,Qt.Key.Key_Space)
        QTest.mousePress(canvas,Qt.MouseButton.LeftButton,pos=point)
        QTest.mouseMove(canvas,point+QPoint(20,15))
        QTest.mouseRelease(canvas,Qt.MouseButton.LeftButton,pos=point+QPoint(20,15))
        QTest.keyRelease(canvas,Qt.Key.Key_Space)
        assert viewport.horizontalScrollBar().value()!=initial and canvas.crop==crop
        canvas.fit_view();assert viewport.mode=='width'
    finally:preview.reject()


def test_page_thumbnail_scope_blocks_empty_selection(view,tmp_path):
    source=tmp_path/'pages.pdf'
    with pymupdf.open() as doc:
        for _ in range(3):doc.new_page()
        doc.save(source)
    preview=CleanupPreview(view,[source],settings({'straighten':False}),CompressionBox)
    try:
        preview.scope.setCurrentIndex(1)
        preview.thumbnails.clearSelection();preview.render_page();assert not preview.apply.isEnabled()
        preview.thumbnails.item(1).setSelected(True);preview.render_page()
        assert preview.apply.isEnabled()
        assert preview.config()['visual']['files'][str(source)]['pages']=='2'
        assert preview.detail is None  # page 1 is outside processing scope
        preview.page.setValue(2);assert preview.detail['page']==2
    finally:preview.reject()


@pytest.mark.parametrize('direction',['lr','rl','tb','bt'])
def test_unequal_multiple_splits_cover_page_once(direction):
    config=split_settings(dict(parts=3,direction=direction,cuts=[20,65]))
    rects=halves((0,0,600,800),config)
    assert sum(r.get_area() for r in rects)==pytest.approx(600*800)
    sizes=[r.width if direction in {'lr','rl'} else r.height for r in rects]
    expected=[.2,.45,.35]
    if direction in {'rl','bt'}:expected.reverse()
    dimension=600 if direction in {'lr','rl'} else 800
    assert sizes==pytest.approx([dimension*f for f in expected])


@pytest.mark.parametrize('cuts',[[50],[20,20],[80,30],[-2,70],[20,100],[True,60],[20,float('inf')]])
def test_invalid_multiple_cuts(cuts):
    with pytest.raises(ValueError):split_settings(dict(parts=3,cuts=cuts))


def test_multiple_dividers_drag_export_and_retry(view,tmp_path):
    source=tmp_path/'spread.pdf'
    with pymupdf.open() as doc:
        p=doc.new_page(width=600,height=400)
        for x,text in ((40,'FIRST'),(200,'SECOND'),(470,'THIRD')):p.insert_text((x,100),text)
        doc.save(source)
    preview=SpreadPreview(view,[source],split_settings({'parts':3}),CompressionBox)
    preview.show();QApplication.processEvents()
    try:
        r=preview.canvas.page_rect
        for index,fraction in enumerate((.2,.7)):
            start=preview.canvas.handle_rects()[index].center().toPoint()
            target=QPoint(int(r.left()+r.width()*fraction),start.y())
            QTest.mousePress(preview.canvas,Qt.MouseButton.LeftButton,pos=start)
            QTest.mouseMove(preview.canvas,target)
            QTest.mouseRelease(preview.canvas,Qt.MouseButton.LeftButton,pos=target)
        config=preview.config();assert config['cuts']==pytest.approx([20,70],abs=.5)
        with pymupdf.open(source) as doc:
            output,_,_=split_document(doc,config)
            with output:assert [p.get_text().strip() for p in output]==['FIRST','SECOND','THIRD']
        job=view.store.create(source,'split',[],split_settings=config);view.retry_job(job)
        assert view.current_split_settings()['cuts']==config['cuts']
    finally:preview.reject()
