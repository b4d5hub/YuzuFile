"""Interaction regressions for the file-centred radial tool menu."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from yuzufile.ui import Window


@pytest.fixture
def view(store,monkeypatch):
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr('yuzufile.ui.installed_languages',lambda:['eng','fra'])
    window=Window(store);window.timer.stop();window.show();app.processEvents()
    yield window
    window.supervisor.shutdown();window.deleteLater();app.processEvents()


def test_each_wedge_selects_only_its_own_operation_and_can_combine(view):
    for code,button in view.operations.items():
        QTest.mouseClick(button,Qt.MouseButton.LeftButton,pos=button.hit_point.toPoint())
        assert view.selected_operations()=={code}
    for button in view.operations.values():button.setChecked(False)
    selected=set()
    for code,button in view.operations.items():
        QTest.mouseClick(button,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.ShiftModifier,pos=button.hit_point.toPoint())
        if code=='remove_ocr':selected-= {'ocr','markdown','docx'}
        elif code in {'ocr','markdown','docx'}:selected.discard('remove_ocr')
        selected.add(code)
        assert {code for code,b in view.operations.items() if b.isChecked()}==selected


def test_real_child_hit_regions_leave_the_drop_target_reachable(view):
    wheel=view.tool_wheel
    center=wheel.rect().center()
    child=wheel.childAt(center)
    assert child is view.upload or view.upload.isAncestorOf(child)
    for button in wheel.buttons:
        point=button.mapTo(wheel,button.hit_point.toPoint())
        assert wheel.childAt(point) is button
        assert not button.hitButton(button.mapFrom(wheel,center))


def test_arrow_keys_move_focus_without_changing_selection_and_space_selects(view):
    buttons=view.tool_wheel.buttons
    before={code:b.isChecked() for code,b in view.operations.items()}
    buttons[0].setFocus();QTest.keyClick(buttons[0],Qt.Key.Key_Right)
    assert buttons[1].hasFocus()
    assert {code:b.isChecked() for code,b in view.operations.items()}==before
    QTest.keyClick(buttons[1],Qt.Key.Key_Space)
    assert view.operations['docx'].isChecked()!=before['docx']
    QTest.keyClick(buttons[1],Qt.Key.Key_Left)
    assert buttons[0].hasFocus()


def test_wheel_keeps_valid_click_targets_after_resize(view):
    for width,height in ((720,540),(920,900),(720,760)):
        view.resize(width,height);QApplication.instance().processEvents()
        for button in view.tool_wheel.buttons:
            assert button.hitButton(button.hit_point.toPoint())
            point=button.mapTo(view.tool_wheel,button.hit_point.toPoint())
            assert view.tool_wheel.rect().contains(point)
        assert view.workspace.horizontalScrollBar().maximum()==0


def test_compression_segments_follow_the_conversion_setting(view):
    for code,button in view.operations.items():button.setChecked(code=='compress')
    segments=view.compression_segments
    for index,button in enumerate(segments.buttons):
        QTest.mouseClick(button,Qt.MouseButton.LeftButton)
        assert view.compression.currentIndex()==index
        assert sum(b.isChecked() for b in segments.buttons)==1
    view.compression.setCurrentIndex(0)
    assert segments.buttons[0].isChecked()
