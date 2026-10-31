# Notification area and desktop PDF drag — 0.23.0

Start PDFai normally by double-clicking the EXE or project shortcut. It registers
its icon in the Windows notification area and remains available without an open
window. Windows can place this icon inside its **^** overflow menu. There is no
Windows-login autorun registration.

Click the icon to restore the current task, results, History or modal editor.
Right-click for Show PDFai, Add PDFs, History, Enable drag + Shift and Quit PDFai.
Closing/minimizing the floating window hides it; the conversion supervisor keeps
running. Explicit Quit asks before cancelling unfinished work. Without a system
tray, normal visible-window startup and close behavior are retained.

## Drag interaction

1. Start dragging one or several local PDFs, then tap Shift while the primary
   mouse button is held. Holding Shift before clicking selects Explorer items
   instead and does not trigger the wheel.
2. A temporary wheel appears near the pointer once the actual drag data includes
   PDF file URLs. Hover highlights the target tool. Releasing Shift keeps the
   wheel open for the remainder of this drag.
3. Drop onto a tool to open its existing task with the PDFs ready for review.
   Drop in the centre to add the PDFs and choose later. Merge and Arrange use
   their existing editors. Existing pending PDFs remain in the current batch.
4. Escape or releasing outside the wheel dismisses the temporary target without
   adding files or changing the current task.

Every external PDF drop target (wheel, floating task, Merge and Arrange) requires
and returns Copy, including when Explorer proposes Move because Shift is held.
Move is reserved for internal page/document reordering. Originals stay in place.
Non-PDF file drags, web URLs and ordinary text selection never expose the wheel.
An open modal editor/menu retains interaction until it is closed.

## Implementation

- `system_tray.py` owns QSystemTrayIcon and residence/restore actions.
- `desktop_drag.py` polls only primary button, Shift and Escape state through
  GetAsyncKeyState's high bit. It honors swapped primary buttons. No keyboard
  text, clipboard contents or Explorer selection are collected.
- The gesture merely arms a nonactivating, topmost Qt drop target. Its almost
  transparent hit-test disc uses nonzero alpha: fully transparent layered-window
  pixels pass input through on Windows. Only a real Qt/OLE DragEnter containing
  local PDF URLs exposes the wheel. Qt handles native OLE registration.
- Drop rereads the MIME payload, forces Copy and defers task/editor opening until
  the native Drop callback returns. Qt-context timers and generation counters
  handle cancellation, shutdown and release/drop ordering.
- Qt logical coordinates and the pointer's monitor work area place the wheel.
  Existing PDFai modal/menu/internal-drag interactions suppress activation.
- `desktop_instance.py` provides a bounded, user-local QLocalServer activation
  channel keyed by the resolved library path. A second GUI launch asks the owner
  to restore itself before opening Store. A short startup retry covers the gap
  before the first GUI's listener is ready. Store's existing exclusive lock
  remains authoritative; CLI and worker paths are unchanged.

The independent implementation was informed by [Kinnow's source](https://github.com/DuhanJishnu/kinnow/tree/45664e6b8b3f2064ff725d0d6904adbe3604eab4),
particularly its no-focus overlay and actual-MIME validation approach. Relevant
platform references: [Windows layered windows](https://learn.microsoft.com/en-us/windows/win32/winmsg/window-features#layered-windows),
[GetAsyncKeyState](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getasynckeystate),
and [Qt drag/drop action override](https://doc.qt.io/qtforpython-6/overviews/qtgui-dnd.html#dropping).

## Validation

225 combined desktop/page-editor tests pass, including 9 real Windows activation
pipe tests, tray/lifecycle behavior, delayed first-start listener, all 9 wheel
targets, actual Qt MIME events, release/cancel races, external Copy safety and
internal reorder behavior. Tests use isolated libraries and generated PDFs.
The shared test teardown drains Qt DeferredDelete events so retired test windows
are disposed before subsequent event loops run.

Native desktop QA confirmed notification-area availability, hidden launch,
second-launch restoration, close-to-tray, and real Windows OLE DragEnter/DragOver
data/Copy negotiation with the hovered tool identified. The automation tool's
atomic drag API cannot press Shift midway through a held Explorer drag; the exact
physical Explorer gesture is not established by those checks. Gesture state and
drop routing are covered separately by automated tests.

The release build guards executable bytecode for all 38 critical modules and
packaged source. Frozen export checks are run with an isolated library and OCR
models offline, preserving the original documents.
