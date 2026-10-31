"""Summon a PDF drop wheel without taking focus from the drag source.

The native sampler observes only the primary button, Shift and Escape. Mouse
movement is an invitation to arm a drop target, never evidence of a file drag.
Only Qt's real OLE MIME data can reveal the wheel or add documents.
"""
from dataclasses import dataclass
import os
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter, QRegion
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

from yuzufile.icons import icon
from yuzufile.tool_wheel import ToolWheel
from yuzufile.ui_style import STYLE, light_palette


def pdf_paths(mime):
    """Read dragged URLs, without touching the clipboard or opening a file."""
    if not mime.hasUrls():
        return []
    paths, seen = [], set()
    for url in mime.urls():
        if not url.isLocalFile():
            continue
        path = url.toLocalFile()
        if Path(path).suffix.lower() != '.pdf':
            continue
        key = os.path.normcase(os.path.normpath(path))
        if key not in seen:
            paths.append(path)
            seen.add(key)
    return paths


def accept_copy(event):
    """Shift proposes Move in Explorer. A yuzufile drop must always be a copy."""
    if event.possibleActions() & Qt.DropAction.CopyAction:
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        return True
    event.ignore()
    return False


@dataclass(frozen=True)
class PointerState:
    down: bool
    shift: bool
    escape: bool
    position: tuple[int, int]
    own_source: bool = False


class DragGesture:
    """One activation per mouse hold, on a fresh Shift after drag movement."""
    def __init__(self, distance=10):
        self.distance = distance
        self.reset()

    def reset(self):
        self.origin = None
        self.previous_shift = False
        self.blocked = False
        self.fired = False

    def step(self, state):
        if not state.down:
            self.reset()
            self.previous_shift = state.shift
            return False
        if self.origin is None:
            self.origin = state.position
            self.blocked = state.own_source or state.shift or state.escape
        rising = state.shift and not self.previous_shift
        self.previous_shift = state.shift
        if state.escape:
            self.blocked = True
        moved = sum(abs(a-b) for a, b in zip(state.position, self.origin)) >= self.distance
        if rising and moved and not self.blocked and not self.fired:
            self.fired = True
            return True
        return False


class WindowsPointer:
    """Read a handful of native state bits; no hooks or keystroke collection."""
    def __init__(self):
        self.available = os.name == 'nt'
        if not self.available:
            return
        import ctypes
        from ctypes import wintypes
        self.ctypes = ctypes
        self.user32 = ctypes.WinDLL('user32', use_last_error=True)
        self.user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self.user32.GetAsyncKeyState.restype = ctypes.c_short
        self.user32.GetSystemMetrics.argtypes = [ctypes.c_int]
        self.user32.GetSystemMetrics.restype = ctypes.c_int
        self.user32.GetForegroundWindow.argtypes = []
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        self.pid_type = wintypes.DWORD

    def read(self):
        if not self.available:
            return PointerState(False, False, False, (0, 0))
        down = lambda key: bool(self.user32.GetAsyncKeyState(key) & 0x8000)
        # GetAsyncKeyState reports physical buttons. Honor the user's swapped
        # primary mouse button setting rather than hard-coding left-handedness.
        primary = 0x02 if self.user32.GetSystemMetrics(23) else 0x01
        point = QCursor.pos()  # Qt logical pixels, including mixed-DPI monitors.
        pid = self.pid_type()
        hwnd = self.user32.GetForegroundWindow()
        if hwnd:
            self.user32.GetWindowThreadProcessId(hwnd, self.ctypes.byref(pid))
        return PointerState(down(primary), down(0x10), down(0x1b),
                            (point.x(), point.y()), pid.value == os.getpid())


class DesktopDropWheel(QWidget):
    """Temporary OLE target. It never changes or steals the user's open task."""
    files_dropped = Signal(list, str, QPoint)
    SIZE = 380

    def __init__(self, controller):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus
                         | Qt.WindowType.NoDropShadowWindowHint)
        self.setWindowTitle('yuzufile · Drop a PDF')
        self.setWindowIcon(controller.windowIcon())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAcceptDrops(True)
        self.setPalette(light_palette())
        self.setStyleSheet(STYLE)
        self.armed = False
        self.payload_seen = False
        self.hover_code = ''
        self.anchor = QPoint()
        center = QPushButton('Drop PDFs\nChoose later')
        center.setObjectName('dragDropCenter')
        center.setIcon(icon('file-plus', 22))
        center.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        center.setStyleSheet('QPushButton { color:#4b5054; background:#f5f5f2; border:1px solid #cbd0cb; border-radius:55px; font-size:12px; }')
        self.wheel = ToolWheel(center)
        self.wheel.setParent(self)
        self.wheel.setFixedSize(self.SIZE, self.SIZE)
        self.wheel.move(0, 0)
        self.codes = {}
        for code, button in controller.operations.items():
            item = self.wheel.add_tool(button.title, button.caption, button.glyph, button.short)
            self.codes[item] = code
        for code, button in (('merge', controller.merge_button), ('arrange', controller.organize_button)):
            item = self.wheel.add_action(button.title, button.caption, button.glyph, button.short, lambda: None)
            self.codes[item] = code
        for button in self.wheel.buttons:
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.drag_active = True
        self.caption = QLabel('Drop on a tool', self)
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption.setGeometry(64, self.SIZE-2, self.SIZE-128, 28)
        self.caption.setStyleSheet('QLabel { color:#42484b; background:#f4f4f1; border:1px solid #d3d5cf; border-radius:12px; font-size:12px; padding:2px 8px; }')
        self.setFixedSize(self.SIZE, self.SIZE+28)
        self.wheel.hide()
        self.caption.hide()

    def arm(self, position):
        self.cancel()
        self.armed = True
        self.anchor = QPoint(position)
        screen = QGuiApplication.screenAt(position) or self.screen()
        area = screen.availableGeometry()
        # A small screen can still fit a smaller wheel, with logical-pixel math.
        size = min(self.SIZE, max(240, area.width()-16), max(240, area.height()-44))
        self.setFixedSize(size, size+28)
        self.wheel.setFixedSize(size, size)
        self.caption.setGeometry(48, size-2, size-96, 28)
        self.move(max(area.left(), min(position.x()-size//2, area.right()-size+1)),
                  max(area.top(), min(position.y()-size//2, area.bottom()-size-27)))
        self.setMask(QRegion(QRect(6, 6, size-12, size-12), QRegion.RegionType.Ellipse))
        self.show()
        self.raise_()  # WA_ShowWithoutActivating + no-focus: Explorer keeps drag.
        self.update()

    def cancel(self):
        self.armed = False
        self.payload_seen = False
        self.hover_code = ''
        for button in self.wheel.buttons:
            button.drag_hovered = False
            button.update()
        self.wheel.hide()
        self.caption.hide()
        self.hide()

    def paintEvent(self, event):
        # Windows layered windows pass through alpha=0 pixels. This barely
        # visible disc permits real OLE DragEnter before exposing any tool UI.
        painter = QPainter(self)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 3))
        painter.drawEllipse(QRectF(6, 6, self.width()-12, self.width()-12))

    def code_at(self, position):
        for button, code in self.codes.items():
            local = button.mapFrom(self, position.toPoint() if isinstance(position, QPointF) else position)
            if button.path.contains(QPointF(local)):
                return code
        return ''

    def _highlight(self, position):
        self.hover_code = self.code_at(position)
        for button, code in self.codes.items():
            hovered = code == self.hover_code
            if getattr(button, 'drag_hovered', False) != hovered:
                button.drag_hovered = hovered
                button.update()
        self.caption.setText(next((b.title for b, c in self.codes.items() if c == self.hover_code), 'Drop to add PDFs'))

    def dragEnterEvent(self, event):
        if not self.armed or not pdf_paths(event.mimeData()) or not accept_copy(event):
            event.ignore()
            return
        self.payload_seen = True
        self.wheel.show()
        self.caption.show()
        region = QRegion(QRect(6, 6, self.width()-12, self.width()-12), QRegion.RegionType.Ellipse)
        self.setMask(region.united(QRegion(self.caption.geometry())))
        self._highlight(event.position())

    def dragMoveEvent(self, event):
        if self.armed and self.payload_seen and accept_copy(event):
            self._highlight(event.position())
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._highlight(QPoint(-100, -100))
        # Keep the target until release/Escape so the user can re-enter it.
        event.accept()

    def dropEvent(self, event):
        paths = pdf_paths(event.mimeData())
        if not self.armed or not self.payload_seen or not paths or not accept_copy(event):
            event.ignore()
            self.cancel()
            return
        code, anchor = self.code_at(event.position()), QPoint(self.anchor)
        self.cancel()
        # The receiver defers controller work until OLE has returned. It must
        # not open a modal editor or inspect a PDF while Drop is on the stack.
        self.files_dropped.emit(paths, code, anchor)


class DesktopDragController(QObject):
    """Lifetime of the global gesture sampler and its short-lived drop wheel."""
    def __init__(self, app, view, shell, read_state=None):
        super().__init__(app)
        self.app, self.view, self.shell = app, view, shell
        self.native = WindowsPointer()
        self.available = self.native.available or read_state is not None
        self.read_state = read_state or self.native.read
        self.enabled = True
        self.gesture = DragGesture(app.startDragDistance())
        self.overlay = DesktopDropWheel(view)
        self.overlay.files_dropped.connect(self._dropped)
        self.timer = QTimer(self)
        self.timer.setInterval(25)
        self.timer.timeout.connect(self.poll)
        self._generation = 0
        self._releasing = False
        app.aboutToQuit.connect(self.shutdown)

    def start(self):
        if self.available and self.enabled:
            self.timer.start()
        return self.available

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)
        self.gesture.reset()
        self.overlay.cancel()
        self._generation += 1
        if self.enabled and self.available:
            self.timer.start()
        else:
            self.timer.stop()

    def poll(self):
        if not self.enabled or self.shell._closed:
            return
        state = self.read_state()
        if state.escape:
            self.overlay.cancel()
        if self.gesture.step(state):
            if not (QApplication.activeModalWidget() or QApplication.activePopupWidget()
                    or QWidget.mouseGrabber()):
                self._generation += 1
                self._releasing = False
                self.overlay.arm(QPoint(*state.position))
        if not state.down and self.overlay.armed and not self._releasing:
            # Give Windows' Drop callback priority over polling mouse release.
            self._releasing = True
            generation = self._generation
            QTimer.singleShot(100, self, lambda: self._release(generation))

    def _release(self, generation):
        if generation == self._generation:
            self.overlay.cancel()
            self._releasing = False

    def _dropped(self, paths, code, anchor):
        self._generation += 1
        self._releasing = False
        QTimer.singleShot(0, self, lambda: self.open_drop(paths, code, anchor))

    def open_drop(self, paths, code, anchor):
        if self.shell._closed:
            return
        if self.shell.resident:
            if code:self.shell.open_tool(code,paths,anchor)
            else:self.shell.choose_tool_menu(position=anchor,paths=paths)
            return
        self.view.add_files(paths)
        if not self.view.pending:
            return
        self.shell._anchor = QPoint(anchor)
        self.shell._task_position = None
        if code in self.view.operations:
            # Shift here is the summoning gesture, never the multi-tool click
            # shortcut. Select the drop's explicit single operation directly.
            for name, button in self.view.operations.items():
                button.setChecked(name == code)
            self.view.update_mode()
        self.shell.showNormal()
        self.shell.show_tray()
        self.shell.raise_()
        self.shell.activateWindow()
        if code == 'merge':
            self.view.merge_pdfs()
        elif code == 'arrange':
            self.view.organize_pages()

    def shutdown(self):
        self.timer.stop()
        self.enabled = False
        self._generation += 1
        self.overlay.cancel()
