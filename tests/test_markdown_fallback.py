import sys

import pymupdf
import pytest

from yuzufile.engines import write_markdown


def test_missing_layout_library_preserves_readable_markdown(digital_pdf, tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "pymupdf4llm", None)
    destination = tmp_path / "fallback.md"
    with pymupdf.open(digital_pdf) as document:
        notes = write_markdown(document, destination, lambda *args, **kwargs: None)
    assert "Hello world" in destination.read_text(encoding="utf-8")
    assert any("readable text" in note for note in notes)


def test_layout_error_on_one_page_preserves_text(digital_pdf, tmp_path, monkeypatch):
    import pymupdf4llm
    def broken(*args, **kwargs):
        raise RuntimeError("simulated unusual layout")
    monkeypatch.setattr(pymupdf4llm, "to_markdown", broken)
    destination = tmp_path / "layout-fallback.md"
    with pymupdf.open(digital_pdf) as document:
        notes = write_markdown(document, destination, lambda *args, **kwargs: None)
    assert "Hello world" in destination.read_text(encoding="utf-8")
    assert any("Page 1" in note for note in notes)


@pytest.mark.parametrize("incomplete", ["", "A useful document", "![Figure](assets/Hello-world.png)", None])
def test_silent_missing_text_recovers_source(digital_pdf, tmp_path, monkeypatch, incomplete):
    import pymupdf4llm
    monkeypatch.setattr(pymupdf4llm, "to_markdown", lambda *args, **kwargs: incomplete)
    destination = tmp_path / "recovered.md"
    with pymupdf.open(digital_pdf) as document:
        notes = write_markdown(document, destination, lambda *args, **kwargs: None)
    text = destination.read_text(encoding="utf-8")
    assert "Hello world" in text
    assert "A useful document" in text
    assert any("omitted text" in note for note in notes)


def test_graphics_retry_preserves_structured_markdown(digital_pdf, tmp_path, monkeypatch):
    import pymupdf4llm
    calls = []
    def extract(*args, **kwargs):
        calls.append(kwargs)
        if not kwargs["ignore_graphics"]:
            return ""
        return "# A useful document\n\nHello world. This is a digital PDF."
    monkeypatch.setattr(pymupdf4llm, "to_markdown", extract)
    destination = tmp_path / "retry.md"
    with pymupdf.open(digital_pdf) as document:
        notes = write_markdown(document, destination, lambda *args, **kwargs: None)
    assert destination.read_text(encoding="utf-8").startswith("# A useful document")
    assert len(calls) == 2 and calls[-1]["ignore_graphics"]
    assert all(call["ignore_alpha"] and call["fontsize_limit"] == 0 for call in calls)
    assert not any("used plain-text" in note for note in notes)


def test_invisible_text_beneath_graphics_survives(tmp_path):
    # A full-page drawing can be classified as a graphic and hide an otherwise
    # extractable OCR layer, without the converter raising an exception.
    source = tmp_path / "already-searchable.pdf"
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.draw_rect(page.rect, color=(0, 0, 0), fill=(1, 1, 1))
        page.insert_text((72, 90), "Existing searchable text must survive", render_mode=3)
        page.insert_text((72, 120), "Small searchable text also survives", fontsize=2, render_mode=3)
        doc.save(source)
    destination = tmp_path / "invisible.md"
    with pymupdf.open(source) as document:
        write_markdown(document, destination, lambda *args, **kwargs: None)
    text = destination.read_text(encoding="utf-8")
    assert "Existing searchable text must survive" in text
    assert "Small searchable text also survives" in text


def test_empty_conversion_keeps_symbol_only_page(tmp_path, monkeypatch):
    import pymupdf4llm
    monkeypatch.setattr(pymupdf4llm, "to_markdown", lambda *args, **kwargs: "")
    destination = tmp_path / "symbols.md"
    with pymupdf.open() as document:
        document.new_page().insert_text((72, 90), "+ - = < > !")
        write_markdown(document, destination, lambda *args, **kwargs: None)
    assert "+ - = < > !" in destination.read_text(encoding="utf-8")
