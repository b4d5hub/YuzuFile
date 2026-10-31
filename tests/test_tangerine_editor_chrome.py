"""Focused tool windows leave the page visible without losing edit controls."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pymupdf,pytest
from PySide6.QtCore import QPoint,Qt
from PySide6.QtWidgets import QApplication
from yuzufile.cleanup_preview import CleanupPreview
from yuzufile.spread_preview import SpreadPreview
from yuzufile.cleanup import settings
from yuzufile.spreads import settings as split_settings
from yuzufile.tool_window import ToolDialog
from yuzufile.ui import CompressionBox


@pytest.fixture
def editor_source(tmp_path):
    app=QApplication.instance() or QApplication([])
    path=tmp_path/'Three pages.pdf'
    with pymupdf.open() as document:
        for number in range(3):
            page=document.new_page(width=600,height=800)
            page.insert_text((45,65),f'Page {number+1}',fontsize=22)
            for line in range(20):page.insert_text((45,110+line*24),'Readable content for a visual page editor.',fontsize=14)
        document.save(path)
    return app,path


def show(dialog,width=1040,height=800):
    dialog.resize(width,height);dialog.show();QApplication.processEvents()
    return dialog


def test_cleanup_context_and_page_strip_expand_without_changing_edits(editor_source):
    app,path=editor_source
    view=show(CleanupPreview(None,[path],settings({'straighten':False}),CompressionBox))
    try:
        assert isinstance(view,ToolDialog) and view.header.height()==48
        assert not view.alignment_row.isVisible() and not view.thumbnails.isVisible()
        assert view.edit_view.width()>view.width()*.9 and view.edit_view.height()>view.height()*.6
        view.set_edit(angle=3.2,rotation=90);view.render_page();before=view.config()
        view.tool('straighten');app.processEvents()
        assert view.alignment_row.isVisible() and not view.crop_context.isVisible()
        view.tool('crop');app.processEvents()
        assert not view.alignment_row.isVisible() and view.crop_context.isVisible()
        assert view.config()==before
        view.scope.setCurrentIndex(1);app.processEvents()
        assert view.pages_button.isChecked() and view.thumbnails.isVisible()
        view.pages_button.click();app.processEvents();assert not view.thumbnails.isVisible()
        assert 'Ctrl+scroll' in view.help_button.toolTip()
    finally:view.reject()


@pytest.mark.parametrize('kind',['cleanup','split'])
@pytest.mark.parametrize('size',[(720,460),(580,520)])
def test_compact_editors_keep_essential_controls_reachable(editor_source,kind,size):
    app,path=editor_source
    view=show(CleanupPreview(None,[path],settings({'straighten':False}),CompressionBox) if kind=='cleanup'
              else SpreadPreview(None,[path],split_settings({'parts':3}),CompressionBox),*size)
    try:
        assert (view.width(),view.height())==size
        controls=[view.files,view.page,view.apply,view.header.close_button,view.zoom_controls]
        if kind=='cleanup':controls += [view.crop_tool,view.align_tool,view.pan_tool,view.batch,view.scope,view.pages_button]
        else:controls += [view.direction,view.parts,view.equal,view.cut_selector,view.cut_position,view.ranges]
        for control in controls:
            assert control.isVisible()
            point=control.mapTo(view,QPoint())
            assert view.rect().contains(point) and view.rect().contains(point+QPoint(control.width()-1,control.height()-1))
        if kind=='cleanup':
            view.tool('straighten');app.processEvents()
            for control in (view.auto,view.angle,view.angle_label):
                point=control.mapTo(view,QPoint())
                assert control.isVisible() and view.rect().contains(point+QPoint(control.width()-1,control.height()-1))
        else:
            assert view.viewport.mode=='width' and view.viewport.height()>size[1]*.4
    finally:view.reject()


@pytest.mark.parametrize('kind',['cleanup','split'])
def test_tool_header_close_releases_editor_documents_and_timers(editor_source,kind):
    app,path=editor_source
    view=show(CleanupPreview(None,[path],settings({'straighten':False}),CompressionBox) if kind=='cleanup'
              else SpreadPreview(None,[path],split_settings(),CompressionBox))
    if kind=='cleanup':view.edit_view.set_zoom(2)
    else:view.viewport.set_zoom(2)
    view.header.close_button.click();app.processEvents()
    assert view.document is None and not view.raster_timer.isActive()
    if kind=='cleanup':assert view.preview_document is None and not view.timer.isActive() and not view.thumb_timer.isActive()
