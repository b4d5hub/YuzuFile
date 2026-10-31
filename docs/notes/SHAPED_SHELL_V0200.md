# A shaped YuzuFile desktop shell — 0.20.0

YuzuFile now starts as a real floating tool wheel. Its top-level window is frameless,
has a transparent background and uses a native input mask: the empty corners do
not cover the desktop. The existing conversion controller and engines are reused.

The wheel keeps its real tool buttons and central PDF drop/browse target. Select
one operation or combine several. The attached grip provides a visible drag handle,
context access, History, Minimize and Close. The context button opens added files
and options when idle, or returns to processing/results when jobs exist. Tool labels and keyboard
focus remain available; icons have accessible names. Minimized YuzuFile remains in
the normal Windows taskbar.

Choosing a tool opens an attached silver tray containing the actual file list,
languages, compression presets, visual-editor buttons, output folder, performance
selector and processing action. The tray shows only the relevant operation options.
On smaller displays, the form takes over the footprint and the grip returns to the
wheel. Long forms scroll vertically while the output/performance/Start area remains
available. Controls reflow to avoid horizontal clipping. Combined-tool labels list
the chosen operations without implying a processing order.

After starting a job, the shell switches to a compact processing capsule with
filename, stage, segmented progress and cancellation. Completed outputs provide
file/folder actions; failed and cancelled work can be retried. Mixed batches keep
their attention count visible. Compression savings are retained. History opens in
a separate large window using the existing history search, filtering and actions.
Closing History leaves YuzuFile and its library running; retry returns to the tray.

Visual page editors remain large, resizable/maximizable workspaces. Their dialog
owner is the visible shell, so editing does not depend on a hidden legacy window.
The page-first cards and full-width crop/split/reader views remain available.

Shortcuts: Ctrl+O adds PDFs, Ctrl+Enter starts a ready batch, Ctrl+H opens History,
Escape folds back to the wheel, and Alt+arrow keys move the shell. Dragging the
grip uses native Windows movement when available. The shell follows monitor and
available-work-area changes, clamping its position and switching its tray layout.
Closing while work is unfinished keeps the existing cancellation confirmation.

This is the first functional release of the shaped shell. Form transitions are
immediate; decorative morphing animation and system-wide Explorer drag shortcuts
are not included. No new conversion engines, external services or persisted
language defaults are introduced.

Validation covers native shape regions, real wedge selection, PDF drops, bound
conversion settings, output locations, queue/cancel/retry, close confirmation,
mixed-batch failure visibility, History lifetime and small-screen form bounds.
Normal and 150% scaling checks and packaged offline conversion checks are included.
