import pytest
import sys

from yuzufile.storage import Store


@pytest.fixture(autouse=True)
def drain_qt_test_windows():
    """Finish deleteLater() teardown before another test enters a Qt loop.

    processEvents() alone leaves DeferredDelete events pending. Large combined
    UI suites otherwise accumulate retired windows, sockets and callback owners
    until a later qWait, making destruction order depend on unrelated tests.
    Non-UI tests do not import or construct Qt through this fixture.
    """
    yield
    core=sys.modules.get('PySide6.QtCore')
    if core is not None and core.QCoreApplication.instance() is not None:
        core.QCoreApplication.sendPostedEvents(None,core.QEvent.Type.DeferredDelete)


@pytest.fixture
def store(tmp_path):
    value = Store(tmp_path / "app")
    yield value
    value.close()


@pytest.fixture
def digital_pdf(tmp_path):
    import pymupdf
    path = tmp_path / "Document français with spaces.pdf"
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 90), "A useful document", fontsize=24)
        page.insert_text((72, 135), "Hello world. This is a digital PDF.", fontsize=13)
        doc.save(path)
    return path


@pytest.fixture
def scanned_pdf(tmp_path, digital_pdf):
    import pymupdf
    path = tmp_path / "scan.pdf"
    with pymupdf.open(digital_pdf) as source, pymupdf.open() as doc:
        page = doc.new_page(width=source[0].rect.width, height=source[0].rect.height)
        page.insert_image(page.rect, pixmap=source[0].get_pixmap(dpi=200))
        doc.save(path)
    return path

