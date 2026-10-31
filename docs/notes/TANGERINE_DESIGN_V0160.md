# YuzuFile design system 0.16.0

Reference: https://tangerineformac.com/ (reviewed 27 October 2026).

The desktop interface takes inspiration from Tangerine's pale neutral canvas,
white rounded surfaces, charcoal type, orange accents and softly raised controls.
YuzuFile keeps its own document icon, Windows typography and batch-processing flow.

Shared colors live in `src/yuzufile/ui_style.py`. The canvas is warm gray `#f5f4f2`,
surfaces are white, text is charcoal `#292724`, and the brand mark is bright
orange `#ff6b35`. Interactive orange `#b94418` is darker for legible links and
white check marks. Primary actions use charcoal with white text. Text contrasts
against white are 14.89:1 for body text and 5.26:1 for secondary text. Interactive
orange has 5.38:1 contrast on white, 4.87:1 on peach selections and 4.53:1 on
hover surfaces. Green and red retain their success and error meanings.

Segoe UI remains the native font. Larger headings use a lighter weight; body
copy remains compact. Panel radii are 18–20 px, controls 12–15 px, and active
navigation uses a rounded white pill. Tool cards have a shallow lower edge for
depth and round selection indicators. The upload area uses one continuous
rounded outline. No image assets, downloads or new runtime dependencies were
introduced for the redesign.

The shared palette applies across Home, History, menus, dropdowns, page
organization, scan cleanup and spread previews. Top-level dialogs and selected
thumbnail icons receive the same application palette, including under Windows
dark mode. Crop handles, split lines and alignment guides use the orange accent.

The bottom action dock stays visible in compact windows; the workspace scrolls
vertically. Existing conversion choices and processing behavior are retained.
Processing messages remain collapsed by default behind Show details.

Validation: existing UI and cleanup UI tests, rendered review of Home with and
without files, 720 × 540 compact view, History, menus, results and all three page
editors. The portable build is checked separately after compilation.
