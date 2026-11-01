# Legacy Arabic font recovery — v0.15.2

Some older Arabic PDFs draw Arabic letters correctly while their text extraction
returns Latin letters, punctuation or other readable Unicode garbage. This is
different from RTL formatting and can occur without any replacement-character
marker. Word cannot recover the intended Arabic by changing paragraph direction
or substituting an ordinary font for those Latin codes.

Word export now checks decoded character codes against the embedded TrueType or
OpenType font's Arabic glyph IDs, and visually checks Type 3 glyph fonts. A strong mismatch triggers a bounded full-page
visual OCR pass, even when no OCR language was selected for an otherwise native
PDF. A legacy script-font hint or an Arabic selection with no extracted Arabic
also triggers a visual check. Valid English text remains native when Arabic OCR
is not confirmed; a missing ToUnicode map alone does not prove corruption.

Confirmed OCR becomes the editable text reference for the affected page. This
prevents coverage recovery from appending the original garbled text again.
Native ruled-table geometry can still be reused, with cells filled from logical
OCR strings. The quality report records `legacy_arabic_recovered` per page and
History includes the OCR review warning. If font evidence confirms a bad Arabic
map and OCR cannot recover reliable Arabic, export fails clearly instead of
publishing a known-garbled Word document. Rotated legacy pages may need to be
rotated upright before this recovery can run safely.

When fast OCR misses dense vocalized Arabic, the bundled Paddle model processes
small paragraphs sequentially with a reduced 2,048-token context. Up to eight
detected lines share a region; input strips are capped at 1,024 × 700 pixels.
This detailed fallback can take minutes per difficult page on CPU. Existing
performance presets control its threads and the worker's resource limits.
Glyph-position coverage checks reject a heading-only recovery; that metric
measures retained locations, not whether the recognized words are correct.

Processing stays local, one bounded page at a time, within the existing preset.
No new model or dependency download is needed; FontTools was already pinned in
the build. This recovery is not a guarantee of correct OCR spelling or numbers.
Unusual font formats or stripped embedded character maps can still need review.
Selecting Arabic helps the visual check when embedded font evidence is missing.

Regression QA deliberately changes a PDF's ToUnicode map while verifying its
rendered pixels are unchanged. The file displays Arabic but extracts Latin
garbage. Tests verify recovery without an explicit language selection, explicit
Arabic fallback, hybrid OCR markers, rejection when recovery is unavailable,
valid English preservation and no duplicate garbage in coverage recovery.
`scripts/verify_legacy_arabic_word.py` exercises the real local OCR models.

A five-page test document used Type 3 Arabic fonts. Its
page 3 reproduced the screenshot. Fast OCR missed most of its vocalized body;
detailed OCR recovered readable Arabic but still made spelling and vowel-mark
errors. The source PDF remains authoritative. These changes fix the Latin
gibberish failure; they do not make this book's OCR a verbatim transcription.

Decorative vector covers with sparse hidden OCR are preserved as replaceable
page images. The unreliable hidden text is discarded. Figure labels remain
inside their replaceable images, without duplicate editable paragraphs below.
Word reflows editable text, so page counts and line breaks may differ from the
source. The five-page user file was converted in full for review, not just its
first-page heading. Spelling, vowel marks and layout still require comparison
with the original PDF.
