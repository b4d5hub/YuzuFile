# Visual page editing — v0.15.0

Select **Clean up scans**, then **Edit pages**. The editor works with the actual
PDF page; the result pane updates as you drag the crop frame.

- Drag an edge or corner to resize the retained area; drag inside to move it.
  Draw a new rectangle from the shaded area. Shaded margins are discarded.
- Scroll to zoom up to 5×. Hold Space and drag, or middle-drag, to pan.
  The Fit page icon restores the full-page view.
- **Straighten** lets you draw along a text baseline to make it horizontal.
  The slider gives live visual fine adjustment; **Auto straighten** detects tilt.
- Rotate left/right in the same editor. **Auto fit** detects content bounds;
  **Reset page** restores automatic geometry for that page.
- Select pages through thumbnails (Ctrl/Shift for several), then choose
  **Selected thumbnails** to process only those pages. An empty selection blocks
  processing. **All pages** processes the whole file.
- **Apply to…** copies the current geometry to selected thumbnails, all pages
  in the current PDF, or all added PDFs. Crop fractions adapt to each page size.
  Applying to the batch replaces earlier per-file edits and page selections.
- Undo/redo includes crop gestures, angle changes, rotations, reset and copy.
  Ctrl+Z, Ctrl+Y and Ctrl+Shift+Z are available. Arrow keys nudge the crop;
  Shift makes larger steps; Ctrl+arrows resize its lower-right corner.

**Preview split** now supports dragging every divider, for 2–12 unequal parts.
Output numbers follow the chosen reading order. Lines cannot cross; each part
must occupy at least 2% of the page (5% for a two-part split). **Equal spacing**
resets the lines. Changing the part count also resets spacing. Split direction,
part count and ranges remain explicit choices; positions are edited on the page.

No numerical margin padding or split-position fields appear on Home. Old jobs
retain their settings when retried. Visual edits are stored with the job and
identified by original source path; worker staging does not lose the association.

Preview/export share the same vector-preserving transform. The editor rasterizes
only the visible page for display, plus small on-demand thumbnails. Preview image
resolution is capped; export retains native PDF text, vectors and scan images.
Manual straightening is bounded to ±45°; automatic deskew remains conservative
at ±7°. Manual cropping intentionally removes content outside the chosen frame.
Selected form pages still require flattening first; annotated pages skip arbitrary
angle straightening to preserve annotations, with a warning. Original files are
never overwritten. Existing links, outlines and metadata use the transformed
geometry. Cleanup runs before splitting, OCR, Markdown, Word and compression.
