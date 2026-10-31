# PDFai 0.11.0 validation — 2026-10-23

This is a personal-use build, as explicitly requested by the user. It bundles
Indra Python 1.1.2 and pinned official 1.1.0 weights. No model weights were
modified. License texts and attribution accompany the app and affected outputs.

## Completed source checks

- Final adapter/performance/UI/history/organization regression run: 84 passed.
- Final spread/compression/Markdown fallback/runtime regression run: 54 passed.
- Conversion/neural/resource batch: 56 passed; two old performance mocks initially
  failed because they disabled RapidOCR but left the new Indra engine enabled.
  Those tests were updated to cover no neural engine, RapidOCR and Indra, and
  passed in the final 84-check run above.
- Real Windows CPU recognition of a mixed English/French/Arabic scan succeeded.
- Four raster-only orientations (0/90/180/270) retained readable multilingual
  text and unchanged PDF raster samples. The initial fast-only test exposed
  malformed table columns; tables now route to detailed verification.
- Synthetic overlay placement tests verify orientation and unchanged pixels.
- Missing/incomplete models cannot trigger an automatic download; failed/empty
  OCR attempts fall back to the existing engines. Forced Markdown failure tests
  verify text preservation, uniquely named assets and correct image links.
- HTML cell markup is removed for coverage checks to prevent duplicate text
  recovery. Native PDF text omitted by layout extraction is retained.
- Final Unicode/figure checks: 19 passed. Exact Arabic text search works after
  saving/reopening overlays in all four orientations, with unchanged pixels.
  The conversion rerun exposed one missed embedded-figure export; it was fixed
  and that real conversion regression passed in this final check.
- Real Indra inference also passed from a Windows path containing French and
  Arabic characters. Image bytes are opened through NumPy, avoiding OpenCV's
  Windows filename limitation. The final 19-check run covers this path too.

## Difficult chapter sample

Indra alone was insufficient: it garbled an attack-chain diagram, although it
retained both chart percentages. Adaptive table/uncertainty routing to the
existing detailed pipeline corrected the diagram.

The two-page local sample completed in 231.39 seconds on Balanced, with no
warnings. Assertions verified all seven labels (Recon, Weaponize, Deliver,
Exploit, Install, C2, Execute), 43% SMB and 57% Enterprise, and unchanged PDF
appearance. This is a limited sample, not an accuracy guarantee or a controlled
speed comparison. Difficult pages remain substantially slower than ordinary OCR.

## Limits

The tests run on this Windows machine, not a clean VM or a broad independent
document corpus. Math models are not enabled. Handwriting, faded scans and
complex tables still require review. Recognition confidence does not guarantee
correctness, and adaptive routing cannot detect every OCR error.
