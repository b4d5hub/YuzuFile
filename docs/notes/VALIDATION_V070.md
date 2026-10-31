# YuzuFile 0.7.0 validation — 2026-10-20

The researched engines are integrated and included in the Windows package, not merely installed in the developer environment.

| Check | Result |
|---|---|
| Final sequential pytest suite | 89 passed, 256.08 seconds |
| Packaged neural OCR and Markdown | RapidOCR + PP-DocLayoutV3 + LightOn actually ran; no fallback warnings |
| Offline packaging smoke | Developer Python/Tesseract paths removed; remote proxies disabled; bundled models used |
| Frozen mixed English/French/Arabic OCR | Correct searchable Unicode text; unchanged raster appearance |
| Frozen GUI conversion | Succeeded under Low usage budget; Home/History and result actions verified |
| Lossless, Balanced, Maximum compression | All passed with readable outputs and page counts retained |
| Three-engine chapter sample | RapidOCR, LightOn, Paddle and layout actually ran under the supervisor's High budget |
| Chapter sample content | All seven attack-chain labels and both chart percentages retained; no duplicate recovery lines; zero warnings |
| Handout region detection | Four regions on pages 1–14, one on page 15: 57 source slides |

The complete optimized diagnostic chapter run took 210.61 seconds for two difficult slides on CPU. This is a limited sample, not an accuracy audit of the entire chapter. Ordinary three-page synthetic OCR/Markdown tests took about 55/35/27 seconds under Low/Balanced/High in an earlier regression run. Model quality settings stay fixed across presets; available resources and image complexity affect elapsed time. Complex documents can still take minutes per page/region.

RapidOCR 3.10.0 uses PP-OCRv6 small detection, medium Latin recognition, and Arabic PP-OCRv5. LightOnOCR-3-0.8B uses the author's Q4_K_M GGUF variant. PaddleOCR-VL-1.6 uses its official GGUF and runs selectively for missing text, tables and figure labels. These choices target local Windows CPU use; they do not reproduce larger/full-precision benchmark configurations. Native digital text stays on the faster PyMuPDF4LLM path where appropriate. Tesseract remains an explicitly reported emergency fallback.

Exact model revisions, sizes and SHA-256 hashes are in `_internal/neural/models.json` in the portable package. Upstream licenses and complete app source are included. No user PDFs were sent to a hosted OCR or AI service. User chapter test data is kept outside the distributed source snapshot.

The package is a portable folder. Extract the entire ZIP and double-click YuzuFile.exe; keep YuzuFile-worker.exe and _internal beside it. No Python or command line is required for normal use. Clean-VM testing and a broad multilingual corpus remain future validation work.
