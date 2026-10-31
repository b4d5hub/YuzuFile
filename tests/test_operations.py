import json
import shutil

import pymupdf

from yuzufile.operations import MODES, mode_for
from yuzufile.worker import convert
from artifact_helpers import artifact_path


def test_all_operation_combinations_have_distinct_compatible_history_modes():
    assert len(MODES) == 72
    for mode, operations in MODES.items():
        assert mode_for(operations) == mode


def test_combined_compression_fallback_keeps_new_ocr_text(scanned_pdf, tmp_path, monkeypatch):
    def recognize(document, scratch, languages, notify, performance=None,**options):
        from yuzufile.ocr_clean import clean_page
        target=options['target_document'];clean_page(document[0],target)
        target[0].insert_text((60, 60), "Retained OCR text")
        return {"ocr_pages": 1, "recognized_pages": 1, "empty_pages": [], "reused_pages": 0}

    def no_savings(document, source, target, level, notify, performance=None):
        # Compression's existing no-savings fallback copies its input. The worker
        # must supply the searchable intermediate rather than the original scan.
        with pymupdf.open(source) as fallback:
            assert "Retained OCR text" in fallback[0].get_text()
        shutil.copyfile(source, target)
        return {"compression": level, "input_bytes": source.stat().st_size,
                "output_bytes": target.stat().st_size, "saved_percent": 0, "warnings": []}

    monkeypatch.setattr("yuzufile.worker.add_searchable_text", recognize)
    monkeypatch.setattr("yuzufile.worker.installed_languages", lambda: ["eng"])
    monkeypatch.setattr("yuzufile.compression.compress_pdf", no_savings)
    root = tmp_path / "job"
    convert({"root": str(root), "source": str(scanned_pdf), "mode": "ocr_compress",
             "languages": ["eng"], "compression": "lossless"})
    result = root / "result"
    with pymupdf.open(artifact_path(root,'pdf')) as doc:
        assert "Retained OCR text" in doc[0].get_text()
    metadata = json.loads((result / "manifest.json").read_text())["metadata"]
    assert metadata["input_bytes"] == scanned_pdf.stat().st_size
    assert metadata['output_bytes']==artifact_path(root,'pdf').stat().st_size
    assert metadata['saved_percent']==round((1-metadata['output_bytes']/metadata['input_bytes'])*100,2)
