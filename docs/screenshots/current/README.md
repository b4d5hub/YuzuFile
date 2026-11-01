# Current application screenshots

Captured from YuzuFile 0.27.0 using `scripts/capture_readme.py`.
The script instantiates the actual Qt widgets with synthetic document content and
an isolated library. Images are unretouched widget captures, not design mockups.

- `tool-wheel.png`: `DesktopDropWheel` after a PDF drag enters the target.
- `tray-menu.png`: `TrayController` menu in an empty session.
- `word-export.png`, `compress-options.png`: `FloatingShell` in resident task mode.
- `workspace.png`: `OrganizeDialog` with three sample pages.
- `split-editor.png`, `cleanup-editor.png`: current visual editors.

The backing `Window` is deliberately never shown: its fallback Home layout is not
the normal resident interface. The wheel appears only during a drag; it is not a
permanent Home window. `capture.json` records source and image hashes so stale
captures can be identified after UI changes.

Regenerate from the repository root with:

```powershell
.venv/Scripts/python.exe scripts/capture_readme.py
```

Inspect every resulting image before committing. The script does not run OCR or
pretend to show successful conversions. Superseded captures are kept in Git
history rather than alongside the current images.
