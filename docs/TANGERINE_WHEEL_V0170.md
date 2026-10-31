# PDFai 0.17.0 sculpted tool workspace

This revision replaces the rectangular tool grid with a file-centred radial
menu, following the sculpted wheel and compact gray tool-window examples at
https://tangerineformac.com/ and https://tangerineformac.com/tools.

Seven rounded sectors surround the PDF input: OCR, Word, compression, cleanup,
spread splitting, Markdown, and page organization. The six conversion sectors
remain independently selectable, so batch operations can still be combined.
Arrange opens the existing visual page organizer. The center browses for PDFs
and accepts the existing window-level PDF drop flow. With files selected, it
shows their count. File names and remove actions remain below the wheel.

The wheel uses native Qt checkbox and push-button semantics. Each sector has
its own shaped mouse region, accessible name and description. Tab and arrow
keys move focus; Space toggles a conversion. The silver rim, rounded sectors,
soft shadow and orange selected surfaces are painted as vectors at runtime.
The application introduces no raster artwork, model downloads or dependencies.

Tool windows now use a cool silver palette, inset fields, raised gray action
buttons and a segmented compression preset control. The default workspace is
720 by 760 logical pixels, limited by the available screen. Compact windows
scroll above a fixed action dock. Processing messages stay collapsed initially.

Validation covers all seven click regions, the center input, combining tools,
arrow/Space navigation, resized hit regions and compression preset binding,
alongside the existing UI and cleanup tests. The build now compares frozen
application modules with the current source before making the portable ZIP.
