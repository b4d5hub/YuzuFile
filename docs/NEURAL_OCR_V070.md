# Neural OCR integration â€” 2026-10-20

This is an integration build, not a claim of universally best extraction.

## Actual components

* RapidOCR 3.10.0: PP-OCRv6 small detector, medium Latin recognizer (English/French), Arabic PP-OCRv5 mobile recognizer. ONNX Runtime 1.31 CPU inference, sequential model copies. Text coordinates create an invisible searchable layer without changing page graphics.
* LightOnOCR-3-0.8B: grounded visual Markdown, using the model author's Q4_K_M GGUF conversion and F16 vision projector. This is a resource-conscious quantized variant, not the larger 4B model or a reproduction of published full-precision benchmarks.
* PaddleOCR-VL-1.6 official GGUF: verifies missing text, table regions and labels inside figures/charts. It runs after LightOn exits. It is conditional, not three complete conversions of every page.
* PP-DocLayoutV3 via RapidLayout 1.2.1: table coordinates. Basic ONNX optimization avoids expensive graph rewrites. Grounded visual blocks provide a fallback when layout fails.
* llama.cpp b11669 Windows CPU runtime: isolated, authenticated loopback server, one model at a time. No hosted inference and no user PDF uploads.
* PyMuPDF / PyMuPDF4LLM 1.28.2: native PDF text, rendering, compression, PDF writing and direct Markdown for digital PDFs. Tesseract remains a reported fallback if neural OCR cannot run.

## Processing and recovery

Markdown proceeds in batches of 1/2/4 physical pages according to Low/Balanced/High. Searchable-PDF OCR keeps one model copy and processes one page at a time with 1/2/4 internal threads. OCR and layout helper processes exit before visual models load, releasing their native heaps. CPU, committed-memory and thread ceilings apply to the entire worker tree. Higher presets change resources, not model quality. All levels can be slow on CPU for complex documents.

Four-up slide frames are detected from matching non-overlapping drawn rectangles; their source drawing order is retained. Other pages use the whole page. Rendered regions have a maximum edge of 2048 pixels. Uniform empty margins are trimmed with a conservative threshold that retains faint footers. Targeted figures/tables are rerendered from the PDF at up to 576 dpi, bounded to 2048 pixels, rather than enlarged from low-resolution screenshots. Labels inside these targets do not also trigger a redundant whole-page verification pass. Large/dense pages can still lose fine print and need future adaptive subdivision.

Grounded blocks provide structure. RapidOCR lines missing from structured text trigger secondary recognition. Better text coverage can replace a deficient transcription; remaining high-confidence lines are retained with a review warning. Scores from unrelated engines are not averaged. This is conservative text recovery, not proof that one model's spelling is correct. Secondary table output can overlap primary text and is explicitly labeled when retained separately.

Accurate native text with tiny logos or photos confirmed to contain no OCR text stays on the native extraction path; these assets do not require visual-model inference.

Complete region images accompany Markdown so vector labels, diagrams and uncertain text remain inspectable. Generated image descriptions are omitted from transcription. Model errors or insufficient memory produce warnings and retain other available OCR results. The manifest records engines actually loaded; loading alone does not establish successful inference on every region.

## Validation

* Actual RapidOCR recognition passed on one image containing English, accented French and Arabic. Exported searchable PDF text preserves logical Arabic order, and a raster comparison confirms unchanged page graphics under the Low resource budget. The helper protocol also has an explicit Windows cp1252 regression test.
* A real combined searchable-PDF/Markdown conversion used RapidOCR, PP-DocLayoutV3 and LightOn successfully with no fallback warnings, in 22.24 seconds including startup. Trimming blank margins resolved an observed 90-second timeout on this synthetic sample.
* Three-page OCR/Markdown conversions completed under Low/Balanced/High resource presets, in 55.35 / 35.45 / 27.00 seconds respectively during the regression run. These small synthetic measurements are not general speed guarantees.
* All three OCR engines, plus PP-DocLayoutV3, ran successfully through the actual worker/supervisor pipeline on two local chapter slides. The output retained all seven attack-chain labels and both pie-chart percentages, including previously missing information. The first complete diagnostic run took 259.77 seconds for those two difficult slides. A subsequent run with selective figure verification completed in 210.61 seconds, with all four components loaded, zero warnings, all expected labels/values present, and no duplicate recovery lines. These are measured CPU timings on this laptop, not a general benchmark.
* All 57 slides in the 15-page four-up chapter handout are detected as individual source regions (four per page except the last). This is region detection, not a completed conversion/quality review of all 57 slides.
* Earlier tests under severe system-memory exhaustion exercised explicit fallbacks. Those runs do not establish neural extraction quality; later successful inference is recorded above.
* Final sequential suite: **89 passed in 256.08 seconds**. The rebuilt executable passed strict offline neural OCR/Markdown checks with zero fallback warnings, mixed-language searchable-PDF verification, all three compression levels, and a complete frozen GUI conversion. See `VALIDATION_V070.md`. A clean Windows VM and a representative multilingual accuracy corpus remain outside this local validation.

CPU inference of complex documents can be slow. The app reports progress and supports cancellation throughout model processing. It retains explicit warnings when recognition is uncertain. There is no claim of universally best accuracy or lossless conversion of arbitrary layouts.

## Reproducibility

`vendor/neural/models.json` records exact files, SHA-256 digests, sizes and pinned GGUF repository revisions. `scripts/download_neural_models.py` downloads resumable ranges and verifies complete hashes. Runtime archive SHA-256 is pinned too. `vendor/neural/licenses` contains upstream license texts; native runtime also includes its OpenMP notice. Build scripts include models and native runtime in the portable app, excluding temporary download caches.

Sources: [RapidOCR 3.10](https://pypi.org/project/rapidocr/3.10.0/), [LightOnOCR-3](https://huggingface.co/lightonai/LightOnOCR-3-0.8B), [author's GGUF](https://huggingface.co/staghado/LightOnOCR-3-0.8B-GGUF), [PaddleOCR-VL-1.6 GGUF](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6-GGUF), [RapidLayout](https://github.com/RapidAI/RapidLayout), [llama.cpp build](https://github.com/ggml-org/llama.cpp/releases/tag/b11669).
