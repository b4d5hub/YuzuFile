# OCR and PDF-to-Markdown research for PDFai

Research date: **18 October 2026**. Scope: local Windows desktop software, English/French/Arabic, mixed-language PDFs, searchable PDF output, and faithful Markdown with tables and diagrams.

## Recommendation

**Use PaddleOCR-VL-1.6's complete document parsing pipeline as the first quality-focused prototype, and benchmark LightOnOCR-3-0.8B as its strongest recent challenger. Use RapidOCR 3.10 with PP-OCRv6 as the first lightweight OCR prototype.** These are recommendations for evaluation, not measured winners on PDFai's documents.

For a CPU-oriented Markdown pipeline, evaluate **Docling 2.140 with RapidOCR**, including explicit handling of mixed scripts. Do not combine every framework into the shipped application. Compare these alternatives, then ship the smallest pipeline that meets the quality requirements.

Keep PDF rendering, compression, the interface, queue and history separate from the recognition engine. A change in OCR library does not require changing the simple interface.

The strongest practical candidates differ by purpose:

| Purpose | First candidate | Reason | Main unresolved point |
| --- | --- | --- | --- |
| Lightweight text recognition | RapidOCR 3.10 + PP-OCRv6 | Small models and ONNX Runtime deployment | Arabic needs a separate recognizer; mixed-script merging needs engineering |
| Structured Markdown on ordinary PCs | Docling + RapidOCR | Layout, reading order and table structure in one framework | Speed, package size and mixed Arabic/Latin behavior on our workload |
| Higher-quality multilingual Markdown | PaddleOCR-VL-1.6, complete pipeline | Broad language coverage and element-level parsing | Actual latency and memory on a 4 GB GPU |
| Recent chart/diagram-focused challenger | LightOnOCR-3-0.8B | Transcription, region boxes and chart data in one small VLM | Arabic quality and native Windows runtime compatibility |
| Larger-machine quality comparison | LightOnOCR-3-4B / Chandra OCR 2 | Strong published document benchmarks | Resource requirements and, for Chandra, model licensing |

The rational next step is a small, controlled bake-off, followed by integration of the winner. Replacing Tesseract based only on a leaderboard would repeat the earlier mistake of accepting output without measuring visual fidelity.

## What the app uses today

Verified against the local source and dependency declarations:

- **Tesseract 5**, invoked as a bundled native executable from Python, performs recognition. It is not a Python neural OCR library. Multiple selected languages become Tesseract's combined language argument.
- **PyMuPDF 1.28.2** renders and manipulates PDFs, including the searchable text overlay and compression.
- **PyMuPDF4LLM 1.28.2** produces Markdown. The current implementation explicitly disables its model-based layout mode with `use_layout(False)`.
- Existing GlyphlessFont OCR text is reused. Presence of an OCR layer currently causes recognition to be skipped, even when that layer contains errors.

Sources: local `pyproject.toml`, `src/pdfai/engines.py` and `src/pdfai/languages.py`.

This means the current conversion can preserve an inaccurate OCR transcript. Improving Markdown formatting cannot recover words that were already missed in that transcript. The current configuration is also distinct from the full capabilities of the PyMuPDF4LLM library.

## Hardware and desktop constraints

Read-only inspection of this computer found an **Intel Core i7-1280P**, approximately **15.7 GiB system RAM**, and **NVIDIA GTX 1650 Max-Q with approximately 4 GB VRAM**, plus Intel integrated graphics.

That supports a CPU-first baseline and makes small accelerated models worth testing. It does not establish that an entire VLM parsing pipeline will fit in VRAM or run quickly. Weights, image tokens, decoding cache, layout models and runtime allocations all consume memory.

Published H100/B200 throughput should not be presented as an estimate for this laptop. Batch throughput also differs from the time a person waits for one PDF.

For distribution, package the worker runtime, models, fonts and licenses alongside the EXE, with predictable local model paths. End users should not need Python, a terminal, Docker or WSL. Download size and peak memory remain unmeasured for the proposed configurations.

## Candidate findings

### 1. PaddleOCR: strongest first multilingual quality prototype

The latest GitHub release observed is **PaddleOCR 3.7.0, 11 June 2026**. Its PP-OCRv6 family has tiny, small and medium tiers. The unified recognizer covers English, French and other Latin languages, but **does not include Arabic**. The project reports recognition and CPU improvements; those are task- and backend-specific vendor results. [Release notes](https://github.com/PaddlePaddle/PaddleOCR/releases), [PP-OCRv6 team article](https://huggingface.co/blog/PaddlePaddle/pp-ocrv6).

Distinguish three products:

- **PP-OCRv6:** text detection and recognition; useful for fast OCR, but not a complete Markdown converter.
- **PP-StructureV3:** a modular layout/table/OCR pipeline with Markdown export. Its documented ONNX Runtime example disables formula recognition because model support is incomplete. [PP-StructureV3 documentation](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/PP-StructureV3.en.md).
- **PaddleOCR-VL-1.6:** a compact document VLM used with layout analysis. The model weights list Apache-2.0 licensing. [Model card](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6).

The VL series documents 109-language coverage; its published language table includes Arabic and French. The full pipeline locates elements, recognizes crops and assembles them in reading order. Running only the VLM is explicitly not equivalent. Official documentation supports CPU paths and a llama.cpp service, while noting that vLLM, SGLang and FastDeploy do not run natively on Windows. [Pipeline and deployment guide](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PaddleOCR-VL.html), [published language list](https://ernie.baidu.com/blog/publication/PaddleOCR-VL_Technical_Report.pdf).

**Assessment:** first quality prototype for the complete multilingual requirement. Test the Windows-compatible runtime and complete pipeline, rather than expecting the raw model to reproduce published results. Treat published OmniDocBench scores as evidence to investigate, not PDFai's accuracy guarantee.

### 2. RapidOCR: best lightweight OCR candidate to test first

**RapidOCR 3.10.0, released 8 October 2026**, adds centralized language/model routing, license metadata and Arabic dependency validation. [Release notes](https://github.com/RapidAI/RapidOCR/releases).

It makes Paddle OCR models usable through runtimes including ONNX Runtime. Arabic handling requires the RTL extra, which installs `python-bidi`; the documented model registry contains separate script-specific recognizers. It does not itself solve document headings, reading order or diagram preservation. [Installation guide](https://rapidai.github.io/RapidOCRDocs/main/en/install_usage/rapidocr/install/), [model registry](https://github.com/RapidAI/RapidOCR/blob/main/python/rapidocr/default_models.yaml).

**Assessment:** strongest first candidate for a small CPU OCR worker. Benchmark PP-OCRv6 small and medium for English/French and the available Arabic-specific model separately. A shared detector plus recognizer routing/merging is a proposed PDFai design, not a documented automatic solution for every three-language page.

### 3. Docling: strongest framework candidate for structured CPU output

**Docling 2.140.0 was released 16 October 2026.** Recent releases include page confidence reporting, progress callbacks and reading-order/OCR fixes. [Release notes](https://github.com/docling-project/docling/releases).

Docling supports local processing, Windows and Markdown/structured JSON export. Its code is MIT; models have their own licenses. [Project documentation](https://github.com/docling-project/docling).

Its Heron layout detector and TableFormer table models address structure separately from OCR. Heron supports ONNX Runtime as well as the Transformers path; TableFormer has its own runtime requirements. Thus, “Docling + ONNX OCR” does not automatically mean an entirely ONNX-only installation. [Model catalog](https://github.com/docling-project/docling/blob/main/docs/usage/model_catalog.md), [Heron model](https://huggingface.co/docling-project/docling-layout-heron), [table/model licenses](https://huggingface.co/docling-project/docling-models).

**Critical limitation:** Docling's current RapidOCR integration accepts one selected recognizer per conversion; extra language entries are dropped with a warning. Its routing uses PP-OCRv6 for English/French and older script-specific models for Arabic. We cannot connect the UI's three checkboxes directly to that adapter and call mixed-language support finished. [OCR language contract](https://github.com/docling-project/docling/blob/main/docs/concepts/OCR.md).

**Assessment:** first structured CPU baseline, conditional on explicit mixed-script support and acceptable packaged performance.

### 4. LightOnOCR-3: most relevant very recent challenger

Released **8 October 2026**, this family provides 0.8B, 1B and 4B variants. It adds grounded regions and chart extraction. The authors report strong results on both document parsing and a French PDF-to-Markdown benchmark, using an H100 for speed tests. These are author-run comparisons and include output normalization; they do not measure our laptop or establish Arabic performance. [Release article and methodology](https://huggingface.co/blog/lightonai/lightonocr-3).

The **0.8B** model offers transcription and a grounding mode with region labels/boxes, image descriptions and chart values. Weights are Apache-2.0. The 4B variant is the larger quality option. [0.8B model card](https://huggingface.co/lightonai/LightOnOCR-3-0.8B), [4B model card](https://huggingface.co/lightonai/LightOnOCR-3-4B).

**Assessment:** include 0.8B in the first comparison, particularly for the user's slide diagrams. Arabic, mixed scripts, runtime support on this GPU and memory use remain unverified. Keep generated image descriptions separate from verbatim extracted document text.

### 5. Marker 2 / Surya OCR 2: useful comparison, with separate model terms

**Marker 2.0.0, released 20 July 2026**, introduces fast/balanced modes and device-dependent defaults. A CPU mode that disables OCR is unsuitable for evaluating scanned-document recognition. [Release notes](https://github.com/datalab-to/marker/releases).

Marker handles structured Markdown, tables and image extraction. Its current code is Apache-2.0, while model weights have modified OpenRAIL terms and commercial thresholds. Surya also documents multilingual OCR and layout capabilities. [Marker project and model terms](https://github.com/datalab-to/marker), [Surya project](https://github.com/datalab-to/surya).

**Assessment:** worthwhile quality comparator; less attractive as the default until the exact model terms and Windows deployment are checked for the intended distribution. Do not use outdated claims that current Marker code is necessarily GPL.

### 6. MinerU 4: capable alternative with a recent architecture change

The latest release observed is **4.0.12, 11 October 2026**. Version 4 offers flash/basic/standard/advanced tiers and separates native parsing, small-model runtimes and VLM backends. CPU and Windows configurations are documented. Older pipeline/VLM comparisons do not describe every 4.x configuration. [Releases](https://github.com/opendatalab/MinerU/releases), [current architecture and hardware guidance](https://github.com/opendatalab/MinerU).

The current license is Apache-2.0-based **with additional conditions**, including commercial thresholds and online-service attribution. It is not simply unmodified Apache-2.0. Model and dependency terms still need checking. [License text](https://github.com/opendatalab/MinerU/blob/master/LICENSE.md).

**Assessment:** second-round alternative if the first prototypes fail. The large framework surface and recent redesign add integration work for this small utility.

### Other options checked

| Option | Evidence and fit |
| --- | --- |
| **OvisOCR2, 0.8B** | Apache-2.0, page-to-Markdown; author-reported 96.58 on OmniDocBench v1.6. Official inference example uses vLLM. Arabic-specific evidence and deployment on this laptop are unresolved. Good additional comparator. [Model card](https://huggingface.co/ATH-MaaS/OvisOCR2) |
| **Chandra OCR 2** | Structured output and 90+ languages including an Arabic example. Strong candidate on larger hardware; modified model terms differ from the code license. [Project](https://github.com/datalab-to/chandra) |
| **olmOCR 2** | Official local requirements include at least 12 GB GPU RAM and 30 GB disk. Poor default fit for this computer. [Official requirements](https://github.com/allenai/olmocr) |
| **GLM-OCR** | Compact, MIT-licensed model. The advertised eight-language coverage does not establish the Arabic requirement. Do not adopt it as the sole recognizer without Arabic validation. [Model card](https://huggingface.co/zai-org/GLM-OCR) |
| **DeepSeek-OCR 2** | Research-oriented CUDA/FlashAttention setup in the official examples; substantial Windows packaging work relative to the first choices. [Official repository](https://github.com/deepseek-ai/DeepSeek-OCR-2) |
| **jina-ocr-v1** | Released September 14; multilingual document parser, but CC-BY-NC-4.0 is a poor default for unrestricted app distribution. [Official model page](https://jina.ai/models/jina-ocr-v1) |
| **Falcon OCR Arabic** | Announced October 6; strong vendor Arabic benchmark. The announcement provides a playground; I could not verify downloadable Arabic adaptation weights or their license. The downloadable base Falcon OCR is a different checkpoint. Watchlist, not an integration-ready recommendation. [Announcement](https://huggingface.co/blog/tiiuae/falcon-ocr-arabic) |
| **EasyOCR** | CPU/Windows support and Arabic available, but language combinations have restrictions and it returns OCR regions rather than complete Markdown structure. Useful baseline, weaker fit as the complete replacement. [Official repository](https://github.com/JaidedAI/EasyOCR) |
| **OCRmyPDF** | Useful searchable-PDF orchestration; the documented default Windows stack still uses Tesseract, with additional dependencies. It does not by itself provide a new recognizer or solve Markdown layout. [Windows installation](https://ocrmypdf.readthedocs.io/en/latest/installation.html) |
| **docling.rs** | Interesting Rust/ONNX packaging route. Native Windows building is documented; the project makes its own speed/parity claims. Validate those and language behavior before adopting it over Python Docling. [Project](https://github.com/docling-project/docling.rs), [Windows guide](https://github.com/docling-project/docling.rs/blob/master/docs/WINDOWS.md) |
| **Xberg, formerly Kreuzberg** | Rust core with Python bindings and extraction/OCR support. Potential packaging alternative, but a framework change alone does not prove improved recognition. [Current repository](https://github.com/xberg-io/xberg) |

## Cloud comparison, if the product scope later permits it

**Mistral OCR 4.1** is the current documented service, released July 16, 2026. It offers paragraph boxes, structural labels and confidence scores, with listed base pricing of $4 per 1,000 pages at research time. It is a hosted service rather than an offline Python OCR engine. [Current model and pricing](https://docs.mistral.ai/models/ocr-4-1).

The Python SDK can return Markdown, image data and structured blocks. [OCR API documentation](https://docs.mistral.ai/studio/document-processing/basic_ocr).

This is a useful optional quality benchmark if uploads are later authorized. It changes privacy, connectivity and operating costs. No user PDF was uploaded to any OCR service during this research, and no cloud integration is proposed as a hidden default.

## Changes needed regardless of library

These are engineering recommendations based on the app's observed failure modes, not claims that a candidate already implements them correctly:

1. **Separate recognition from export.** Preserve regions, coordinates, script/language, confidence and page references in a common internal representation. Render Markdown from those records.
2. **Handle slides as slides.** Detect reliable slide frames on multi-slide pages and process their crops at sufficient resolution. Preserve original reading order and map crop coordinates back to the physical page. Do not blindly split every page into quadrants.
3. **Reassess existing OCR.** A hidden text layer is not proof of accurate text. Compare it with visual recognition for suspicious pages; avoid masking potentially wrong OCR before re-recognizing them.
4. **Preserve diagrams as whole regions.** Render a diagram crop containing vector and raster content. Exporting every embedded bitmap produces fragments and can lose labels.
5. **Keep extraction faithful.** Preserve source typos and uncertain numbers. Do not silently paraphrase, translate or invent a chart description. Include original figure images even when structured chart values are generated.
6. **Support Arabic logically.** Verify Unicode logical order, French accents, mixed-direction numbers, punctuation and Arabic table columns. Avoid applying display-order bidi transforms twice.
7. **Keep the existing UX.** Only available language choices appear; no saved defaults or model settings page. Routing, retries and resource management belong inside the worker.
8. **Build searchable PDFs independently.** Markdown-generating VLM output is not automatically a correctly positioned invisible PDF text layer. Validate positions, copy/paste and search separately; retain the existing overlay path as a fallback until a new one passes.

## Benchmark before choosing the production engine

Public benchmarks are useful for shortlisting. They are not a universal accuracy percentage. **96 on OmniDocBench cannot be compared directly with 85 on olmOCR-bench**, and neither establishes mixed Arabic/French performance. Dataset versions, tested pipeline, postprocessing and hardware must match. [OmniDocBench dataset and evaluation](https://github.com/opendatalab/OmniDocBench).

Prepare approximately 40–60 representative pages with manually checked references:

- The current chapter PDF, emphasizing diagrams, percentages, tiny labels and multi-slide ordering.
- Clean digital English and French; noisy scans; Arabic; same-page Arabic/French/English.
- Tables with merged cells, RTL columns and numbers; equations; rotated pages; stale OCR layers.
- One long document for cancellation, memory growth and failure recovery.

Run the current app as baseline, then:

1. RapidOCR/PP-OCRv6 plus available Arabic recognition, for character accuracy and OCR speed.
2. Docling/RapidOCR with explicit mixed-script handling, for structured CPU conversion.
3. Full PaddleOCR-VL-1.6 pipeline, for multilingual quality.
4. LightOnOCR-3-0.8B, for compact VLM quality and diagram/chart behavior.

Measure missing/extra text, character/word errors per language, reading-order errors, exact critical labels/numbers, table cell fidelity, complete figure preservation, and searchable-PDF behavior. Record cold/warm duration, slowest-page time, peak RAM/VRAM, model/runtime download size and packaged EXE behavior. Test one worker before increasing concurrency.

Use a held-out set after tuning. Require material improvement over the baseline, no silent page failures and acceptable latency on the actual machine. If a small model cannot recover a difficult diagram reliably, retain the full diagram image and a readable warning instead of claiming complete transcription.

## Decision status

**Research completed; production engine selection remains conditional on the local benchmark.** The recommendation is specific enough to begin prototypes, but the new candidates have not been installed or executed here. No new speed or accuracy measurements are claimed. The app, dependencies and packaged EXE were not changed during this research.
