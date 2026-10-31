# Split spreads — v0.8.0

Home adds Split spreads as a fourth operation. A two-column operation layout keeps compact windows usable. Split controls appear only when selected: four orders (Right → Left, Left → Right, Top → Bottom, Bottom → Top), a 5–95% split position starting at 50%, page ranges, and Preview & Adjust. Blank/All means every page. Unselected pages remain intact. Configuration applies to the batch; History stores it per job and Process Again restores it. No saved preference is introduced.

Preview loads one PDF and renders one page at a time, bounded to 1,100 px per side. File/page controls, a draggable dividing line, first/second labels, output count and Apply/Cancel provide inspection without OCR. Changed settings apply only on Apply.

The worker splits first, then runs existing OCR/Markdown/compression. PDF clipping preserves native text, vectors, and embedded images, and removes the other half's hidden text rather than merely hiding it with a crop box. Crop boxes and rotations are normalized while retaining visible geometry. Basic bookmarks are remapped to the first output half; resolvable internal and external links are remapped to the appropriate half. Annotation crossings and unresolvable links produce warnings. Interactive form fields on selected pages are rejected with instructions to flatten first. Existing password/signature restrictions remain.

Processing uses the current performance profile's bounded page traversal, native worker isolation, cancellation, staged atomic publication, output location and recorded-only deletion. A compression no-savings fallback uses the split document, never the unsplit source. Original input limits remain 2,000 pages; splitting can produce up to 4,000 pages. Splitting does not promise smaller files.

Output names: document.split.pdf for split alone or split + Markdown; document.ocr.pdf with OCR; document.compressed.pdf with compression. Only the final PDF is retained alongside optional Markdown/assets.

History schema migration 5 adds split_settings with an empty JSON default. Existing seven operation modes retain their meaning, including all (OCR + Markdown + Compress). Eight new modes cover every combination with splitting, for 15 nonempty combinations total. CLI exposes --split-order rl/lr/tb/bt, --split-position, --split-pages.

Validation: 73 targeted UI/storage/operation/migration/conversion tests passed, plus a separate real OCR test on a scanned spread (74 checks total). Coverage includes all four orders, exact rendered pixel comparisons across all rotations with cropped pages, unchanged scan pixels, opposite-half hidden text removal, range/cover behavior, custom split positions, link/bookmark/annotation preservation, all supported output types, preview dragging, original file preservation, custom output folders, and retry settings. Home/preview and both resulting PDF halves were rendered and visually inspected.
