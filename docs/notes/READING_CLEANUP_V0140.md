# Reading cleanup — v0.14.0

Historical release notes. Version 0.15 replaces the numerical controls below
with [visual page editing](VISUAL_EDITING_V0150.md).

The reading workflow now covers rotation (Arrange pages), spread splitting
(2–12 parts, four orders), automatic straightening and excess-margin trimming.

Select **Clean up scans** on Home. Choose **Auto straighten**, **Trim margins**,
or both. Padding is initially 3 mm and adjustable from 1 to 20 mm. Leave the
page field blank for all pages, or enter a range such as `2-15, 18`.
**Compare pages** shows original and cleaned pages side by side, with the
estimated correction and resulting page size. Options can be adjusted there
before returning to Home. No new main page or saved preference is introduced.

## Processing

- Cleanup runs before spread splitting, OCR, Markdown, Word and compression.
  Split preview includes cleanup when both tools are selected.
- Automatic straightening handles reliable small tilts up to 7 degrees.
  Native PDF baselines are reused when consistent; scans use bounded raster
  analysis and horizontal projection, with a minimum improvement threshold.
  Ambiguous pages remain unrotated. Quarter-turn rotation stays in Arrange pages.
- Export applies PDF transformations rather than rasterizing complete pages.
  Text stays searchable, vectors remain vectors, and source scan image bytes
  are retained. Raster analysis is capped at 3 million pixels and processed
  one page at a time, within existing worker resource limits.
- Trimming detects visible content and retains padding. Native text, hidden
  OCR text, small embedded images, faint vector artwork, footers and annotations
  expand the retained area. Blank, sparse or dark-edged pages may remain unchanged
  with a recorded explanation. Scanner shadows and complex backgrounds can
  prevent useful trimming; preview the result.
- Selected interactive form pages require a flattened copy. Unselected form
  pages remain intact. Arbitrary-angle straightening is skipped on annotated
  pages to preserve their annotations; trimming can still apply.
- Links and bookmark destinations are remapped. Document attachments and
  metadata are retained through a disk-backed working copy. Unselected pages
  retain their content and page geometry.

Originals are not overwritten. Cleanup alone saves `document.cleaned.pdf`.
When combined with searchable PDF or compression, the corresponding PDF is
the final result. Cleanup + Markdown/Word also includes a cleaned PDF. With
splitting, the existing split output convention applies. Compression's
no-savings fallback retains the cleaned intermediate, not the original scan.

History records each job's options, applied angles, changed page dimensions,
trimmed/straightened counts and warnings. Retry restores its options. Schema
migration 7 adds `cleanup_settings` with an empty default for old jobs; existing
history mode identifiers retain their meaning.

## Validation

Tests cover native/scanned skew correction, unchanged source hashes and image
bytes, footer/text preservation, all quarter-turn rotations with crop boxes,
faint artwork, blank pages, annotations, form rejection/preservation, links,
bookmarks, attachments, page ranges, worker outputs, compression fallback,
preview controls, queueing and retry. `scripts/verify_cleanup.py` creates matching
native/scanned fixtures and verifies their results. Render final pages using
PDF crop boxes, for example `pdftoppm -cropbox -png`.

Primary API reference: [PyMuPDF page transformations and clipping](https://pymupdf.readthedocs.io/en/latest/page.html).
