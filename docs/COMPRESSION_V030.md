# PDF compression validation (v0.3.0)

36 source tests passed, including OCR regression, compression presets, no-OCR compression jobs, source preservation, history migration and UI behavior.

| Level | Input MB | Output MB | Saved | Seconds |
|---|---:|---:|---:|---:|
| lossless | 92.17 | 92.12 | 0.05% | 1.12 |
| balanced | 92.17 | 31.25 | 66.09% | 59.68 |
| maximum | 92.17 | 8.08 | 91.24% | 17.49 |

Measured on the same 81-page scanned PDF used for the v0.2 OCR check. Individual timings vary by machine and system load; this is not a controlled performance benchmark. The original PDF was read only. All outputs retain 81 pages. Sampled lossless pages 1, 41 and 81 render pixel-identically at 72 dpi; balanced and maximum sample pages render successfully. A synthetic two-page PDF with a shared image also retains searchable text, bookmarks, URI links and comments at each level. Lossless preserves synthetic page pixels.

Balanced and Maximum are lossy, preserve color, and skip bitonal-image rewriting. Savings depend on source images and encoding. Files that do not shrink are returned as an unchanged copy with a note. Signed-field PDFs and locked PDFs follow the existing rejection rules. Outputs are recorded in the same managed library and use the same cancellation, retry and deletion controls.

Packaged v0.3.0 checks passed with Python/Tesseract developer paths removed: GUI startup and supervised OCR conversion, bundled language discovery, digital Markdown, scanned PDF plus Markdown, and all three compression levels.
