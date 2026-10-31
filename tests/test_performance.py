"""Resource isolation, bounded parts and content preservation across presets."""
import ctypes
import os
import sqlite3
from ctypes import wintypes

import pymupdf
import pytest

from yuzufile.performance import PROFILES, performance_profile
from yuzufile.storage import Store
from yuzufile.windows_job import WindowsJob


@pytest.mark.parametrize("code", list(PROFILES))
@pytest.mark.parametrize('neural', ['none', 'rapid', 'indra'])
def test_ocr_drains_and_cleans_each_part(code, neural, tmp_path, monkeypatch):
    from yuzufile import engines
    profile = performance_profile(code)
    monkeypatch.setattr('yuzufile.neural_text.available', lambda: neural == 'rapid')
    monkeypatch.setattr('yuzufile.indra_engine.available', lambda: neural == 'indra')
    workers = 1 if neural != 'none' else profile.page_workers()
    with pymupdf.open() as overlay:
        overlay.new_page().insert_text((40, 80), "Verified page text")
        overlay_bytes = overlay.tobytes()
    events = []
    rendered = []

    def render(page, path):
        # Every preceding part must be drained before a new part starts.
        count = len(list(tmp_path.glob("page-*.png")))
        assert count < workers
        rendered.append(count)
        path.write_bytes(b"temporary raster")
        return 220

    def recognize(path, dpi, languages, page_number):
        target = path.with_suffix(".pdf")
        target.write_bytes(overlay_bytes)
        return target

    monkeypatch.setattr(engines, "render_for_ocr", render)
    monkeypatch.setattr(engines, "recognize_page", recognize)
    monkeypatch.setattr(engines, "page_needs_ocr", lambda page: True)
    with pymupdf.open() as document:
        for _ in range(7):
            document.new_page()
        stats = engines.add_searchable_text(document, tmp_path, ["eng"],
                                            lambda stage, **kw: events.append(stage), profile)
        assert all("Verified page text" in page.get_text() for page in document)
    assert stats["recognized_pages"] == 7
    assert stats["ocr_parts"] == (7 + workers - 1) // workers
    assert rendered == [i % workers for i in range(7)]
    assert any("Part 2" in stage for stage in events)
    assert not list(tmp_path.iterdir())


def test_old_history_migrates_with_balanced_budget(tmp_path):
    home = tmp_path / "old-library"
    home.mkdir()
    with sqlite3.connect(home / "history.sqlite3") as db:
        db.execute("""CREATE TABLE jobs(id TEXT PRIMARY KEY, source TEXT NOT NULL,
            mode TEXT NOT NULL, languages TEXT NOT NULL, state TEXT NOT NULL,
            stage TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL,
            error TEXT NOT NULL DEFAULT '', metadata TEXT NOT NULL DEFAULT '{}')""")
        db.execute("INSERT INTO jobs(id,source,mode,languages,state,stage,created,updated) VALUES(?,?,?,?,?,?,?,?)",
                   ("legacy", "old.pdf", "both", '["eng"]', "succeeded", "Completed", "old", "old"))
    store = Store(home)
    try:
        assert store.get("legacy")["performance"] == "balanced"
        assert store.get("legacy")["state"] == "succeeded"
    finally:
        store.close()


def test_invalid_performance_cannot_queue(store, digital_pdf):
    with pytest.raises(ValueError, match="performance"):
        store.create(digital_pdf, "both", ["eng"], performance="unknown")
    assert not store.jobs()


@pytest.mark.skipif(os.name != "nt", reason="Native Windows resource enforcement")
@pytest.mark.parametrize("code", list(PROFILES))
def test_windows_enforces_requested_cpu_and_memory_budgets(code):
    profile = performance_profile(code)
    group = WindowsJob(profile.memory_mb, profile.cpu_percent)
    try:
        kernel = group.kernel
        kernel.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
            ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
        kernel.QueryInformationJobObject.restype = wintypes.BOOL
        # Windows' extended-limits ABI places JobMemoryLimit after ProcessMemoryLimit.
        extended = ctypes.create_string_buffer(144 if ctypes.sizeof(ctypes.c_void_p) == 8 else 112)
        assert kernel.QueryInformationJobObject(group.handle, 9, extended, len(extended), None)
        offset = 120 if ctypes.sizeof(ctypes.c_void_p) == 8 else 100
        assert ctypes.c_size_t.from_buffer(extended, offset).value == profile.memory_mb * 1024**2
        cpu = (wintypes.DWORD * 2)()
        assert kernel.QueryInformationJobObject(group.handle, 15, cpu, ctypes.sizeof(cpu), None)
        assert cpu[0] == 0x5 and cpu[1] == profile.cpu_percent * 100
    finally:
        group.close()
