import hashlib
import json
import sqlite3
import time

import pymupdf
import pytest

from yuzufile.compression import compress_pdf
from yuzufile.storage import Store
from yuzufile.supervisor import Supervisor


@pytest.fixture
def image_pdf(tmp_path):
    from PIL import Image
    import io
    image = Image.effect_noise((1600, 2000), 40).convert("RGB")
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    path = tmp_path / "shared images.pdf"
    with pymupdf.open() as doc:
        image_xref = 0
        for index in range(2):
            page = doc.new_page(width=400, height=500)
            image_xref = page.insert_image(page.rect, stream=stream.getvalue(), xref=image_xref)
            page.insert_text((30, 40), f"Searchable page {index + 1}")
            page.insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(20, 20, 100, 50),
                              "uri": "https://example.com"})
            page.add_text_annot((60, 70), "Preserve this comment")
        doc.set_toc([[1, "First page", 1], [1, "Second page", 2]])
        doc.save(path)
    return path


@pytest.mark.parametrize("level", ["lossless", "balanced", "maximum"])
def test_compression_preserves_content_and_original(image_pdf, tmp_path, level):
    before = hashlib.sha256(image_pdf.read_bytes()).digest()
    target = tmp_path / f"{level}.pdf"
    with pymupdf.open(image_pdf) as source:
        metadata = compress_pdf(source, image_pdf, target, level, lambda *a, **kw: None)
    assert metadata["output_bytes"] <= metadata["input_bytes"]
    assert metadata["compression"] == level
    with pymupdf.open(image_pdf) as source, pymupdf.open(target) as result:
        assert len(result) == len(source)
        assert result.get_toc() == source.get_toc()
        for a, b in zip(source, result):
            assert a.get_text() == b.get_text()
            assert a.get_links()[0]["uri"] == b.get_links()[0]["uri"]
            assert list(b.annots())[0].info["content"] == "Preserve this comment"
            if level == "lossless":
                assert a.get_pixmap().samples == b.get_pixmap().samples
            else:
                assert len(b.get_pixmap().samples) > 0
    assert hashlib.sha256(image_pdf.read_bytes()).digest() == before


def test_compression_worker_does_not_require_ocr(store, scanned_pdf):
    job_id = store.create(scanned_pdf, "compress", [], "maximum")
    supervisor = Supervisor(store)
    deadline = time.monotonic() + 60
    try:
        while store.get(job_id)["state"] in {"queued", "running"}:
            supervisor.tick()
            assert time.monotonic() < deadline
            time.sleep(0.05)
    finally:
        supervisor.shutdown()
    job = store.get(job_id)
    assert job["state"] == "succeeded", job["error"]
    metadata = json.loads(job["metadata"])
    assert metadata["compression"] == "maximum"
    assert metadata["output_bytes"] < metadata["input_bytes"]
    assert store.artifacts(job_id)[0]["kind"] == "pdf"
    assert not (store.job_dir(job_id) / "staging").exists()


def test_already_optimized_output_never_grows(digital_pdf, tmp_path, monkeypatch):
    target = tmp_path / "optimized.pdf"
    with pymupdf.open(digital_pdf) as source:
        source.save(target, garbage=4, deflate=True, use_objstms=1)
    output = tmp_path / "again.pdf"
    real_save = pymupdf.Document.save

    def save_with_overhead(document, filename, **options):
        real_save(document, filename, **options)
        # Valid PDF comments simulate an optimization that produced a larger file.
        with open(filename, "ab") as stream:
            stream.write(b"\n% overhead" * 1000)

    monkeypatch.setattr(pymupdf.Document, "save", save_with_overhead)
    with pymupdf.open(target) as source:
        metadata = compress_pdf(source, target, output, "lossless", lambda *a, **kw: None)
    assert metadata["saved_percent"] == 0
    assert metadata["warnings"]
    assert output.read_bytes() == target.read_bytes()


def test_migrates_existing_history(tmp_path, digital_pdf):
    home = tmp_path / "old-library"
    home.mkdir()
    with sqlite3.connect(home / "history.sqlite3") as db:
        db.execute("""CREATE TABLE jobs(id TEXT PRIMARY KEY, source TEXT NOT NULL,
            mode TEXT NOT NULL, languages TEXT NOT NULL, state TEXT NOT NULL,
            stage TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL,
            error TEXT NOT NULL DEFAULT '', metadata TEXT NOT NULL DEFAULT '{}')""")
        db.execute("INSERT INTO jobs VALUES('old',?,'pdf','[]','succeeded','Completed','2026-01-01','2026-01-01','','{}')",
                   (str(digital_pdf),))
    store = Store(home)
    try:
        assert store.get("old")["state"] == "succeeded"
        assert store.get("old")["compression"] == "balanced"
        assert store.get("old")["output_directory"] == ""
        assert store.get('old')['page_plan']=='{}'
        assert store.get(store.create(digital_pdf, "compress", [], "lossless"))["compression"] == "lossless"
    finally:
        store.close()
