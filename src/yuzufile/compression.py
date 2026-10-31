"""PDF compression presets, independent of OCR and recognition languages."""
from pathlib import Path
import shutil
import hashlib

import pymupdf

from yuzufile.engines import ConversionError
from yuzufile.performance import Performance
from yuzufile.resources import page_indices, trim_cache


LEVELS = {
    "lossless": ("Lossless", "Keep image quality. Savings depend on the PDF.", None),
    "balanced": ("Balanced", "150 dpi images, good for everyday reading. Some image quality is lost.", (180, 150, 80)),
    "maximum": ("Maximum", "96 dpi images, smaller files with visibly lower image quality.", (120, 96, 55)),
}


def size_label(value: int) -> str:
    return f"{value / 1_000_000:.2f} MB" if value >= 1_000_000 else f"{value / 1000:.1f} KB"


def compression_summary(metadata: dict) -> str:
    percentage = metadata['saved_percent']
    if metadata['output_bytes'] > metadata['input_bytes']:
        change = f"{-percentage:.1f}% larger" if percentage <= -0.05 else "<0.1% larger"
    else:
        change = f"{percentage:.1f}% smaller"
    return (f"{size_label(metadata['input_bytes'])} → {size_label(metadata['output_bytes'])}"
            f" · {change}")


def compress_pdf(document, source: Path, target: Path, level: str, notify,
                 performance: Performance | None = None) -> dict:
    if level not in LEVELS:
        raise ConversionError("Choose a valid PDF compression level.")
    title, _, settings = LEVELS[level]
    # Keep fixed-size per-page fingerprints rather than a second copy of all text.
    original_text = [hashlib.sha256(document[index].get_text().encode("utf-8")).digest()
                     for index in page_indices(len(document), performance, notify,
                                               "Checking PDF before compression", 0, 14)]
    notify(f"Compressing PDF · {title}", progress=15)
    if settings:
        threshold, dpi, quality = settings
        # Preserve bitonal scans and color. MuPDF handles shared image references.
        document.rewrite_images(dpi_threshold=threshold, dpi_target=dpi,
                                quality=quality, bitonal=False, set_to_gray=False)
    trim_cache()
    notify("Saving compressed PDF", progress=80)
    document.save(target, garbage=4, deflate=True, deflate_images=True,
                  deflate_fonts=True, use_objstms=1)
    notify("Verifying compressed PDF", progress=92)
    with pymupdf.open(target) as verified:
        if len(verified) != len(original_text):
            raise ConversionError("Compression validation found a page-count mismatch.")
        for index in page_indices(len(original_text), performance, notify,
                                  "Verifying compressed PDF", 92, 99):
            text = original_text[index]
            if hashlib.sha256(verified[index].get_text().encode("utf-8")).digest() != text:
                raise ConversionError(f"Compression validation found changed text on page {index + 1}.")
    before = source.stat().st_size
    warnings = []
    if target.stat().st_size >= before:
        shutil.copyfile(source, target)
        warnings.append("No further size reduction at this level.")
    after = target.stat().st_size
    return {"compression": level, "input_bytes": before, "output_bytes": after,
            "saved_percent": round((before - after) / before * 100, 2), "warnings": warnings}
