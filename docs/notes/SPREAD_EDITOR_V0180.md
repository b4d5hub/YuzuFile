# Readable spread editor 0.18.0

Spread preview now opens at page width instead of shrinking a portrait page to
fit its height. Its window uses more of the screen and supports Maximize and
Restore. A scrollable canvas provides Fit width, Fit page, zoom buttons, a zoom
percentage field and Ctrl plus mouse-wheel zoom anchored at the pointer.

Drag the page background, hold Space while dragging, or use the middle mouse
button to pan. A background click no longer jumps a cut line to that position.
Dividers have an expanded hit area and 18 by 52 logical-pixel handles, which
stay centred in the visible part of a vertical cut while scrolling. Horizontal
cuts get equivalent horizontal handles. Choosing a divider brings it into view.

The selected divider remains selected after releasing the mouse. Arrow keys
nudge it by 0.1 percentage point; Shift plus an arrow moves it by 1 point. The
divider selector and percentage field provide precise positioning, including
for multi-part splits. All pointer coordinates are mapped back to PDF-relative
fractions; changing zoom and panning do not change the saved split positions.

Only the current page is rasterized. Zoom changes are debounced for 140 ms, with
an eight-million-pixel and 6,000-pixel-per-dimension raster budget, including on
high-DPI screens. A transformed cleanup page is retained only while that page
is being previewed. Closing the editor stops pending rendering and releases it.

Validation covers fit modes, cursor anchoring, background panning, reachable
handles, horizontal cuts, selected-divider keyboard edits, raster limits,
closing cleanup, and PDF export geometry. The input PDF is never saved by the
preview editor.
