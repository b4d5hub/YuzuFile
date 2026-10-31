# Remove OCR and fresh page recognition — 0.21.0

Remove OCR creates a new image-only PDF. All visible text, graphics and current
annotation/form appearances are rendered onto the page image. Old hidden text,
fonts and page resources are not copied. The output has no searchable/selectable
page text or editable form fields; the original PDF stays unchanged. Page sizes,
visible orientation, bookmark titles/destinations and supported navigation links
are retained. Rendering targets 300 DPI, bounded to 8 million pixels per page.
Image streams use lossless compression; the optional Compress tool applies its
selected quality level afterwards. Rasterization can change file size.

Remove OCR can be combined with cleanup, spread splitting and compression. It is
exclusive with OCR, Word and Markdown: selecting a recognition tool deselects
Remove OCR, and vice versa. Recognition already performs the cleanup internally.
Standalone output is `document.no-ocr.pdf`; with compression the single output
is `document.compressed.pdf`, which remains image-only.

All recognition now ignores the PDF's old text layer, including PDFs with native
digital text or a YuzuFile OCR marker. It needs selected OCR languages. Each source
page is rasterized into a fresh page, recognized by the local OCR engines, and
marked with fresh provenance. No old text is retained as a fallback. Unsupported
or failed recognition fails clearly or reports an empty recognized page instead
of silently restoring the old layer.

Word export follows the literal sequence: clean page 1, recognize page 1, append
editable Word content for page 1, then repeat for page 2. The writer consumes the
fresh logical OCR rows and layout cache, including Arabic, and does not run the
full-page recognizer again. It keeps source-page section order, editable detected
tables and replaceable figures. Physical Word pagination and OCR spelling remain
approximate; the quality report records fresh recognition for every source page.

Searchable PDF creation cleans and adds the new text overlay one page at a time.
Markdown uses those freshly recognized pages and cached layout, with sequential
visual fallbacks when detailed verification is needed. If Word is selected too,
PDF and Markdown reuse the pages prepared while Word was built.

Only one page is cleaned and recognized at a time. Performance levels continue to
control internal model threads, CPU and memory limits. Completed PDF pages spill
to incremental disk checkpoints instead of accumulating decoded raster buffers;
temporary rasters are removed before the next page. The source file is never
overwritten, and failed attempts do not publish partial outputs.

Validation includes deliberately incorrect hidden OCR beneath correct visible
text, all three recognized exports, blank/rotated pages, Arabic logical rows,
editable tables, image-only text/font checks, checkpoint reopening, and failure on
page 2 without a partial Word export. Real local Tesseract and Indra checks both
discarded the deliberately incorrect layer and recovered the visible text.
