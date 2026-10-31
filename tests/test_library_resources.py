import pymupdf
import pytest

from yuzufile.performance import PROFILES
from yuzufile.resources import library_budget, page_indices
from test_compression import image_pdf  # Shared PDF with bookmarks, links and annotations.


def test_library_policy_is_restored_after_failure():
    initial = pymupdf.TOOLS.set_low_memory()
    with pytest.raises(RuntimeError):
        with library_budget(PROFILES['low']):
            assert pymupdf.TOOLS.set_low_memory() is True
            raise RuntimeError('native stage failed')
    assert pymupdf.TOOLS.set_low_memory() == initial


@pytest.mark.parametrize('profile', PROFILES.values(), ids=list(PROFILES))
def test_native_page_checks_are_ordered_and_clear_caches(profile, monkeypatch):
    calls = []
    monkeypatch.setattr('yuzufile.resources.trim_cache', lambda: calls.append('trim'))
    events = []
    assert list(page_indices(7, profile, lambda stage, **kw: events.append(kw['progress']))) == list(range(7))
    parts = (7 + profile.page_workers() - 1) // profile.page_workers()
    assert len(events) == parts
    assert len(calls) == parts + 1
    assert events == sorted(events)


@pytest.mark.parametrize('profile', PROFILES.values(), ids=list(PROFILES))
def test_compression_with_each_budget_preserves_pdf_features(profile, image_pdf, tmp_path):
    from yuzufile.compression import compress_pdf
    target = tmp_path / (profile.code + '.pdf')
    events = []
    with library_budget(profile), pymupdf.open(image_pdf) as document:
        compress_pdf(document, image_pdf, target, 'balanced',
                     lambda stage, **kw: events.append(stage), profile)
    with pymupdf.open(image_pdf) as original, pymupdf.open(target) as result:
        assert original.get_toc() == result.get_toc()
        for a, b in zip(original, result):
            assert a.get_text() == b.get_text()
            assert a.get_links()[0]['uri'] == b.get_links()[0]['uri']
            assert list(a.annots())[0].info['content'] == list(b.annots())[0].info['content']
    assert any('Checking PDF before compression · part' in stage for stage in events)
    assert any('Verifying compressed PDF · part' in stage for stage in events)
