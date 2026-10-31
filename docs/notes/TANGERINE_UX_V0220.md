# Tangerine reference study and YuzuFile 0.22.0

## Sources inspected

- [Launcher and PDF details](https://tangerineformac.com/#details)
- [Merge PDFs](https://tangerineformac.com/tools#tool-mergePDF)
- [Compress](https://tangerineformac.com/tools#tool-compress)
- [Organize PDF](https://tangerineformac.com/tools#tool-organizePDF)

The website's launcher is an interactive simulation. I selected its PDF example,
opened the format wheel with Enter and applied the DOCX action. The menu closed
and a new output appeared beside the original. The site also describes dragging
a file, tapping a modifier to choose a contextual wheel, and dropping on an action.
This was a website interaction study, not a test of Tangerine's installed Mac app.

I inspected the full-resolution Compress, Merge PDFs, Organize PDF and Crop Image
window screenshots. They establish the task-window design more clearly than the
wheel alone. These images remain references; they are not application assets.

## What the references establish

The wheel selects an action and gets out of the way. A task with options opens a
focused window. There is no permanently attached universal settings form.

Windows use an off-white surface, rounded outline, soft shadow, centered title,
circular close control, thin separators and a stable bottom action area. Controls
are mostly neutral gray. Orange identifies the selected wheel sector, page order
and editing handles. File content and current settings take priority over prose.

Merge is a document-order list. Each row has a number, document icon and filename,
with small move controls. Organize is a page workspace: the page image occupies
the card, with an order badge and rotation control on the image. Compress shows
file context and original size before its preset controls. Crop places its
adjustment handles directly on a large content preview.

## Applied to YuzuFile's existing features

| Feature | Resulting interaction |
| --- | --- |
| Launcher | One normal click opens one tool. The wheel closes while the task is open. Shift-click and Add tool explicitly combine operations. |
| OCR | Focused file list, available-language checkboxes, output folder, performance level and one action. |
| Word / Markdown | The same focused conversion window; existing fresh page OCR and editable exports remain intact. |
| Compress | Original-size context, Lossless/Balanced/Maximum segmented presets and a fixed action area. |
| Remove OCR | Image-only explanation beside the input list, with no language controls. |
| Merge PDFs | Whole-document rows with drag ordering, move arrows, removal, Add PDFs and output-folder selection. Uses the existing page assembler. |
| Arrange pages | Compact toolbar, large page cards, orange order badges and per-card rotation. Multi-selection, drag feedback, undo/redo, extraction and full-size inspection remain available. |
| Clean up pages | Large edit canvas; Crop/Straighten/Pan show relevant controls. Pages opens the thumbnail strip; selected-page scope opens it automatically. |
| Split spreads | Two compact control rows, fit-width startup, direct cut-line dragging and ranges in the footer. All four orders and 2–12 parts remain available. |
| Processing/results | Movable compact status window with persistent Back to tools. A file selector exposes every result in a batch. Details stay folded by default. |
| History | The same tool-window chrome, with search, status filters and existing file actions. Closing History restores the launcher. |

YuzuFile keeps Windows shortcuts and its current backend capabilities. Tangerine's
target-size compression, media resizing and unrelated file tools are not added.

## YuzuFile visual implementation

- Segoe UI: 13 px body text and a 16 px semibold centered tool title.
- Tool header: 48 px; body spacing: 8–12 px; body inset: 16–18 px.
- Window surface: `#f8f8f8`; borders/dividers: `#dddddd`.
- Text: `#454545`; secondary text: `#737373`.
- Neutral rounded buttons and inset segmented controls.
- Orange wheel selection and page-editing feedback; success/error colors are reserved for status.
- Rounded frameless tool windows retain moving, minimizing, maximizing and corner resizing.
- Tool windows have an independent Windows taskbar presence while the launcher is hidden.

## Data and output behavior

Existing OCR, language, performance and output-folder settings stay bound to the
same controller. Originals remain unchanged. Existing History entries are not
renamed. New merge jobs use `<first document>_merge.pdf`; other operation suffixes
continue to follow the source-name convention introduced in 0.21.1.

## Verification

Existing geometry and page-plan tests cover anchored zoom/pan, fit-width startup,
pixel limits, all split directions, crop scopes, page rotation, drag feedback,
extraction and unchanged sources. New interaction checks cover single-tool
launching, explicit combinations, modal return to the launcher, batch result
selection, merge order and merge output naming. A separate real Qt event-loop
check confirms that closing a focused tool does not quit YuzuFile.

Visual QA includes large and small editor windows, Straighten and Pages states,
and the current launcher, conversion, compression, merge and arrange windows.
