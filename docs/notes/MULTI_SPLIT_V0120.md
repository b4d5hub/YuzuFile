# YuzuFile 0.12.0 — multiple sections per page

Split spreads now includes a **Parts per page** count from 2 to 12. A count of
3 creates two cut lines and three output pages for every selected input page;
4 creates three cut lines and four outputs. This divides each selected page
once into the requested number of sections, rather than recursively halving it.

The four orders remain Left → Right, Right → Left, Top → Bottom and Bottom → Top.
In v0.12, for more than two parts the sections are equally sized. Version 0.15
adds draggable dividers for unequal parts; see [visual editing](VISUAL_EDITING_V0150.md).
Two-part splits keep the
existing adjustable 5–95% position and draggable preview divider. The preview
shows every divider, numbers sections in output order, and updates the total
output page count. Page ranges still let covers or other pages remain intact.

History stores the count with each job; Process Again restores it. Existing
history without a count continues to use two parts. No database migration or
saved preference is needed. CLI callers can pass `--split-parts N`.

Splitting runs before OCR, Markdown and compression. Clipping, native document
quality, rotation/crop normalization, hidden-text removal, links and bookmarks
use the same processing path as the original two-part operation. Output is
limited to 4,000 pages; excessive requests fail before pages are copied. The
preview also reports this limit. Original files are not overwritten.

Validation: 140 targeted tests passed. New coverage includes 3/4/12 parts in all
four directions and all rotations with cropped pages and exact raster comparison,
opposite-section hidden-text removal, selected ranges, output limits, numbered
preview controls, legacy/new History retry and split + Markdown/compression.
The three-part preview was also rendered and visually inspected.
