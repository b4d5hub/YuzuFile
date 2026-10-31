import time

import psutil
import pymupdf
import pytest

from yuzufile.languages import installed_languages
from yuzufile.supervisor import Supervisor
from artifact_helpers import artifact_path,artifact_paths


def assert_visually_equivalent(before,after):
    # Fresh recognition deliberately rasterizes the visible source. Resampling
    # must preserve its appearance, but it need not produce identical RGB bytes.
    from PIL import Image,ImageChops,ImageStat
    assert (before.width,before.height)==(after.width,after.height)
    images=[Image.frombytes('RGB',(pix.width,pix.height),pix.samples) for pix in (before,after)]
    assert max(ImageStat.Stat(ImageChops.difference(*images)).mean)<3


def run_job(store, source, mode, languages, timeout=180, performance="balanced", output_directory=None):
    job = store.create(source, mode, languages, performance=performance, output_directory=output_directory)
    supervisor = Supervisor(store)
    deadline = time.monotonic() + timeout
    try:
        while store.get(job)["state"] in {"queued", "running"}:
            supervisor.tick()
            if time.monotonic() > deadline:
                pytest.fail("Worker timed out")
            time.sleep(0.05)
        return store.get(job)
    finally:
        supervisor.shutdown()


def test_combined_conversion_saves_in_chosen_output_folder(store, digital_pdf, tmp_path):
    destination = tmp_path / 'Chosen outputs français'
    destination.mkdir()
    original = digital_pdf.read_bytes()
    job = run_job(store, digital_pdf, 'all', ['eng'], output_directory=destination)
    assert job['state'] == 'succeeded', job['error']
    root = store.job_dir(job['id'])
    assert root.parent == destination
    result = root / 'result'
    with pymupdf.open(artifact_path(root,'pdf')) as document:
        assert 'Hello world' in document[0].get_text()
    assert 'Hello world' in artifact_path(root,'markdown').read_text(encoding='utf-8')
    assert not (root / 'staging').exists()
    assert not (store.library / job['id']).exists()
    assert digital_pdf.read_bytes() == original


@pytest.mark.parametrize("performance", ["low", "balanced", "high"])
def test_performance_presets_preserve_ocr_and_markdown(store, scanned_pdf, tmp_path, performance):
    import json
    source = tmp_path / (performance + "-multipage.pdf")
    with pymupdf.open(scanned_pdf) as scan, pymupdf.open() as doc:
        for _ in range(3):
            doc.insert_pdf(scan)
        doc.save(source)
        before = [page.get_pixmap(dpi=60) for page in doc]
    original = source.read_bytes()
    job = run_job(store, source, "both", ["eng"], performance=performance)
    assert job["state"] == "succeeded", job["error"]
    metadata = json.loads(job["metadata"])
    assert metadata["performance"] == performance
    assert metadata["ocr_pages"] == 3
    root = store.job_dir(job["id"]) / "result"
    with pymupdf.open(artifact_path(root,'pdf')) as doc:
        assert all("Hello world" in page.get_text() for page in doc)
        for original_page,page in zip(before,doc):
            assert_visually_equivalent(original_page,page.get_pixmap(dpi=60))
    assert artifact_path(root,'markdown').read_text(encoding="utf-8").count("Hello world") == 3
    assert source.read_bytes() == original
    assert not (root.parent / "staging").exists()


@pytest.mark.parametrize("mode", ["ocr_compress", "markdown_compress", "all"])
def test_combined_compression_preserves_searchable_text(store, scanned_pdf, mode):
    original = scanned_pdf.read_bytes()
    job = run_job(store, scanned_pdf, mode, ["eng"])
    assert job["state"] == "succeeded", job["error"]
    result = store.job_dir(job["id"]) / "result"
    with pymupdf.open(artifact_path(result,'pdf')) as doc:
        assert len(doc) == 1
        assert "Hello world" in doc[0].get_text()
    assert len(list(result.glob('*.pdf')))==1
    if mode in {"markdown_compress", "all"}:
        assert "Hello world" in artifact_path(result,'markdown').read_text(encoding="utf-8")
    else:
        assert not artifact_paths(result,'markdown') and not list(result.glob('*.md'))
    assert scanned_pdf.read_bytes() == original


def test_digital_markdown_requires_fresh_ocr_language(store, digital_pdf):
    job = run_job(store, digital_pdf, "markdown", [])
    assert job["state"] == "failed" and 'language' in job['error']
    assert not (store.job_dir(job['id'])/'result').exists()
    assert not (store.job_dir(job["id"]) / "staging").exists()


@pytest.mark.skipif("eng" not in installed_languages(), reason="English Tesseract data is required")
def test_scanned_pdf_produces_searchable_pdf_and_markdown(store, scanned_pdf):
    original = scanned_pdf.read_bytes()
    job = run_job(store, scanned_pdf, "both", ["eng"])
    assert job["state"] == "succeeded", job["error"]
    root = store.job_dir(job["id"]) / "result"
    with pymupdf.open(artifact_path(root,'pdf')) as doc:
        assert doc.page_count == 1
        assert "Hello world" in doc[0].get_text()
    assert "Hello world" in artifact_path(root,'markdown').read_text(encoding="utf-8")
    assert scanned_pdf.read_bytes() == original


@pytest.mark.skipif("eng" not in installed_languages(), reason="English Tesseract data is required")
def test_mixed_pdf_freshly_recognizes_visible_text_and_image(store, scanned_pdf, tmp_path):
    mixed = tmp_path / "mixed.pdf"
    with pymupdf.open(scanned_pdf) as doc:
        doc[0].insert_text((72, 220), "Native caption survives", fontsize=15)
        doc.save(mixed)
    job = run_job(store, mixed, "pdf", ["eng"])
    assert job["state"] == "succeeded", job["error"]
    with pymupdf.open(artifact_path(store.job_dir(job["id"]),'pdf')) as doc:
        text = doc[0].get_text()
        assert "Native caption survives" in text
        assert text.count("Native caption survives") == 1
        assert "Hello world" in text


def test_rotated_scan_keeps_visual_appearance(store, scanned_pdf, tmp_path):
    rotated = tmp_path / "rotated.pdf"
    with pymupdf.open(scanned_pdf) as doc:
        doc[0].set_rotation(90)
        doc.save(rotated)
        before = doc[0].get_pixmap(dpi=72)
    job = run_job(store, rotated, "pdf", ["eng"])
    assert job["state"] == "succeeded", job["error"]
    with pymupdf.open(artifact_path(store.job_dir(job["id"]),'pdf')) as doc:
        assert_visually_equivalent(before,doc[0].get_pixmap(dpi=72))


def test_already_searchable_scan_is_cleaned_and_freshly_recognized(store, scanned_pdf):
    import json
    first = run_job(store, scanned_pdf, "pdf", ["eng"])
    assert first["state"] == "succeeded", first["error"]
    searchable = artifact_path(store.job_dir(first["id"]),'pdf')
    second = run_job(store, searchable, "pdf", ["eng"])
    assert second["state"] == "succeeded", second["error"]
    metadata=json.loads(second['metadata'])
    assert metadata['ocr_pages']==1 and metadata['reused_pages']==0
    assert metadata['text_preparation']['old_text_reused'] is False


def test_markdown_uses_linked_figures_without_base64(store, digital_pdf, tmp_path):
    from PIL import Image
    import io
    photo = io.BytesIO()
    Image.new("RGB", (320, 200), (50, 120, 90)).save(photo, format="PNG")
    source = tmp_path / "text-and-figure.pdf"
    with pymupdf.open(digital_pdf) as doc:
        doc[0].insert_image(pymupdf.Rect(72, 300, 250, 410), stream=photo.getvalue())
        doc.save(source)
    job = run_job(store, source, "markdown", ["eng"])
    assert job["state"] == "succeeded", job["error"]
    root = store.job_dir(job["id"]) / "result"
    markdown = artifact_path(root,'markdown').read_text(encoding="utf-8")
    assert "Hello world" in markdown
    assert "data:image" not in markdown
    assets = [a for a in store.artifacts(job["id"]) if a["kind"] == "asset"]
    assert assets
    assert all((store.job_dir(job["id"]) / a["path"]).is_file() for a in assets)


def test_scan_markdown_does_not_embed_full_page_images(store, scanned_pdf):
    job = run_job(store, scanned_pdf, "markdown", ["eng"])
    assert job["state"] == "succeeded", job["error"]
    text = artifact_path(store.job_dir(job["id"]),'markdown').read_text(encoding="utf-8")
    assert "Hello world" in text and "data:image" not in text
    assert len(text) < 5000


def test_large_page_render_has_bounded_pixel_count(tmp_path):
    from PIL import Image
    from yuzufile.engines import render_for_ocr, MAX_PIXELS
    with pymupdf.open() as doc:
        page = doc.new_page(width=4000, height=3000)
        page.insert_text((72, 90), "Large sheet")
        path = tmp_path / "bounded.png"
        render_for_ocr(page, path)
        with Image.open(path) as image:
            assert image.width * image.height <= MAX_PIXELS * 1.002


def test_transparent_image_pdf_is_ocrable(store, tmp_path):
    import io
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new("RGBA", (1200, 300), (255, 255, 255, 0))
    ImageDraw.Draw(image).text((40, 90), "Transparency supported", fill=(0, 0, 0, 255),
                              font=ImageFont.load_default(size=58))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    source = tmp_path / "transparent.pdf"
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_image(pymupdf.Rect(30, 60, 570, 195), stream=buffer.getvalue())
        doc.save(source)
    job = run_job(store, source, "pdf", ["eng"])
    assert job["state"] == "succeeded", job["error"]
    with pymupdf.open(artifact_path(store.job_dir(job["id"]),'pdf')) as doc:
        assert "Transparency supported" in doc[0].get_text()


def test_unavailable_language_fails_without_publishing(store, scanned_pdf):
    job = run_job(store, scanned_pdf, "both", ["not_installed"])
    assert job["state"] == "failed"
    assert "no longer available" in job["error"]
    assert not (store.job_dir(job["id"]) / "result").exists()
    assert not (store.job_dir(job["id"]) / "staging").exists()


def test_corrupt_input_has_actionable_error(store, tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.7\ncorrupt")
    job = run_job(store, path, "markdown", [])
    assert job["state"] == "failed"
    assert "damaged" in job["error"]


def test_encrypted_input_explains_unlock_requirement(store, digital_pdf, tmp_path):
    path = tmp_path / "locked.pdf"
    with pymupdf.open(digital_pdf) as doc:
        doc.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="reader")
    job = run_job(store, path, "markdown", [])
    assert job["state"] == "failed"
    assert "unlocked copy" in job["error"]


def test_cancel_kills_worker_and_leaves_no_published_partial_output(store, scanned_pdf):
    job = store.create(scanned_pdf, "both", ["eng"])
    supervisor = Supervisor(store)
    supervisor.tick()
    pid = supervisor.process.pid
    supervisor.cancel(job)
    assert not psutil.pid_exists(pid)
    assert store.get(job)["state"] == "cancelled"
    assert not store.artifacts(job)
    assert not (store.job_dir(job) / "staging").exists()
