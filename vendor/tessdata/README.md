# Additional language data

The portable build includes French and Arabic models from the official
[Tesseract tessdata_fast repository](https://github.com/tesseract-ocr/tessdata_fast),
under the Apache 2.0 license included here. English comes from the configured
Tesseract installation. Binary `.traineddata` files are ignored by Git.

To prepare these models before rebuilding, run `scripts/download_languages.py`.
Normal users receive them inside the portable app and do not need this script.
