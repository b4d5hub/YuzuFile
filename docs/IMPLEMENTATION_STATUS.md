# Implementation status

2026-10-18 — current version: **0.6.1**. See [library resource controls](LIBRARY_RESOURCES_V061.md) for the extension of performance presets to native rendering, heading detection, figure export and compression validation. Previous version notes follow.

2026-10-18 — current version: **0.6.0**. See [performance controls](PERFORMANCE_V060.md) for Low usage / Balanced / High performance, bounded page parts, Windows CPU/memory limits and verification. All 69 source tests and the packaged smoke checks passed. The OCR/Markdown engine upgrade remains a separate benchmarked implementation; this build uses Tesseract/PyMuPDF. Earlier notes below are historical.

2026-10-17 — current version: 0.2.0. See [the reliability report](RELIABILITY_V020.md) for the new page-based OCR pipeline, redesigned UI, 27-test suite, and actual 81-page document benchmark. The notes below describe the earlier v0.1 implementation and packaging work; its OCRmyPDF/PDFium pipeline has been replaced.

## Delivered

- Python/PySide6 desktop UI with Convert and History tabs; no saved language preferences or language-pack indicators.
- Multiple PDF inputs via picker/drop; one document processed at a time in a supervised child process.
- Searchable PDF, Markdown, and combined output.
- Installed-only language discovery and multiple selections per job. Selections clear after submission and are not restored on retry.
- SQLite history with filename/status filters and per-job artifact records.
- Open PDF, open Markdown, open output folder, retry, and cancel actions.
- Separate history removal and generated-file recycling, with source files untouched and containment checks against traversal, links, and junctions.
- Atomic output-directory publication, interrupted-job recovery, temporary snapshot cleanup, and a per-library instance lock.
- Windows Job Objects to stop the entire worker process tree on cancellation or app death; bounded job time and memory.
- CLI, dependency diagnostics, project environment, setup and launch scripts.
- Portable `PDFai.exe` and hidden `PDFai-worker.exe` sharing a bundled Python/Qt runtime, Tesseract, and English recognition data. Normal users double-click the main executable; no Python/PowerShell or separate OCR installation is needed.
- Reproducible PyInstaller spec, developer build script, portable ZIP, included source snapshot/component notices, and packaged smoke checks with developer tools removed from PATH.

## Engine decisions for the prototype

- OCRmyPDF 17.4.2 + Tesseract, standard PDF output, PDFium rasterization, redo mode, optimization disabled. Actual scan and mixed image/native-text conversions passed without Ghostscript.
- PyMuPDF/PyMuPDF4LLM 1.28.2, legacy layout path, OCR performed upstream once, images embedded in Markdown. Explicit document closure avoids retained handles on Windows.
- PySide6 Essentials 6.12.0. Full Qt web/browser components are not required by the project dependency declaration.
- Fixed per-library app data storage and two tabs keep the first UI small. A custom location is selected using `--home`; there is no settings screen.
- Password-protected/signed inputs are rejected with instructions rather than introducing password/signature dialogs in this version.

## Verification

Automated checks exercise actual conversion subprocesses on synthetic digital, scanned, mixed, encrypted, and corrupt PDFs. Storage checks cover restart persistence, interrupted jobs, partial deletion, history-only removal, and a Windows junction pointing outside the managed library. UI checks verify installed-only languages, per-submission resets, and history filtering. Engine tests include Unicode source paths and spaces.

All 20 tests passed on Windows/Python 3.13.7, including a real app-process crash that confirms both worker and grandchild exit. Dependency consistency and Python compilation checks also passed. Offscreen renders of both desktop tabs and the scanned OCR result were visually inspected. The offscreen Qt platform exposes no system fonts in this environment, so preview tooling explicitly registers the installed Segoe UI font. The normal desktop uses Qt's platform font configuration.

Only English recognition data is installed here. Multi-language UI/request handling is tested; recognition quality for French, Arabic, mixed scripts, and RTL output has not been validated. No private documents were used.

The packaging work adds a bundled-runtime preference test; all 21 source tests pass. Packaged-worker checks verify digital Markdown and scanned PDF/Markdown with only Windows system directories on PATH and an intentionally invalid inherited TESSDATA_PREFIX. The app uses its included Tesseract and language data. The GUI smoke check also exercises the frozen app's supervisor and its separate hidden worker. This is environment-isolation testing on the development machine, not a clean Windows VM validation.

The packaged GUI check caught an ICU collision: PyInstaller selected Poppler's `icuuc.dll` from the developer PATH, which has versioned exports incompatible with Qt's use of the native Windows ICU forwarder. The spec excludes that root DLL so Qt loads the Windows component, matching the working source application. Both GUI startup and a supervised OCR conversion were verified after removing the conflicting DLL.

## Remaining release gates

1. Expand to the planned 15–20-document corpus, including selected target languages, blank/rotated/long documents, tables, and multi-column reading order. Agree on quality/performance budgets using representative user documents and hardware.
2. Measure peak memory, speed, and output size across that corpus. Current limits are protective prototype limits, not performance claims.
3. Decide distribution licensing before adopting the AGPL/commercial document engine stack for release; audit all runtime and bundled-data obligations.
4. Verify the portable build on a clean Windows VM with no Python/developer dependencies. A standalone installer, signing, upgrade, and uninstall workflow remain future work; the delivered ZIP runs after extraction.
5. Perform interactive native-desktop usability and file-association checks. Offscreen tests do not prove Explorer launch behavior or every display/DPI configuration.

The original M0 exit gate is still open because broad quality validation and clean-machine validation are incomplete. Core, UI, and portable packaging work make the prototype usable without a terminal.
