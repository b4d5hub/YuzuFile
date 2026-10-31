"""Developer helper: download the public official CPU OCR language models."""
from pathlib import Path
from urllib.request import urlopen

root = Path(__file__).resolve().parents[1] / "vendor/tessdata"
root.mkdir(parents=True, exist_ok=True)
for name in ("fra.traineddata", "ara.traineddata", "LICENSE"):
    url = "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/" + name
    with urlopen(url, timeout=60) as response:
        (root / name).write_bytes(response.read())
print("French and Arabic recognition data are ready for packaging.")
