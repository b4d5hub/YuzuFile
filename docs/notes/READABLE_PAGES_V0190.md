# Readable page workspaces — 0.19.0

The cleanup editor now gives the page the full available width. Edit and Result
switch between two large views instead of dividing the window into small panes.
Each view keeps its own zoom and scroll position. Fit width is the initial view;
Fit page shows the whole sheet. Use the percentage, +/− buttons or Ctrl+scroll to
zoom. Ordinary scrolling moves through the page. Space+drag, the middle mouse
button, or the Pan tool moves the editing view without changing the crop.
Crop handles are larger, and side handles stay reachable when zoomed in.
The window can be maximized. A one-page PDF hides the thumbnail strip unless
thumbnail selection is needed for processing scope.

Arrange pages has larger cards and a Page size slider. Double-click a card or
choose View page to inspect it at full width, with the same zoom and pan controls.
Previous and Next follow the planned output order. The viewer identifies the
source file, original page and planned rotation; viewing never changes the plan.

Dragging shows a floating page card and moving-page count. Source cards fade
while moving. An orange insertion line and “Drop before page…” label identify
the destination. Dropping on the right half of a card inserts after it; the left
half inserts before it. At the end, the label reads “Drop at end”. Moved pages
remain selected and briefly show an orange border and “Moved” label. A message
reports the output positions. Cancelled and unchanged moves are identified.
Undo/redo, rotation, extraction and source-file protection are retained.

Only the current reading page is rasterized. Raster size is capped at 8 million
pixels and 6,000 pixels per side; extreme zoom can therefore reach the preview's
resolution limit. Zoom changes are debounced. Thumbnail generation remains
restricted to visible cards and has a bounded cache. Previews do not alter the
PDF or save screenshots into exported documents.

Launch the updated version using the workspace YuzuFile shortcut or
`dist/YuzuFile-0.19.0/YuzuFile.exe`. Close an older app normally after finishing any open
editing session, then reopen using the updated shortcut.
