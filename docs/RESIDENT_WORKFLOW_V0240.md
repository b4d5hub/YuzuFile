# Tray-first workflow — 0.24.0

Normal Windows use has no persistent wheel or Home window. PDFai remains in the
notification area. A real external PDF drag followed by Shift reveals the
temporary wheel near the cursor. Drop on a tool to open that focused task.
The wheel closes with the drag; it has no movable handle.

Tray clicks open a compact menu: Process PDFs, Processing & results, History,
Open latest result, Open result folder, Enable drag + Shift, Quit PDFai.
Resume task appears when a draft is available, so hiding an unfinished task does
not make it inaccessible. It switches back from History to that task directly.
Process PDFs offers a native picker and a compact tool menu as an accessible
alternative to dragging. Picked paths are staged until a tool is selected.
Cancelling the menu preserves the current batch.

The task/processing windows retain movable title bars. Close/Escape hides a task;
Hide keeps processing in the background; Done closes completed results. History
closes to the background. Visual editors return to their prior task. Direct
Merge/Arrange open their editors without briefly showing an unrelated task;
cancellation returns to the tray, and saving opens progress. History's Process
Again preserves organization plans and opens the proper editor directly.

The tray menu keeps the full History feature and provides quick result access.
Starting a second instance restores a real current task/History/editor, or opens
the tray menu when idle. No manual persistent-wheel entry remains. A visible
wheel is retained only when the operating system's notification area is absent.

Existing operations, language selection, page previews, batch handling,
performance/output controls, output naming and conversion engines are preserved.
External PDF drops still require Copy; originals remain unchanged. Login autorun
is not registered.

The gesture implementation and its native testing limits remain documented in
[the 0.23.0 implementation record](TRAY_AND_DESKTOP_DRAG_V0230.md). The exact
physical Explorer drag/Shift sequence cannot be interleaved with the available
automation API; real OLE entry/hover and the component state/drop paths are
verified separately. Native menu, task, History and packaged exports are checked
with generated PDFs and isolated libraries.
