# Arabic Word export — v0.15.1

Choose **Word document**. For scanned PDFs, select **Arabic**; also select
**English** for bilingual material. Existing native Arabic text is reused when
its mappings are readable. Conversion remains local and needs no new download,
paid service or GPU. Existing performance presets and cancellation still apply.

This release addresses failures reproduced with shaped Arabic PDF text:

- Native table extractors could return visually reversed Arabic strings.
  Cells now reuse glyph coordinates to reconstruct logical Arabic text.
- One bilingual baseline could be exported as many separate lines. Nearby
  horizontal fragments are reunited without joining distant table columns.
- Word paragraphs use RTL alignment when their first strong character is RTL.
  Arabic and Latin/numeric runs have separate direction; identifiers, emails,
  amounts and dates remain editable. Complex-script font, size, language, bold
  and italic properties are explicitly written. Diacritics stay with letters.
- Arabic tables have RTL logical order while retaining source physical column
  positions and widths, including merged cells and numeric-only paragraphs.
- A single damaged font mapping no longer causes the whole native page to be
  replaced by OCR. When possible, only the affected word is repaired; valid
  neighboring text and numbers remain native. Broader repairs are disclosed.
- Scans reuse logical OCR strings rather than converting them back through a
  potentially damaged invisible PDF font. Verified grid tables remain editable.
  Low-confidence Arabic pages may receive one additional bounded RapidOCR pass
  to recover standalone numeric cells. Mixed sentences are never replaced by
  a numeric-only recognizer result. Confident pages skip this second pass.

OCR can still misread Arabic spelling, vowel marks, percentages, dates and
numbers. The QA fixture demonstrates this limit: text/table direction is fixed,
but some scanned numeric values still differ from the original. Review warnings
and compare important values with the PDF. Extracted-text coverage is not an OCR
accuracy score. No perfect-conversion claim is made.

Tests cover glyph order, marks, mixed-script runs, Arabic formatting, table
merges/widths, native bilingual PDFs, selective mapping repair, numeric fallback
and avoiding unnecessary model loads. `scripts/verify_arabic_word.py` generates
native/scanned Arabic and mixed-language fixtures. Development QA renders the
DOCX files through the document renderer; LibreOffice is not required by PDFai.

OOXML references: [RTL run formatting](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.righttolefttext)
and [RTL table presentation](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.bidivisual).
