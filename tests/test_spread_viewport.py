import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import QPoint,QPointF,Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from yuzufile.spread_preview import SpreadPreview
from yuzufile.spreads import settings
from yuzufile.ui import Window,CompressionBox


@pytest.fixture
def preview(store,digital_pdf):
    app=QApplication.instance() or QApplication([])
    parent=Window(store);parent.timer.stop()
    dialog=SpreadPreview(parent,[digital_pdf],settings({'parts':3}),CompressionBox)
    dialog.resize(1040,800);dialog.show()
    QTest.qWait(180);app.processEvents()
    yield dialog
    dialog.reject();parent.supervisor.shutdown();parent.deleteLater();app.processEvents()


def test_portrait_opens_at_width_and_fit_page_is_an_explicit_choice(preview):
    viewport=preview.viewport;rect=preview.canvas.fit_rect()
    assert viewport.mode=='width'
    assert rect.width()==pytest.approx(viewport.viewport().width()-48,abs=2)
    assert viewport.horizontalScrollBar().maximum()==0
    assert viewport.verticalScrollBar().maximum()>0
    preview.fit_page.click();QApplication.processEvents()
    assert preview.canvas.fit_rect().height()<=viewport.viewport().height()-46
    preview.fit_width.click();QApplication.processEvents()
    assert preview.canvas.fit_rect().width()==pytest.approx(rect.width(),abs=2)


def test_zoom_and_pan_preserve_cut_geometry_and_anchor(preview):
    viewport=preview.viewport;canvas=preview.canvas;before=list(canvas.cuts())
    viewport.verticalScrollBar().setValue(120)
    anchor=QPoint(180,140)
    old=canvas.fit_rect();point=canvas.mapFrom(viewport.viewport(),anchor)
    fraction=((point.x()-old.x())/old.width(),(point.y()-old.y())/old.height())
    viewport.set_zoom(viewport.zoom*1.5,anchor);QApplication.processEvents()
    new=canvas.fit_rect();point=canvas.mapFrom(viewport.viewport(),anchor)
    assert ((point.x()-new.x())/new.width(),(point.y()-new.y())/new.height())==pytest.approx(fraction,abs=.003)
    initial=viewport.verticalScrollBar().value()
    point=canvas.mapFrom(viewport.viewport(),QPoint(90,200))
    QTest.mousePress(canvas,Qt.MouseButton.LeftButton,pos=point)
    QTest.mouseMove(canvas,point+QPoint(0,-50))
    QTest.mouseRelease(canvas,Qt.MouseButton.LeftButton,pos=point+QPoint(0,-50))
    assert viewport.verticalScrollBar().value()>initial
    assert canvas.cuts()==before


def test_scrolled_handles_are_reachable_and_second_line_stays_selected(preview):
    viewport=preview.viewport;canvas=preview.canvas
    viewport.verticalScrollBar().setValue(200);QApplication.processEvents()
    handle=canvas.handle_rects()[1]
    assert canvas.visible_rect().contains(handle.center())
    assert handle.width()>=18 and handle.height()>=48
    start=handle.center().toPoint();target=start+QPoint(35,0)
    before=list(canvas.cuts())
    QTest.mousePress(canvas,Qt.MouseButton.LeftButton,pos=start)
    QTest.mouseMove(canvas,target);QTest.mouseRelease(canvas,Qt.MouseButton.LeftButton,pos=target)
    assert canvas.cuts()[0]==before[0] and canvas.cuts()[1]>before[1]
    assert preview.cut_selector.currentIndex()==1
    value=canvas.cuts()[1]
    QTest.keyClick(canvas,Qt.Key.Key_Left)
    assert canvas.cuts()[1]==pytest.approx(value-.1)
    preview.cut_position.setValue(75)
    assert preview.config()['cuts'][1]==pytest.approx(75)


def test_ctrl_wheel_zooms_without_repositioning_a_split(preview):
    canvas=preview.canvas;viewport=preview.viewport;before=list(canvas.cuts());zoom=viewport.zoom
    point=canvas.mapFrom(viewport.viewport(),QPoint(160,180))
    event=QWheelEvent(QPointF(point),QPointF(canvas.mapToGlobal(point)),QPoint(),QPoint(0,120),
        Qt.MouseButton.NoButton,Qt.KeyboardModifier.ControlModifier,Qt.ScrollPhase.NoScrollPhase,False)
    QApplication.sendEvent(canvas,event)
    assert viewport.zoom>zoom and canvas.cuts()==before


def test_raster_refresh_is_bounded_and_close_stops_pending_work(preview):
    old=preview.canvas.pixmap.size()
    preview.viewport.set_zoom(6);QTest.qWait(180)
    width,height=preview.raster_size
    assert width*height<=8_020_000 and max(width,height)<=6001
    assert preview.canvas.pixmap.width()>old.width()
    preview.viewport.set_zoom(2);assert preview.raster_timer.isActive()
    preview.reject()
    assert not preview.raster_timer.isActive() and preview.document is None


def test_horizontal_dividers_scroll_into_view_and_keep_export_order(preview):
    preview.direction.setCurrentIndex(preview.direction.findData('bt'))
    preview.cut_selector.setCurrentIndex(1);QApplication.processEvents()
    canvas=preview.canvas;handle=canvas.handle_rects()[1]
    assert canvas.visible_rect().contains(handle.center())
    before=list(canvas.cuts());start=handle.center().toPoint();target=start+QPoint(0,-30)
    QTest.mousePress(canvas,Qt.MouseButton.LeftButton,pos=start)
    QTest.mouseMove(canvas,target);QTest.mouseRelease(canvas,Qt.MouseButton.LeftButton,pos=target)
    assert canvas.cuts()[0]==before[0] and canvas.cuts()[1]<before[1]
    assert preview.config()['direction']=='bt' and preview.config()['parts']==3
