import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pymupdf
import pytest
from PySide6.QtCore import Qt,QPoint
from PySide6.QtWidgets import QApplication
from yuzufile.organize_ui import OrganizeDialog
from yuzufile.page_preview import PagePreview
from yuzufile.cleanup_preview import CleanupPreview
from yuzufile.cleanup import settings
from yuzufile.ui import CompressionBox


@pytest.fixture
def pages(tmp_path):
    app=QApplication.instance() or QApplication([])
    path=tmp_path/'Readable pages.pdf'
    with pymupdf.open() as doc:
        for number in range(6):
            p=doc.new_page(width=600,height=800);p.insert_text((45,75),f'Page {number+1}')
        doc.save(path)
    return app,path


def test_crop_views_use_full_width_and_zoom_never_changes_edits(pages):
    app,path=pages;original=path.read_bytes()
    view=CleanupPreview(None,[path],settings({'straighten':False,'trim':True}),CompressionBox)
    view.show();app.processEvents()
    try:
        assert view.edit_view.width()>view.width()*.9
        assert not view.result_view.isVisible()
        crop=view.before.crop[:];config=view.config()
        view.edit_view.set_zoom(2);view.render_raster()
        view.edit_view.verticalScrollBar().setValue(100)
        y=view.edit_view.verticalScrollBar().value()
        view.render_page()
        assert view.edit_view.verticalScrollBar().value()==y
        assert view.before.crop==crop and view.config()==config
        view.show_view(1);view.render_raster();app.processEvents()
        assert view.result_view.isVisible() and not view.edit_view.isVisible()
        assert view.result_view.width()>view.width()*.9
        assert view.after.pixmap.width()*view.after.pixmap.height()<=8_020_000
        view.show_view(0);assert view.edit_view.zoom==pytest.approx(2)
    finally:view.reject()
    assert view.preview_document is None and not view.raster_timer.isActive()
    assert path.read_bytes()==original


def test_reader_uses_output_order_and_does_not_accumulate_rotation(pages):
    app,path=pages;dialog=OrganizeDialog(None,[path])
    plan=dialog.entries();plan=[{**plan[4],'rotation':90},plan[1],plan[0]]
    view=PagePreview(dialog,dialog.sources,plan)
    view.show();app.processEvents()
    try:
        assert 'Page 5' in view.pdf_page.get_text()
        assert view.pdf_page.rect.width==800
        view.show_page(1);assert 'Page 2' in view.pdf_page.get_text()
        view.show_page(0);assert view.pdf_page.rotation==90
        assert view.pdf_page.rect.width==800
        view.view.set_zoom(3);view.render()
        assert view.canvas.pixmap.width()*view.canvas.pixmap.height()<=8_020_000
        assert not view.previous.isEnabled() and view.next.isEnabled()
    finally:view.reject();dialog.reject()
    assert view.document is None and not view.timer.isActive()


def test_thumbnail_resize_and_before_after_targets_preserve_page_plan(pages):
    app,path=pages;view=OrganizeDialog(None,[path]);view.show();app.processEvents()
    try:
        original=view.entries();view.grid.item(1).setSelected(True)
        view.page_size.setValue(270);app.processEvents()
        assert view.grid.iconSize().width()==270 and view.entries()==original and view.selected()==[1]
        rect=view.grid.visualItemRect(view.grid.item(0))
        assert view.grid.insertion_target(QPoint(rect.left()+10,rect.center().y()))==0
        assert view.grid.insertion_target(QPoint(rect.right()-10,rect.center().y()))==1
        view.move_to(0,[4,5])
        assert [p['page'] for p in view.entries()]==[4,5,0,1,2,3]
        assert view.grid.landed=={0,1} and 'Moved' in view.message.text()
        assert view.selected()==[0,1]
        count=len(view.undo_stack);view.move_to(0)
        assert len(view.undo_stack)==count and 'already' in view.message.text()
        view.undo();assert view.entries()==original and not view.grid.landed
        # Paint the custom insertion marker and landing delegate offscreen.
        view.grid.target=2;assert not view.grid.grab().isNull()
        view.move_to(6,[0]);assert not view.grid.grab().isNull()
    finally:view.reject()
    assert not view.feedback_timer.isActive()


def test_drag_ghost_and_cancel_restore_visible_cards(pages,monkeypatch):
    app,path=pages;view=OrganizeDialog(None,[path]);view.show();app.processEvents()
    view.grid.item(0).setSelected(True);view.grid.item(1).setSelected(True)
    seen={}
    class Drag:
        def __init__(self,source):seen['source']=source
        def setMimeData(self,data):assert data is not None
        def setPixmap(self,pixmap):seen['ghost']=pixmap
        def setHotSpot(self,point):pass
        def exec(self,action):
            assert view.grid.dragging and view.grid.dragged_rows==[0,1]
            view.grid.target=3;assert not view.grid.grab().isNull()
            return Qt.DropAction.IgnoreAction
    monkeypatch.setattr('yuzufile.page_grid.QDrag',Drag)
    try:
        before=view.entries();view.grid.startDrag(Qt.DropAction.MoveAction)
        assert not seen['ghost'].isNull() and seen['ghost'].width()>=190
        assert not view.grid.dragging and view.grid.target is None
        assert view.entries()==before and 'cancelled' in view.message.text()
    finally:view.reject()


@pytest.mark.parametrize('size',[(840,595),(595,842)])
def test_page_image_fills_card_and_caption_does_not_grow(pages,size):
    app,path=pages
    with pymupdf.open() as doc:
        page=doc.new_page(width=size[0],height=size[1])
        page.draw_rect(page.rect,fill=(.1,.65,.85),color=None)
        doc.save(path.parent/'Color sample.pdf')
    view=OrganizeDialog(None,[path.parent/'Color sample.pdf']);view.show();app.processEvents()
    try:
        from yuzufile.page_grid import ASPECT_ROLE
        item=view.grid.item(0);index=view.grid.model().index(0,0);delegate=view.grid.itemDelegate()
        view.timer.stop();view.render_thumbnail();app.processEvents()
        rect=view.grid.visualItemRect(item);image_rect=delegate.image_rect(rect,index)
        assert image_rect.width()==pytest.approx(300,abs=2)
        assert image_rect.height()/image_rect.width()==pytest.approx(size[1]/size[0])
        assert image_rect.width()>rect.width()*.93
        assert image_rect.height()>rect.height()*.76
        view.grid.landed={0};item.setSelected(True)
        screenshot=view.grid.viewport().grab().toImage();dpr=screenshot.devicePixelRatio()
        for x in (image_rect.left()+4,image_rect.right()-4):
            for y in (image_rect.top()+4,image_rect.center().y()):
                color=screenshot.pixelColor(round(x*dpr),round(y*dpr))
                assert color.blue()>180 and color.red()<70
        caption_height=rect.height()-image_rect.height()
        view.page_size.setValue(460);app.processEvents();view.timer.stop();view.render_thumbnail()
        larger=view.grid.visualItemRect(view.grid.item(0));larger_image=delegate.image_rect(larger,index)
        assert larger_image.width()>image_rect.width()*1.5
        assert larger.height()-larger_image.height()==pytest.approx(caption_height,abs=2)
        assert larger_image.height()>larger.height()*.83
        view.grid.item(0).setSelected(True);view.rotate(90);app.processEvents()
        assert view.grid.item(0).data(ASPECT_ROLE)==pytest.approx(size[0]/size[1])
    finally:view.reject()
