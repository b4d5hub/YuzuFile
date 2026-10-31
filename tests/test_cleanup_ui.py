import json
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtWidgets import QApplication

from yuzufile.cleanup import settings
from yuzufile.cleanup_preview import CleanupPreview
from yuzufile.spread_preview import SpreadPreview
from yuzufile.spreads import settings as split_settings
from yuzufile.ui import CompressionBox,Window


@pytest.fixture
def window(store,monkeypatch):
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr('yuzufile.ui.installed_languages',lambda:['eng','fra'])
    view=Window(store)
    view.timer.stop()
    yield view
    view.supervisor.shutdown()
    view.deleteLater()
    app.processEvents()


def test_cleanup_gating_queue_and_retry(window,digital_pdf):
    for code,card in window.operations.items():card.setChecked(code=='cleanup')
    for box in window.languages.values():box.setChecked(False)
    window.add_files([str(digital_pdf)])
    assert window.start_button.isEnabled()
    assert window.start_button.text()=='Clean PDFs'
    assert window.language_row.isHidden()
    window.cleanup_straighten.setChecked(False)
    window.cleanup_trim.setChecked(False)
    assert not window.start_button.isEnabled()
    window.cleanup_trim.setChecked(True)
    window.cleanup_padding.setValue(6)
    window.cleanup_ranges.setText('1')
    window.enqueue()
    job=window.store.jobs()[0]
    assert job['mode']=='cleanup'
    assert json.loads(job['languages'])==[]
    assert json.loads(job['cleanup_settings'])['padding_mm']==6
    window.store.update(job['id'],'failed','Failed','Test fixture')
    window.cleanup_padding.setValue(3)
    window.retry_job(job['id'])
    assert window.cleanup_padding.value()==6
    assert not window.cleanup_straighten.isChecked()
    assert window.cleanup_ranges.text()=='1'


def test_preview_matches_options_and_rejects_invalid_ranges(window,digital_pdf):
    original=digital_pdf.read_bytes()
    preview=CleanupPreview(window,[digital_pdf],settings({'straighten':False}),CompressionBox)
    try:
        assert preview.apply.isEnabled()
        assert preview.detail['trimmed']
        assert not preview.before.pixmap.isNull() and not preview.after.pixmap.isNull()
        small=preview.detail['output_size']
        preview.padding.setValue(15)
        preview.render_page()
        assert preview.detail['output_size'][0]>small[0]
        preview.ranges.setText('3')
        preview.render_page()
        assert not preview.apply.isEnabled()
        assert preview.after.pixmap.isNull()
    finally:
        preview.reject()
    assert preview.document is None
    assert not preview.timer.isActive()
    assert digital_pdf.read_bytes()==original


def test_split_preview_shows_cleanup_before_dividing(window,digital_pdf):
    preview=SpreadPreview(window,[digital_pdf],split_settings(),CompressionBox,
                          settings({'straighten':False}))
    try:
        assert preview.apply.isEnabled()
        # Cropped source becomes wide rather than the original portrait page.
        assert preview.canvas.pixmap.width()>preview.canvas.pixmap.height()
    finally:preview.reject()
