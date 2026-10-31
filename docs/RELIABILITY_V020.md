# v0.2.0 reliability and speed work

The user's 81-page, 92 MB scanned document exposed a whole-document OCR failure (OCRmyPDF exit code 4). A later successful PDF-only attempt recorded 217.23 seconds in application history. The old code discarded engine logs and reported only the numeric exit code; the exact cause inside that engine cannot be reconstructed from the saved record.

## New pipeline

- PyMuPDF renders pages directly to RGB, removing transparency/color-space complications. Recognition images are capped at eight million pixels and normally rendered at 220 DPI.
- Tesseract runs on at most four pages concurrently, one native OCR thread per page. All MuPDF operations stay on the main worker thread; MuPDF is not called concurrently from Python threads.
- A small invisible text-only PDF is overlaid on each original page. Existing graphics/images are preserved, native text is masked only in the temporary recognition image, and existing searchable Tesseract scans are reused.
- Failed/timed-out pages get one lower-resolution retry. A second failure identifies the page and stops publication. A page with no recognized text produces a review note rather than claiming OCR accuracy.
- Original PDF objects are saved without rasterizing/recompressing the complete document. Whole-document OCRmyPDF/PDFium/PDF-A checks are no longer on the conversion path.
- Markdown is written page by page. Full-page scans are not embedded again; actual figures are linked through managed image assets. Layout extraction can fall back to readable plain text with a note.
- Output page/text checks, staged publication, process-tree cancellation, source preservation, and history/deletion containment remain in place.

## Evidence

The same real document completed in 109.88 seconds for **both PDF and Markdown**, versus the previous 217.23 seconds for PDF alone. These are observed local runs with different pipeline work, not a controlled general-purpose benchmark or a universal speed promise. All 81 pages contained recognized text. The Markdown was 41,733 bytes, and the PDF was approximately 92.5 MB. Rendered comparisons of pages 1, 41, and 81 had identical pixels at 72 DPI. No private extracted content is recorded in this report.

The 27-test source regression suite passes, covering real synthetic OCR, mixed native/scanned content without duplicated captions, rotation appearance, alpha transparency, oversized-page render bounds, reuse of searchable scans, linked Markdown figures, no embedded scan/base64 bloat, corrupt/encrypted files, cancellation, app-death cleanup, history persistence, safe deletion/junction handling, installed-only languages, and per-conversion resets. Two additional tests pass for missing-library and per-page-layout failures preserving readable Markdown, bringing coverage to 29 tests.

Packaged testing also caught a PyMuPDF4LLM import requirement: version 1.28.2 imports ONNX Runtime even with model-based layout disabled. The build keeps this required dependency, disables unused model-based layout, and tests that ordinary conversions do not silently fall back. Fallback notes remain available for unusual documents or a damaged layout component.

The simplified UI keeps the user on the conversion screen, displays page progress, offers cancellation and direct result actions, and shows completion/review notes. Language defaults are still not saved. The portable build includes English, French and Arabic recognition data; multiple choices are supported.

## Final packaged verification

The final Windows executable completed the same 81-page document in 133.02 seconds for both outputs, with no review/fallback warnings. All 81 PDF pages contained recognized text; final-executable page renders at 1, 41 and 81 matched the original pixels. This packaged run occurred alongside packaging/smoke work, so it should not be treated as a controlled comparison with the 109.88-second source run. Both improve on the recorded older 217.23-second PDF-only attempt.

The complete 29-test source suite passed. Packaged GUI startup, digital Markdown, scanned PDF/Markdown, normal structured extraction without fallback, and combined English/French/Arabic model loading passed with developer tools removed from PATH. The 191.6 MB portable ZIP passed an archive CRC check and includes all three recognition languages. A clean Windows VM remains a separate release gate.

Recognition quality still depends on scan clarity and selecting the actual languages. Presence of recognized text is not an accuracy score. Handwriting, complex tables, and mixed RTL/LTR reading order are not claimed to be universally correct. Broad quality benchmarking and clean-machine validation remain open release work.
