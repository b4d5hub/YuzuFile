# History removal and tray menu — 0.27.0

Removed the History page/window, navigation links, wheel/task/progress buttons,
Ctrl+H shortcut, tray action, CLI command, and Remove from History result action.
The application no longer builds or refreshes an invisible history list.

The tray menu is now Process PDFs, optional Resume task, Processing & results,
Enable drag + Shift, and Quit YuzuFile. Duplicate latest-file and latest-folder
shortcuts were removed; file actions remain on current-session results. Icons
use the existing Lucide set. The literal ampersand is escaped for Qt menus.

Internal job storage remains for conversion supervision, publishing, recovery
and safe file recycling. No migration deletes existing records or user files.
Completed jobs from previous launches are not shown. Clear finished removes
cards from the current session. Existing result files remain on disk.

Validation covers tray action availability, modal ownership, cancel/quit,
session results, retry, file actions, drag gestures, page tools and the shaped
shell. The 155 relevant checks pass across the main run and the corrected
organize-result check; the final tray icon/label change also passes its 13
focused tests. A menu preview was inspected at native control scale.
