# Page-first cards — 0.19.1

Arrange pages now draws the PDF preview directly, filling the card above a fixed,
two-line caption. Increasing Page size grows the PDF image; the caption stays the
same height. The initial preview is 300 pixels wide, with adjustments from 160 to
480 pixels. Filenames are elided within the caption, with full details in the
tooltip and full-page viewer.

Cards follow each page's aspect ratio and planned rotation. Landscape pages use
shorter cards instead of leaving a tall blank area below the preview. Portrait
pages keep their proportions. Mixed portrait/landscape documents are supported.
Exceptionally tall or wide pages fit proportionally into a bounded preview.

The floating drag card also follows the page proportions. Selection, insertion
markers, moved-page highlights, undo/redo and full-page viewing remain available.

Page dimensions are read without rasterizing the document. Only visible previews
are rendered, using images sized for the preview and display scaling. Offscreen
cards release their images; the thumbnail cache remains bounded.

Validation includes rendering solid-color portrait and landscape PDFs and checking
their actual painted pixels, preview proportions, fixed caption height and image
growth when resizing. The checks run at normal and 150% display scaling.
