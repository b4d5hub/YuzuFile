"""The global gesture only arms; real dragged PDF data decides the action."""
import ctypes
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QMimeData, QPoint, QPointF, QRect, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from yuzufile import desktop_drag
from yuzufile.desktop_drag import DesktopDragController, DragGesture, PointerState, WindowsPointer
from yuzufile.shaped_shell import FloatingShell
from yuzufile.ui import Window


def state(down=True, shift=False, escape=False, position=(100, 100), own_source=False):
    return PointerState(down, shift, escape, position, own_source)


def test_gesture_requires_movement_then_fresh_shift_and_only_fires_once_per_drag():
    gesture = DragGesture(10)
    assert not gesture.step(state())
    assert not gesture.step(state(position=(105, 104)))
    assert gesture.step(state(shift=True, position=(106, 104)))
    assert not gesture.step(state(shift=True, position=(130, 100)))
    assert not gesture.step(state(position=(140, 100)))
    assert not gesture.step(state(shift=True, position=(140, 100)))
    assert not gesture.step(state(down=False))
    assert not gesture.step(state(position=(200, 100)))
    assert gesture.step(state(shift=True, position=(210, 100)))


@pytest.mark.parametrize('initial', [
    state(shift=True), state(escape=True), state(own_source=True),
])
def test_shift_selection_escape_or_pdfai_internal_drag_cannot_summon(initial):
    gesture = DragGesture(10)
    assert not gesture.step(initial)
    assert not gesture.step(state(position=(150, 100)))
    assert not gesture.step(state(shift=True, position=(150, 100)))
    assert not gesture.step(state(down=False))
    assert not gesture.step(state())
    assert gesture.step(state(shift=True, position=(110, 100)))


def test_a_shift_tap_before_movement_needs_another_tap_after_movement():
    gesture = DragGesture(10)
    assert not gesture.step(state())
    assert not gesture.step(state(shift=True))
    assert not gesture.step(state(shift=True, position=(130, 100)))
    assert not gesture.step(state(position=(130, 100)))
    assert gesture.step(state(shift=True, position=(130, 100)))


def test_escape_cancels_and_blocks_this_drag_until_the_mouse_is_released():
    gesture = DragGesture(10)
    gesture.step(state())
    assert not gesture.step(state(escape=True, position=(120, 100)))
    assert not gesture.step(state(shift=True, position=(120, 100)))
    gesture.step(state(down=False))
    gesture.step(state())
    assert gesture.step(state(shift=True, position=(120, 100)))


@pytest.mark.parametrize('swapped,primary', [(False, 0x01), (True, 0x02)])
def test_native_sampler_honors_swapped_primary_and_only_reads_high_bit(monkeypatch, swapped, primary):
    # No native input is injected. A fake user32 verifies which physical button
    # the shipping sampler queries and that toggle/low bits are never mistaken
    # for a held key.
    qt = QApplication.instance() or QApplication([])
    calls = []
    keys = {primary: 0x8000, 0x10: 0x8001, 0x1b: 1}
    class User32:
        def GetSystemMetrics(self, metric):
            assert metric == 23
            return int(swapped)
        def GetAsyncKeyState(self, key):
            calls.append(key)
            return keys.get(key, 0)
        def GetForegroundWindow(self):
            return 42
        def GetWindowThreadProcessId(self, hwnd, target):
            assert hwnd == 42
            target._obj.value = os.getpid()
    pointer = WindowsPointer.__new__(WindowsPointer)
    pointer.available = True
    pointer.user32 = User32()
    pointer.ctypes = ctypes
    pointer.pid_type = ctypes.c_ulong
    monkeypatch.setattr(desktop_drag.QCursor, 'pos', lambda: QPoint(-1400, 250))
    observed = pointer.read()
    assert observed == PointerState(True, True, False, (-1400, 250), True)
    assert calls == [primary, 0x10, 0x1b]


@pytest.fixture
def desktop(store, monkeypatch):
    qt = QApplication.instance() or QApplication([])
    monkeypatch.setattr('yuzufile.ui.installed_languages', lambda: ['eng', 'fra', 'ara'])
    view = Window(store)
    view.timer.stop()
    shell = FloatingShell(view)
    shell.timer.stop()
    current = SimpleNamespace(value=state(down=False))
    drag = DesktopDragController(qt, view, shell, read_state=lambda: current.value)
    qt.processEvents()
    yield SimpleNamespace(app=qt, view=view, shell=shell, drag=drag,
                          overlay=drag.overlay, current=current)
    drag.shutdown()
    drag.overlay.hide()
    drag.overlay.deleteLater()
    drag.deleteLater()
    shell.shutdown()
    view.timer.stop()
    view.supervisor.shutdown()
    shell.hide()
    view.hide()
    shell.deleteLater()
    view.deleteLater()
    qt.processEvents()


def mime_for(*paths):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
    return mime


def arm(desktop):
    desktop.overlay.arm(QPoint(300, 300))
    desktop.app.processEvents()


def point_for(overlay, code):
    button = next(button for button, name in overlay.codes.items() if name == code)
    return button.mapTo(overlay, button.hit_point.toPoint())


def enter(overlay, mime, point=None, actions=None):
    actions = actions if actions is not None else Qt.DropAction.CopyAction | Qt.DropAction.MoveAction
    point = point if point is not None else overlay.wheel.center_button.mapTo(overlay, QPoint(55, 55))
    event = QDragEnterEvent(point, actions, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier)
    QApplication.sendEvent(overlay, event)
    return event


def drop(overlay, mime, point):
    event = QDropEvent(QPointF(point), Qt.DropAction.CopyAction | Qt.DropAction.MoveAction,
                       mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier)
    QApplication.sendEvent(overlay, event)
    return event


def test_mime_filter_accepts_only_local_pdfs_and_deduplicates_paths(tmp_path):
    pdf = tmp_path / 'Arabic العربية.PDF'
    note = tmp_path / 'notes.txt'
    mime = mime_for(pdf, note, pdf)
    mime.setUrls(mime.urls() + [QUrl('https://example.com/remote.pdf')])
    assert [Path(path) for path in desktop_drag.pdf_paths(mime)] == [pdf]
    plain = QMimeData()
    plain.setText(str(pdf))
    assert desktop_drag.pdf_paths(plain) == []


def test_armed_target_is_nonactivating_and_reveals_ui_only_for_real_pdf_mime(desktop, digital_pdf, tmp_path):
    overlay = desktop.overlay
    arm(desktop)
    assert overlay.isVisible() and overlay.armed
    assert not overlay.wheel.isVisible() and not overlay.caption.isVisible()
    assert overlay.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    assert overlay.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert not desktop.shell.isVisible() and desktop.view.pending == []
    invalid = mime_for(tmp_path / 'not-a-pdf.txt')
    assert not enter(overlay, invalid).isAccepted()
    assert not overlay.wheel.isVisible()
    accepted = enter(overlay, mime_for(digital_pdf))
    assert accepted.isAccepted() and accepted.dropAction() == Qt.DropAction.CopyAction
    assert overlay.payload_seen and overlay.wheel.isVisible() and overlay.caption.isVisible()
    assert desktop.view.pending == []
    assert not desktop.shell.isVisible()


def test_a_move_only_source_and_unarmed_drop_target_are_rejected(desktop, digital_pdf):
    mime = mime_for(digital_pdf)
    assert not enter(desktop.overlay, mime).isAccepted()
    arm(desktop)
    event = enter(desktop.overlay, mime, actions=Qt.DropAction.MoveAction)
    assert not event.isAccepted() and not desktop.overlay.payload_seen
    assert desktop.view.pending == []


def test_drag_hover_identifies_real_sector_and_drag_leave_keeps_reentry_target(desktop, digital_pdf):
    overlay = desktop.overlay
    arm(desktop)
    mime = mime_for(digital_pdf)
    assert enter(overlay, mime).isAccepted()
    position = point_for(overlay, 'docx')
    movement = QDragMoveEvent(position, Qt.DropAction.CopyAction | Qt.DropAction.MoveAction,
                              mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier)
    QApplication.sendEvent(overlay, movement)
    assert movement.isAccepted() and movement.dropAction() == Qt.DropAction.CopyAction
    assert overlay.hover_code == 'docx'
    highlighted = [code for button, code in overlay.codes.items() if button.drag_hovered]
    assert highlighted == ['docx'] and overlay.caption.text() == desktop.view.operations['docx'].title
    assert desktop.view.selected_operations() == {'ocr'}
    QApplication.sendEvent(overlay, QDragLeaveEvent())
    assert overlay.isVisible() and overlay.armed
    assert overlay.hover_code == ''
    assert all(not button.drag_hovered for button in overlay.codes)
    assert enter(overlay, mime).isAccepted()


def test_drop_forces_copy_and_defers_single_tool_selection_without_changing_source(desktop, digital_pdf):
    original = hashlib.sha256(digital_pdf.read_bytes()).digest()
    arm(desktop)
    mime = mime_for(digital_pdf)
    assert enter(desktop.overlay, mime).isAccepted()
    position = point_for(desktop.overlay, 'compress')
    received = drop(desktop.overlay, mime, position)
    assert received.isAccepted() and received.dropAction() == Qt.DropAction.CopyAction
    assert desktop.view.pending == [] and not desktop.shell.isVisible()
    assert not desktop.overlay.isVisible() and not desktop.overlay.armed
    desktop.app.processEvents()
    assert desktop.view.pending == [digital_pdf]
    assert desktop.view.selected_operations() == {'compress'}
    assert desktop.shell.isVisible() and desktop.shell.mode == 'tray'
    assert hashlib.sha256(digital_pdf.read_bytes()).digest() == original


def test_multi_pdf_center_drop_preserves_existing_files_and_selected_operation(desktop, digital_pdf, scanned_pdf):
    desktop.view.add_files([str(digital_pdf)])
    arm(desktop)
    mime = mime_for(digital_pdf, scanned_pdf, scanned_pdf)
    center = desktop.overlay.wheel.center_button.mapTo(desktop.overlay, QPoint(55, 55))
    assert enter(desktop.overlay, mime, center).isAccepted()
    assert drop(desktop.overlay, mime, center).isAccepted()
    desktop.app.processEvents()
    assert desktop.view.pending == [digital_pdf, scanned_pdf]
    assert desktop.view.selected_operations() == {'ocr'}
    assert desktop.shell.mode == 'tray' and desktop.shell.isVisible()


@pytest.mark.parametrize('code,method', [('merge', 'merge_pdfs'), ('arrange', 'organize_pages')])
def test_modal_tool_opens_after_drop_callback_and_receives_the_real_pdf(desktop, digital_pdf, monkeypatch, code, method):
    calls = []
    monkeypatch.setattr(desktop.view, method, lambda: calls.append(list(desktop.view.pending)))
    arm(desktop)
    mime = mime_for(digital_pdf)
    assert enter(desktop.overlay, mime).isAccepted()
    position = point_for(desktop.overlay, code)
    assert drop(desktop.overlay, mime, position).isAccepted()
    assert calls == [] and desktop.view.pending == []
    desktop.app.processEvents()
    assert calls == [[digital_pdf]] and not desktop.overlay.isVisible()


def trigger(desktop):
    for value in (state(), state(position=(120, 100)), state(shift=True, position=(120, 100))):
        desktop.current.value = value
        desktop.drag.poll()
    desktop.app.processEvents()


def test_mouse_release_without_drop_cancels_without_reopening_the_app(desktop):
    trigger(desktop)
    assert desktop.overlay.armed
    desktop.current.value = state(down=False, position=(120, 100))
    desktop.drag.poll()
    assert desktop.overlay.armed  # OLE Drop callback gets time to win this race.
    QTest.qWait(130)
    assert not desktop.overlay.armed and not desktop.overlay.isVisible()
    assert not desktop.shell.isVisible() and desktop.view.pending == []


def test_escape_and_disable_dismiss_overlay_and_stop_sampler(desktop):
    trigger(desktop)
    assert desktop.overlay.armed
    desktop.current.value = state(shift=True, escape=True, position=(120, 100))
    desktop.drag.poll()
    assert not desktop.overlay.armed and not desktop.overlay.isVisible()
    desktop.current.value = state(down=False)
    desktop.drag.poll()
    trigger(desktop)
    assert desktop.overlay.armed
    assert desktop.drag.start() and desktop.drag.timer.isActive()
    desktop.drag.set_enabled(False)
    assert not desktop.drag.timer.isActive() and not desktop.overlay.armed
    desktop.current.value = state(shift=True, position=(120, 100))
    desktop.drag.poll()
    assert not desktop.overlay.isVisible() and not desktop.shell.isVisible()


def test_accepted_drop_wins_mouse_release_cleanup_and_does_not_lose_the_file(desktop, digital_pdf):
    trigger(desktop)
    mime = mime_for(digital_pdf)
    assert enter(desktop.overlay, mime).isAccepted()
    position = point_for(desktop.overlay, 'docx')
    desktop.current.value = state(down=False, position=(120, 100))
    desktop.drag.poll()
    assert drop(desktop.overlay, mime, position).isAccepted()
    QTest.qWait(140)
    assert desktop.view.pending == [digital_pdf]
    assert desktop.view.selected_operations() == {'docx'}
    assert desktop.shell.isVisible() and desktop.shell.mode == 'tray'
    assert not desktop.overlay.isVisible()


@pytest.mark.parametrize('code', ['ocr', 'docx', 'markdown', 'compress', 'cleanup', 'split', 'remove_ocr'])
def test_each_conversion_sector_selects_one_operation_even_when_shift_is_held(desktop, digital_pdf, code):
    arm(desktop)
    mime = mime_for(digital_pdf)
    assert enter(desktop.overlay, mime).isAccepted()
    position = point_for(desktop.overlay, code)
    assert desktop.overlay.code_at(QPointF(position)) == code
    assert drop(desktop.overlay, mime, position).isAccepted()
    desktop.app.processEvents()
    assert desktop.view.selected_operations() == {code}
    assert desktop.view.pending == [digital_pdf]


def test_drop_rereads_payload_and_rejects_a_replaced_non_pdf_payload(desktop, digital_pdf, tmp_path):
    arm(desktop)
    assert enter(desktop.overlay, mime_for(digital_pdf)).isAccepted()
    position = point_for(desktop.overlay, 'compress')
    rejected = drop(desktop.overlay, mime_for(tmp_path / 'changed-to-text.txt'), position)
    assert not rejected.isAccepted()
    desktop.app.processEvents()
    assert desktop.view.pending == []
    assert not desktop.shell.isVisible() and not desktop.overlay.armed


def test_a_modal_editor_blocks_the_gesture_without_interrupting_the_editor(desktop, monkeypatch):
    monkeypatch.setattr(QApplication, 'activeModalWidget', lambda: object())
    trigger(desktop)
    assert not desktop.overlay.isVisible() and not desktop.overlay.armed
    assert desktop.view.pending == [] and not desktop.shell.isVisible()


@pytest.mark.parametrize('area,point', [
    (QRect(0, 0, 1280, 720), QPoint(1279, 719)),
    (QRect(-1920, -200, 1920, 1080), QPoint(-1920, -200)),
    (QRect(100, 50, 580, 520), QPoint(101, 51)),
])
def test_drop_wheel_stays_inside_the_pointer_monitor_work_area(desktop, monkeypatch, area, point):
    monkeypatch.setattr(desktop_drag.QGuiApplication, 'screenAt', lambda position: SimpleNamespace(availableGeometry=lambda: area))
    desktop.overlay.arm(point)
    desktop.app.processEvents()
    assert area.contains(desktop.overlay.geometry())
    assert desktop.overlay.anchor == point
    assert not desktop.overlay.wheel.isVisible()


@pytest.fixture(params=['merge', 'arrange'])
def page_tool(desktop, request):
    from yuzufile.merge_ui import MergeDialog
    from yuzufile.organize_ui import OrganizeDialog
    kind = request.param
    dialog = MergeDialog(desktop.shell) if kind == 'merge' else OrganizeDialog(desktop.shell)
    dialog.show()
    desktop.app.processEvents()
    target = dialog.documents if kind == 'merge' else dialog.grid
    yield dialog, target
    for name in ('timer', 'feedback_timer'):
        timer = getattr(dialog, name, None)
        if timer is not None:
            timer.stop()
    dialog.hide()
    dialog.deleteLater()
    desktop.app.processEvents()


def test_direct_page_tool_shift_drop_copies_the_pdf_without_moving_original(page_tool, digital_pdf):
    dialog, target = page_tool
    original = digital_pdf.read_bytes()
    mime = mime_for(digital_pdf)
    position = QPoint(15, 15)
    actions = Qt.DropAction.CopyAction | Qt.DropAction.MoveAction
    modifiers = Qt.KeyboardModifier.ShiftModifier
    entered = QDragEnterEvent(position, actions, mime, Qt.MouseButton.LeftButton, modifiers)
    QApplication.sendEvent(target.viewport(), entered)
    assert entered.isAccepted() and entered.dropAction() == Qt.DropAction.CopyAction
    moved = QDragMoveEvent(position, actions, mime, Qt.MouseButton.LeftButton, modifiers)
    QApplication.sendEvent(target.viewport(), moved)
    assert moved.isAccepted() and moved.dropAction() == Qt.DropAction.CopyAction
    dropped = QDropEvent(QPointF(position), actions, mime, Qt.MouseButton.LeftButton, modifiers)
    QApplication.sendEvent(target.viewport(), dropped)
    assert dropped.isAccepted() and dropped.dropAction() == Qt.DropAction.CopyAction
    assert len(dialog.sources) == 1 and Path(dialog.sources[0]['path']) == digital_pdf
    assert target.count() == 1
    assert digital_pdf.read_bytes() == original


@pytest.mark.parametrize('invalid', ['move-only', 'non-pdf'])
def test_direct_page_tool_rejects_external_move_only_or_non_pdf(page_tool, digital_pdf, tmp_path, invalid):
    dialog, target = page_tool
    mime = mime_for(digital_pdf if invalid == 'move-only' else tmp_path / 'notes.txt')
    actions = Qt.DropAction.MoveAction if invalid == 'move-only' else Qt.DropAction.CopyAction | Qt.DropAction.MoveAction
    position, modifiers = QPoint(15, 15), Qt.KeyboardModifier.ShiftModifier
    entered = QDragEnterEvent(position, actions, mime, Qt.MouseButton.LeftButton, modifiers)
    moved = QDragMoveEvent(position, actions, mime, Qt.MouseButton.LeftButton, modifiers)
    dropped = QDropEvent(QPointF(position), actions, mime, Qt.MouseButton.LeftButton, modifiers)
    # Call every native handler independently: even an unexpected Drop after a
    # rejected DragEnter must not grant a Move or add a non-PDF to the document.
    for handler, event in ((target.dragEnterEvent, entered), (target.dragMoveEvent, moved), (target.dropEvent, dropped)):
        handler(event)
        assert not event.isAccepted()
    assert target.count() == 0 and dialog.sources == []
    assert digital_pdf.is_file()
