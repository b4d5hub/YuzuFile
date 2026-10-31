# YuzuFile engineering plan

Date: 2026-10-17. Status: proposed; engine selection requires a working prototype.

Implementation started: a runnable Python/PySide6 prototype now covers conversion, history, installed-only multilingual selection, cancellation, and safe file actions. See [implementation status](IMPLEMENTATION_STATUS.md) for verified behavior and outstanding release gates. The sections below retain the original roadmap; the prototype intentionally uses only Convert and History tabs, a fixed managed library selected through `--home`, and no preferences screen.

## 1. Product definition

A small, offline desktop app that turns PDFs into searchable PDFs and Markdown, then makes the results easy to find and manage.

Working assumptions:
- Windows x64 first; macOS/Linux later if needed.
- Local processing, no account, cloud upload, subscription, or GPU requirement.
- Multilingual OCR in the MVP: users select one or more installed languages per conversion, including mixed languages within a page or PDF. Validate target-language combinations in the prototype.
- Inputs stay untouched. Generated files live in an app-managed library.
- OCR means creating a PDF with searchable/selectable text. Markdown is a separate output, with OCR applied when needed.

“Any PDF” is an aspiration, not a reliable acceptance criterion. Support ordinary digital, scanned, and mixed PDFs. Explain failures for corrupt files, unsupported encryption, missing passwords, exhausted resources, and unsupported content. Handwriting, equations, complex tables, and unusual reading order are best effort.

## 2. MVP scope and user flow

1. Add PDFs using a picker or drag and drop.
2. Choose searchable PDF, Markdown, or both.
3. Select one or more available OCR languages for this conversion and choose the destination library. Do not save language defaults or reuse selections across conversions.
4. Start conversion and see queued/running/completed/failed status, current stage, and available progress.
5. Open a result, reveal its folder, retry a failed job, or cancel a queued/running job.
6. Browse history after restarting the app; search by filename and filter by status.
7. Remove a history entry or delete its generated files using distinct actions.

For Markdown-only jobs, extract existing text directly where usable; OCR pages that need recognition. For both outputs, reuse the OCR result where the chosen engines permit it.

Keep language selection simple: populate a multi-select list from language packs available to the configured OCR engine. Omit unavailable languages entirely; no missing-pack badges, disabled language entries, or language-pack management screen. If no usable languages are installed, show one actionable setup error. Validate availability again when starting a job in case the installation changed. Store selected languages in job history only to describe that conversion, never as defaults for future conversions.

Keep three simple views: Convert, History, Settings. History rows show source name, output types, date, status, and actions. A details panel shows output paths, language, engine version, warnings, and a readable failure reason. Do not show invented percentage progress when an engine only reports stages.

Out of MVP: document editing, cloud AI, watched folders, automatic updates, full PDF preview/editor, advanced table reconstruction, collaboration, and multi-machine sync.

## 3. Technology decision

**Recommend Python + PySide6 Widgets + SQLite.** Keep conversion engines behind adapters and run conversion work in child processes.

| Option | Advantages | Costs | Decision |
| --- | --- | --- | --- |
| Python + PySide6 | Direct access to document tooling; one application language; mature desktop controls | Native dependency packaging; Qt distribution requirements | Preferred |
| Rust + Tauri + Python worker | Web-based UI; Rust host integration | Rust, frontend, Python, IPC, and sidecar packaging to maintain | Use only if web UI becomes a requirement |
| Rust-only | Single-language host and stronger compile-time guarantees | Still requires OCR/PDF engines; more integration work for Markdown | Not justified for MVP |

Python coordinates work; native engines do most expensive processing. A Rust rewrite should require measured evidence of a bottleneck.

Candidate conversion engines:
- Searchable PDF: evaluate OCRmyPDF with Tesseract first. Native Windows installation is documented, but a development install does not prove redistributable packaging.
- Markdown: evaluate PyMuPDF4LLM first for extraction and layout handling. Its AGPL/commercial licensing is a distribution decision to resolve before adoption.
- If licensing or measured quality rules out that stack, evaluate Docling for Markdown. Measure CPU memory use, model downloads, first-run setup, and packaged size before accepting it.
- PySide6 has community/commercial licensing options; record actual component obligations with all bundled native dependencies and language/model data before release.

Do not commit to a final engine or exact dependency versions until the packaging and quality spike passes. Pin tested versions afterward. The product's intended open-source/proprietary distribution remains an open decision.

## 4. Architecture

```text
PySide6 views
    -> application services (enqueue, cancel, retry, open, delete)
        -> SQLite repository + managed artifact storage
        -> job supervisor
            -> isolated worker process
                -> OCR adapter / Markdown adapter
```

No HTTP server is needed. Use a small versioned JSON message protocol over process pipes for job commands and progress events. Pass arguments without shell interpolation. Keep the UI responsive and limit initial processing to one active document; engines may have their own bounded parallelism.

Suggested source layout:

```text
src/yuzufile/
  ui/                 # windows, widgets, view models
  application/        # use cases and job supervisor
  domain/             # job states, settings, errors
  engines/            # adapter interfaces and implementations
  infrastructure/     # SQLite, files, OS integration
  worker.py           # child process entry point
tests/
  unit/
  integration/
  fixtures/           # small redistributable test PDFs
```

Build a command-line vertical slice before the GUI so engine behavior can be verified independently. Avoid an extensible plugin framework; two narrow adapter interfaces are sufficient.

## 5. Processing and recovery

Job states: queued -> running -> succeeded / failed / cancelled. On startup, mark abandoned running jobs interrupted and offer retry. Retry creates a new attempt; never silently resumes partially written PDFs.

Pipeline:
1. Validate readable input and PDF format; inspect page count/encryption and check available engines/languages.
2. Create a unique job directory and snapshot the input into temporary job storage for consistent processing; remove the snapshot after completion or failure cleanup.
3. Inspect page text and route native text/scanned/mixed content using the engine's supported modes. Report ambiguous or poor results rather than claiming quality certainty.
4. Produce requested outputs in a staging directory. Preserve useful existing text by default; forcing OCR is an advanced option.
5. Validate that the PDF opens and has the expected page count; verify Markdown and referenced image assets exist. Blank documents may legitimately have no extracted text and should produce a warning.
6. Move validated outputs into the final job directory, then record artifacts and completion in a database transaction.
7. Clean temporary inputs/intermediates. Reconcile orphaned staging/final directories at startup because filesystem and SQLite changes cannot share one atomic transaction.

Cancellation first requests graceful termination, then terminates the worker and its child processes after a timeout. Never publish partial outputs. Apply configurable page/file/time limits; process pages incrementally where supported. Store error codes alongside readable explanations and sanitized technical logs.

Passwords stay in memory and never enter logs/history. Signed PDFs require an explicit warning before generating a derivative because conversion may invalidate signatures. Open output files/directories using OS APIs and treat external Markdown/image references as untrusted when previewing.

## 6. Storage and deletion

Use the platform app-data location for SQLite/settings and a selectable library root for results. Default library location is chosen during implementation using platform conventions.

```text
library/<job-uuid>/
  document.ocr.pdf
  document.md
  assets/
```

Minimal database tables:
- `jobs`: UUID, source path/display name, input hash, requested outputs, options JSON, engine versions, state, stage, timestamps, error code/message, attempt linkage.
- `artifacts`: UUID, job UUID, kind, relative library path, size, creation time, deletion/missing status.
- `schema_migrations`: applied schema versions.

Use UUID directories to avoid filename collisions. Record each job's library root so changing the default does not break old results. File hashes identify repeated input; offer rerun instead of silently reusing potentially stale output.

Deletion behavior:
- **Remove from history:** remove metadata only; explicitly tell the user outputs remain on disk.
- **Delete generated files:** confirm listed outputs, use the recycle bin where available, then update history. Keep failure details if only some files were deleted.
- Source PDFs are never deletion targets.
- Only delete recorded app-owned artifacts after resolving paths and checking containment in that job's library directory, including symlink/junction handling. Never recursively delete a user-selected destination folder.
- Missing/moved files show “missing” with a helpful action; history loading must still work.

## 7. Delivery milestones

### M0 — Prove engines and packaging

Create a CLI prototype and a representative 15–20 document corpus: native text, scans, mixed pages, rotated scans, multi-column layouts, simple/complex tables, blank pages, password-protected input, corrupt input, Unicode paths, and a large document. Add target-language cases before claiming support.

Compare original/output side by side. Record OCR transcription errors on manually checked samples, Markdown reading order/headings/tables, runtime, peak memory, output size, and engine versions. Define numeric quality/performance budgets from these results and the intended user's hardware before M1; do not invent a universal OCR accuracy claim.

Exit: searchable output works, Markdown is useful on the agreed corpus, license direction is recorded, and a packaged prototype runs on a clean Windows VM without Python, WSL, Docker, or developer PATH entries. If this fails, revisit engines before building the GUI.

### M1 — Reliable core

Implement job model, migrations, managed storage, engine adapters, worker supervision, cancellation, startup reconciliation, and CLI conversion. Test failures and recovery before adding UI.

Exit: conversion, retry, cancellation, interruption recovery, and artifact publication work through automated integration checks.

### M2 — Desktop workflow

Implement Convert, History, Settings, drag/drop, progress, open/reveal, retry, and the two deletion actions. Include an available-languages-only multi-select, essential setup errors, and keyboard navigation; no saved language preferences or missing-pack indicators.

Exit: a user can complete the entire requested workflow without a terminal, and history survives restart.

### M3 — Release candidate

Build the Windows installer, dependency/license manifest, versioned migrations, and short user guide. Test installation, upgrade, and uninstall on a clean VM, including paths with spaces and non-ASCII characters. Uninstall must preserve the document library unless explicitly selected for deletion.

Exit: all acceptance criteria pass on the supported Windows environment. Record measured installer size and performance. Decide signing/distribution channel before public release.

## 8. Acceptance and verification

- A scanned test PDF becomes searchable while preserving page count and readable appearance; verify search/copy text in a PDF viewer.
- A digital PDF converts to Markdown without unnecessary OCR; headings, reading order, and simple tables meet corpus expectations.
- Mixed PDFs preserve useful existing text and recognize scanned pages.
- Users can select multiple installed OCR languages for a single job; the corpus includes mixed-language pages. Unavailable languages are absent from the selector, and selections are not saved as defaults.
- “Both” produces two validated outputs with correct asset links.
- The UI stays interactive during a large conversion; cancel stops the process tree and leaves no published partial output.
- Killing/restarting the app yields an interrupted job with a working retry.
- History, settings, and output paths persist across restart; unavailable files do not crash the app.
- Open file/reveal directory work for Unicode names and spaces.
- Deleting generated files never deletes or modifies the source, other jobs, or files outside the managed directory.
- Encrypted/corrupt input, missing language data, disk-full, and worker failure produce actionable errors.
- Conversion runs offline after required components are installed; no document content is logged or transmitted.
- The installer works on a clean supported machine without a development environment.

Use unit tests for job transitions, path containment, deletion ownership, and migrations; integration tests with real small PDFs for conversion, cancellation, and recovery; manual visual review for extraction quality and desktop behavior. Add a packaging smoke test. Avoid brittle pixel snapshots and tests that only repeat implementation details.

## 9. Decisions to confirm before implementation

Defaults above allow the prototype to proceed. Before locking the release architecture, confirm Windows-only versus cross-platform, target OCR languages, intended open-source/proprietary distribution, and a few representative PDFs that define acceptable Markdown quality. These decisions affect engine licensing, bundled size, and scope.

Recommended next action: M0 packaging-and-quality prototype. It should produce concrete sample outputs and a measured decision record before UI implementation.

## References checked

- [OCRmyPDF installation and native Windows guidance](https://ocrmypdf.readthedocs.io/en/latest/installation.html)
- [PyMuPDF4LLM API and OCR options](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/api.html)
- [PyMuPDF licensing FAQ](https://pymupdf.readthedocs.io/en/latest/faq/index.html)
- [Qt for Python licensing](https://doc.qt.io/qtforpython-6/licenses.html)
- [Docling documentation](https://docling-project.github.io/docling/)
