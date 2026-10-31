"""Per-conversion native-library policy and bounded page traversal."""
from contextlib import contextmanager
import gc

from yuzufile.performance import Performance, performance_profile


def trim_cache():
    import pymupdf
    pymupdf.TOOLS.store_shrink(100)
    gc.collect()


@contextmanager
def library_budget(profile: Performance):
    import pymupdf
    previous = pymupdf.TOOLS.set_low_memory()
    pymupdf.TOOLS.set_low_memory(profile.code == "low")
    trim_cache()
    try:
        yield
    finally:
        try:
            trim_cache()
        finally:
            pymupdf.TOOLS.set_low_memory(previous)


def page_indices(count: int, profile: Performance | None = None, notify=None,
                 stage: str = "Checking pages", start: int = 0, end: int = 100):
    """Keep native caches bounded at part boundaries and report steady progress.

    Trim between page parts because this PyMuPDF build does not expose native
    cache-size accounting. The Windows process-tree limit is the memory ceiling.
    """
    profile = profile or performance_profile()
    part_size = profile.page_workers()
    parts = (count + part_size - 1) // part_size
    try:
        for index in range(count):
            if index % part_size == 0:
                trim_cache()
                if notify:
                    notify(f"{stage} · part {index // part_size + 1} of {parts}",
                           progress=round(start + (end - start) * index / max(1, count)))
            yield index
    finally:
        trim_cache()
