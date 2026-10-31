# PDFai 0.11.0 — personal-use Indra integration

Indra OCR Python package 1.1.2 uses the official v1.1.0 model set, pinned at
`bd02167fdf2005a19962cc15188f8496a2c87d3b`. Model sizes and SHA-256 hashes
are recorded in `vendor/neural/indra/ready.json`; the build verifies them.

This build is for the user's explicitly confirmed personal use. The actual model
license is `vendor/neural/indra/LICENSE`. It includes restrictions on competing
products, redistribution obligations, attribution and output share-alike terms.
The build and conversion outputs include the license and notices. Public or
commercial distribution has not been cleared. Do not treat Apache licensing of
the Python source as permission to distribute the weights without their terms.

## Behavior

- Image pages use Indra CPU recognition first. RapidOCR, then Tesseract remain
  emergency OCR fallbacks; fallback pages are reported in conversion metadata.
- Searchable-PDF overlays preserve the source appearance and map Indra's upright
  coordinates back onto sideways/upside-down source pages.
- Arabic fallback-font Unicode maps are normalized from presentation forms to
  ordinary Arabic characters so standard search/copy works after export.
- Ordinary visual Markdown uses Indra layout and reading order. Tables or long
  lines below 0.7 confidence use the existing detailed LightOn/Paddle pipeline
  when its models are available. This is a conservative quality safeguard after
  a chapter sample exposed corrupted diagram labels and malformed table columns.
- Existing PDF text is preserved. Image-only page results are reused for Markdown;
  masked hybrid-page recognition is not reused as complete-page Markdown.
- Figure placeholders become local image crops. Headers and footers are kept.
- English/French/Arabic selection and mixed-script recognition remain available.
  Indra performs its own per-line script routing; language selection does not
  restrict its recognition vocabulary.
- Optional math models are not bundled or enabled in this release. Difficult
  mathematical pages remain a limitation; tables route to detailed processing.

## Resource and offline policy

ONNX CPU execution is explicit. No CUDA, PyTorch, Docker or API key is needed.
Every call supplies a complete local model directory, so it never asks Indra to
download weights. The isolated helper loads one reader, handles one page, and
exits, releasing native allocations. Source page results are disk-backed; rasters
are limited to 8 megapixels and removed after each part. Model startup overhead
is included in end-to-end tests and can dominate short jobs.

Low/Balanced/High keep their existing process-tree CPU and memory ceilings and
provide 1/2/4 threads to Indra. Resource selection does not change model quality.
Detailed fallback can still take minutes on complicated pages.

## Development

Install pinned project dependencies. For authorized personal use, run
`python scripts/prepare_indra.py --personal-use`, then the normal build script.
This is a developer operation; normal users double-click the packaged EXE.

Official references:
- https://github.com/datalab-to/indra
- https://www.datalab.to/blog/indra-ocr-1-1
- https://huggingface.co/datalab-to/indra-ocr/tree/v1.1.0
