# Local editable Word export — v0.13.0

Choose **Word document** on Home, select languages for scanned pages and click
**Export Word**. Word can also be combined with searchable PDF, Markdown,
compression and spread splitting. Queue, cancellation, output directory,
performance levels, History and retry work as with existing conversions.

The priority is editable text and tables, replaceable images, and approximate
layout preservation. Conversion runs locally without a paid API, office suite,
GPU requirement or first-run model download. The existing personal-use model
license remains applicable when Indra processes a document.

## Adaptive processing

1. Reuse native PDF text and font information. Scans use the existing OCR pass;
   its cached Indra results are reused. Existing scanned OCR PDFs can receive
   a layout pass without discarding their text. Broken character mappings trigger
   local OCR repair where available, with a warning.
2. Detect vector tables with PyMuPDF, considering text alignment when no ruled
   table is found. OpenCV recovers full grid geometry from scans. Indra HTML
   offers another editable-table candidate, including HTML row/column spans.
3. Compare candidates with extracted region text and numbers. Reject uncertain
   cells instead of silently substituting model wording. Unresolved Indra table
   regions receive a selective local PaddleOCR-VL pass, one region at a time.
   If verification fails, retain editable text and report the uncertainty.
4. Reconstruct paragraphs and tables with python-docx 1.2.0. Preserve source page
   sizes/orientation, approximate indentation and vertical gaps, font sizes,
   bold/italic/color, and Arabic direction. White PDF text becomes dark on Word's
   white background. Missing installed fonts can be substituted by the editor.
5. Embed source images, vector illustration crops and detected scan figures as
   ordinary replaceable Word pictures. Whole-page images are a last resort for
   pages without recognized text, and are explicitly reported as non-editable.
6. Recover omitted extracted text, reopen the saved DOCX, check the archive and
   compare editable text coverage. Write `document.quality.json` beside the DOCX.

Only one large table model runs at a time. Page rasters are capped, caches are
trimmed between small page parts, and existing performance CPU/memory budgets
apply. Word XML and embedded output images accumulate until the document is saved;
very large documents can still exceed the configured memory budget.

## Quality limits

The report measures preservation of **extracted/recognized text**, not whether OCR
recognized the source correctly. It does not claim visual equivalence or perfect
conversion. Runtime conversion does not render through LibreOffice. Development
QA renders representative exports separately.

Complex columns are converted to a reading sequence and flagged. Floating objects,
exact pagination, complex equations, decorative panels, rotated scan layouts and
unusual table structures can require manual adjustment. Pictures remain images,
not editable vector drawings. A model can miss a figure or misread text; original
PDFs remain the source of truth. No new content is intentionally generated.

## Validation

Automated checks cover editable native text, invisible OCR layers, table cells and
numbers, scanned grid geometry, broken character-map repair, RTL text, source
orientation, replaceable images, column reading order, UI submission and History.
`scripts/verify_word_export.py` exercises real local OCR on matching native/scanned
fixtures and checks numeric values, an editable table and one figure.

Representative DOCX files are rendered with a temporary local LibreOffice copy;
the app does not install or bundle that QA copy. Inspect every rendered page.

Primary library documentation:
- [PyMuPDF extraction and table detection](https://pymupdf.readthedocs.io/en/latest/page.html)
- [python-docx 1.2.0](https://python-docx.readthedocs.io/en/latest/)
