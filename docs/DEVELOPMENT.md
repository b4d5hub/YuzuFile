# Development and packaging

Run commands from the repository root in PowerShell. End users should use the
portable app; these instructions are for developers. The recorded lock targets
Windows x64 / Python 3.13, although project metadata permits Python 3.11+.

## Environment

```powershell
.\scripts\setup.ps1
.\run.ps1 doctor
```

`setup.ps1` uses `py -3`, creates `.venv`, installs the lock with `--no-deps`, and
installs the project editable. Ensure `py -3` selects the intended interpreter.
If several versions are installed, create the environment explicitly instead:

```powershell
py -3.13 -m venv .venv
.venv/Scripts/python.exe -m pip install --no-deps -r requirements-windows.lock
.venv/Scripts/python.exe -m pip install --no-deps -e .
```

Do not replace the lock with an unconstrained dependency upgrade: the environment
contains native inference dependencies and deliberately avoids conflicting OpenCV
variants. The lock is a development snapshot, not proof of reproducibility on all
machines. Record dependency changes and rerun affected packaged checks.

## Native tools and models

Install a Windows Tesseract distribution including its executable, DLLs, English
language data, and license documentation. Development discovers Tesseract on PATH
or standard Windows installation paths. The packager can also use
`YUZUFILE_TESSERACT` pointing to `tesseract.exe`; that override is build-specific.
The package spec expects a `tessdata` and `doc` directory beside the executable.

Model acquisition is explicit and requires network access. Read the license files
and acquisition scripts first. The current Indra command is specifically for an
authorized **personal-use** build, not authorization to redistribute a public app.

```powershell
.venv/Scripts/python.exe scripts/download_languages.py
.venv/Scripts/python.exe scripts/download_neural_models.py
.venv/Scripts/python.exe scripts/prepare_indra.py --personal-use
.venv/Scripts/python.exe scripts/prepare_arabic_print.py
.\run.ps1 doctor
```

The language downloader fetches French/Arabic Tesseract data; English comes from
the installed distribution. Neural assets live under `vendor/neural/`, with
manifests/provenance alongside them. Preparation can require large downloads and
disk space. These scripts are not a public model-distribution policy.

## Run with isolated development data

```powershell
.\run.ps1 --home .\tmp\dev-library gui
```

The library lock prevents two processes from using the same store. Keep test jobs
away from personal app data. CLI conversion is also available:

```powershell
.\run.ps1 convert --help
.\run.ps1 --home .\tmp\cli-library convert .\sample.pdf --format ocr --languages eng fra ara
```

Use a real local sample in place of `sample.pdf`. CLI operations are defined in
`src/yuzufile/operations.py`; the current CLI has no History command.

## Repository map

```text
src/yuzufile/                  Application, engines, editors, persistence
tests/                      Regression tests and generated fixtures
scripts/                    Setup, model preparation, verification, builds
packaging/                  PyInstaller spec, entry point, end-user instructions
vendor/                     Third-party assets, model manifests and licenses
docs/                       Current guides and historical implementation notes
requirements-windows.lock   Recorded Windows environment
pyproject.toml              Package metadata and direct dependencies
```

`build/`, `dist/`, `tmp/`, local outputs, and model binaries are generated/local
material. Audit the publishing set; `.gitignore` alone is not a privacy audit.

## Verification

For headless Qt test execution in the current PowerShell session:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
.venv/Scripts/python.exe -m pytest tests/test_storage.py tests/test_output_names.py tests/test_system_tray.py -q
```

Run the full regression suite when validating a release:

```powershell
.venv/Scripts/python.exe -m pytest -q
```

Some checks require native tools/models or Windows. Inspect skips and prerequisites;
a passing subset is not equivalent to the full suite. Remove the offscreen setting
before interactive UI verification:

```powershell
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
```

| Change | Relevant verification |
| --- | --- |
| Tray, shell, dragging | `test_system_tray.py`, `test_desktop_drag.py`, `test_resident_navigation.py`, interactive Explorer drag |
| Storage/publication | `test_storage.py`, `test_source_output.py`, `test_output_names.py` |
| Fresh recognition | `test_worker_fresh_pipeline.py`, `test_fresh_ocr_engines.py`, `test_ocr_clean.py` |
| Arabic/Word | `test_arabic_print.py`, `test_word_arabic.py`, `test_word_fresh_ocr.py`, rendered sample inspection |
| Visual page tools | `test_spreads.py`, `test_organize.py`, `test_cleanup.py`, visual geometry/editor suites |
| Packaging | Frozen-module guard and real packaged smoke run |

Tests cover behavior and preservation. OCR accuracy requires a separate ground-truth
corpus: report character/word error rates by language, table structure errors,
reading order, conversion time, and peak memory. Do not substitute model confidence
for measured accuracy. Use synthetic or redistributable samples only in public tests.

## Build the Windows portable app

Prepare all models and Tesseract first. Review the packaging spec for expected
assets. Then:

```powershell
.venv/Scripts/python.exe scripts/build_windows.py
.venv/Scripts/python.exe scripts/verify_frozen_modules.py
```

The build verifies prepared model hashes, builds desktop/worker executables,
checks guarded modules against source, copies source/notices, creates a ZIP, and
updates the local workspace shortcut. Outputs follow:

```text
dist/YuzuFile-<version>/YuzuFile.exe
dist/YuzuFile-<version>/YuzuFile-worker.exe
dist/YuzuFile-<version>/_internal/
dist/YuzuFile-Windows-<version>.zip
```

This is a portable bundle, not a signed installer. `--package-only` refreshes
packaging without rebuilding executables; it is not a substitute for rebuilding
changed runtime code. The source guard checks selected modules, not every possible
runtime dependency or model behavior.

Before release, run the packaged app without a developer PATH and with an isolated
library. Verify a real conversion, cancellation, output placement, multilingual
content, tray lifecycle, and visual editors. `scripts/smoke_windows.py` and
`src/yuzufile/packaging_smoke.py` contain existing smoke tooling; inspect their options
before use. No CI workflow or universal clean-machine certification is claimed.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| No window on launch | Tray/hidden-icons menu; the app is resident by design |
| Library already in use | Quit the other instance or use a separate `--home` |
| Language missing | `doctor`, model manifests, Tesseract installed language data |
| Build fails on missing assets | Preparation scripts, Tesseract directories, packaging spec |
| Old behavior after rebuilding | Quit old tray process; open the new versioned executable |
| Wrong or missing OCR | Selected languages, source resolution, warnings, language-specific fixture |
| Lost-looking results after restart | History was removed; inspect the source/selected output folder |

Do not fix missing outputs by deleting the personal library. Preserve a sanitized
failure report and investigate the manifest and job state first.
