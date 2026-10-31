# YuzuFile desktop experience — v0.10.0

The redesign organizes the interface around documents, tools and a clear next action. Home and History remain the only main pages. No sidebar, dashboard, gradients, decorative imagery or additional settings page is introduced.

## Workspace

A compact document intake replaces the large upload form. Selected files sit directly below it. Six visual, keyboard-accessible multi-select cards communicate outcomes: Searchable PDF, Markdown, Word document, Smaller PDF, Split spreads and Clean up scans. Whole-card interaction, an icon, short supporting copy and a visible checked marker identify each action. Arrange pages is a full-width action card for merging and visual page management.

Relevant options are progressively disclosed: language choices for searchable text/Markdown/Word, quality for compression and split controls for spread division. Compression no longer occupies a disabled section. Reading order choices remain Right → Left, Left → Right, Top → Bottom and Bottom → Top. Clean up scans is the sixth tool card, beside Split spreads. Version 0.15 replaces numerical geometry forms with **Edit pages**: a draggable crop frame with shaded discarded margins, baseline alignment, rotation, thumbnail selection, undo/redo and a live result pane. Zoom/pan supports precise work on small screens. All split dividers are draggable, including unequal multi-part splits; Equal spacing resets them. Home and History remain the only main pages.

A fixed bottom dock keeps the output folder, performance choice, readiness and primary action available while content scrolls. The action changes to Make searchable, Export Markdown, Compress PDFs or Split spreads for a single tool, and Process PDFs for combinations. Icons expose accessible names and descriptive tooltips. Newly queued results are scrolled into view. Existing queue, cancel and green segmented progress behavior is retained.

## Visual language

Canvas #F4F6FA, white surfaces, text #182333, secondary text #606F84, icons #68788E, border #E3E8F0. Accent #2563EB with #EEF4FF selected surfaces. Success/error remain semantic; progress retains the supplied rounded green tick design. Segoe UI: 13 px body, 12 px secondary, 14 px card titles, 24–27 px headings. Panels/cards use 14 px corners, controls 9–10 px. No painted text is used for icon-only affordances; official Lucide SVG assets are bundled with their ISC license.

## Page workspace and History

Arrange pages uses a compact icon toolbar for undo/redo, movement, rotation and removal. Tooltips include keyboard hints. Save/extract remain labeled actions; source identity, output position and original page number remain on cards. Selected thumbnails retain their original paper colors instead of acquiring a system-generated tint. Undo and original-file preservation remain unchanged.

History expands search, uses quiet operation icons, clear status badges and compact open/retry controls, with full names in tooltips and the existing explicit overflow menu.

## Verification

95 UI, organization, storage, operation, spread and migration checks passed. This includes whole-card click/keyboard semantics, fixed action geometry across scroll positions at compact sizes, contextual actions, progressive settings, readable popup colors, original-file preservation, page-plan retry and real OCR. Empty/loaded/compact workspace, populated History and the page editor were rendered and visually inspected. New Lucide assets are recorded in src/yuzufile/icon_assets.py; shared visual controls are in src/yuzufile/ui_components.py. Back-end engines and output formats are unchanged.
