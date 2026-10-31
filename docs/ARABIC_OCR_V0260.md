# Arabic print OCR, version 0.26.0

The supplied ten-page Arabic book sample exposed two independent failures:
Indra's recognizer dropped and misread vowelled Naskh lines, and MuPDF's default
font fallback lost combining vowel marks in the invisible PDF text layer.
Higher resolution alone did not correct recognition. RapidOCR Arabic mobile,
Tesseract fast/best, PaddleOCR-VL 1.6 and LightOnOCR 3 also made errors on this font.

When Arabic is selected, Indra provides orientation and document layout, while
Kraken PP-OCRv6 medium recognizes independently detected text lines. The 64 MB
SquiddleOCR ONNX conversion runs with the existing CPU ONNX runtime. It uses
RGB line images at height 96 and CTC decoding followed by bidirectional ordering.
English/French lines retain their established Indra readings. There is no language
model rewriting, spelling substitution or cross-engine confidence averaging.
Arabic processing also runs when Indra finds no rows, allowing independent line
detection to recover omissions. Blank pages remain blank.

Page raster input is now 300 dpi, capped at eight million pixels. One page and
one line are processed at a time. Thread budgets follow the performance preset;
the isolated helper exits after each page to release native model memory. The
same fresh logical rows feed searchable PDF and Word. Arabic Markdown keeps
the specialized transcript instead of replacing uncertain prose with a general
vision model; tables retain their separate layout verification path.

The invisible Arabic overlay explicitly uses Windows Arial when available,
normalizes presentation forms and nonbreaking spaces, and uses an RTL boundary
to keep final vowel marks attached during extraction. Latin rows keep their
existing font mapping. OCR text is invisible and must not change visible pixels.

Recognition is still imperfect. Vowelled Arabic, decorative lettering, names,
and Arabic/Persian lookalike code points need review. Warnings flag vowelled or
uncertain pages; model confidence is not an accuracy guarantee. The fallback
Tesseract path refuses partial language loading instead of silently producing
Latin-only OCR after Arabic data fails to load.

Model provenance: Benjamin Kiessling, Kraken PP-OCRv6 medium,
https://doi.org/10.5281/zenodo.21788410; ONNX conversion by
https://huggingface.co/storytracer/squiddleocr, pinned revision
0e05fbe9d0a2df35871ccbe881c0c3d1380fcdd5. Apache-2.0 model license, original
model card, NOTICE and conversion parity metadata are included. Files and hashes
are in `arabic-print-model.json`; `scripts/prepare_arabic_print.py` acquires them
explicitly. Runtime never downloads models. Existing Indra model terms still
apply to this personal-use build.

## Validation on the supplied document

The final source run processed all ten pages in 78.93 seconds with four CPU
threads (development run; not a universal speed estimate). It recognized nine
nonblank pages and left the genuinely blank second page without text. All ten
saved pages matched the source raster at reading resolution (mean RGB difference
0.0); saved text had no NUL/missing-character codes. The original file's SHA-256
was unchanged. Independent detection recovered lines omitted by the original
recognizer, including the prayer-conditions line on page ten. Two bounded crop
retries improved the overlapping line containing المقدمة الآجرومية.

Seventy-four focused regression tests pass, covering CTC/bidi decoding, partial
language failure, independent line recovery, Arabic vowel extraction/search,
unchanged PDF rendering, Word mixed scripts/fresh-cache reuse, page sequencing,
and resource budgets. This verifies preservation and integration, not perfect
OCR. Arabic/Persian character variants, some names and vowel marks remain wrong
in the sample. Review the transcript before treating it as authoritative.
