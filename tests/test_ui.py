import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
import pytest
from PySide6.QtGui import QPalette
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QTextBrowser, QMessageBox
from PySide6.QtWidgets import QFileDialog
from yuzufile.ui import Window
from yuzufile.ui_style import COLORS


def test_word_tool_queues_with_languages_and_can_retry(window,digital_pdf):
    for code,card in window.operations.items():card.setChecked(code=='docx')
    window.add_files([str(digital_pdf)])
    assert window.start_button.text()=='Export Word'
    assert not window.language_row.isHidden()
    window.enqueue()
    job=window.store.jobs()[0]
    assert job['mode']=='word' and json.loads(job['languages'])
    window.store.update(job['id'],'failed','Failed','Test fixture')
    window.retry_job(job['id'])
    assert window.operations['docx'].isChecked()


def test_word_result_opens_docx_and_disables_missing_output(window,digital_pdf,monkeypatch):
    job=window.store.create(digital_pdf,'word',['eng'])
    result=window.store.job_dir(job)/'result'
    result.mkdir(parents=True)
    output=result/'document.docx'
    output.write_bytes(b'fixture')
    (result/'manifest.json').write_text(json.dumps({'artifacts':[
        {'path':'result/document.docx','kind':'docx'}],'metadata':{}}))
    window.store.complete(job)
    output=window.artifact_path(job,'docx')

    opened=[]
    monkeypatch.setattr(window,'open_path',opened.append)
    action=next(a for a in window.create_job_menu(job).actions() if a.text()=='Open Word')
    assert action.isEnabled()
    action.trigger()
    assert opened==[output]
    output.unlink()
    assert not next(a for a in window.create_job_menu(job).actions() if a.text()=='Open Word').isEnabled()


def test_history_removed_but_session_results_and_existing_records_preserved(window,digital_pdf):
    job=window.store.create(digital_pdf,'compress',[])
    window.store.update(job,'failed','Failed','Fixture')
    window.refresh_queue()
    assert window.tabs.count()==1
    assert not hasattr(window,'show_history')
    assert not window.cards
    window.session_jobs.append(job);window.refresh_queue()
    assert job in window.cards
    assert all('History' not in action.text() for action in window.create_job_menu(job).actions())
    window.clear_finished()
    assert not window.cards and window.store.get(job)['state']=='failed'


def test_output_picker_cancel_reset_and_queued_destination(window, digital_pdf, tmp_path, monkeypatch):
    destination = tmp_path / 'Chosen outputs'
    destination.mkdir()
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *args: str(destination))
    window.choose_output_directory()
    assert window.output_path.text() == str(destination)
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *args: '')
    window.choose_output_directory()
    assert window.output_directory == destination
    window.add_files([str(digital_pdf)])
    window.start_button.click()
    job = window.store.jobs()[0]
    assert job['output_directory'] == str(destination)
    window.store.update(job['id'], 'failed', 'Failed', 'Test fixture')
    window.output_reset.click()
    assert window.output_directory is None
    window.retry_job(job['id'])
    assert window.output_directory == destination
    window.output_reset.click()
    assert window.output_directory is None


def test_output_folder_actions_follow_chosen_location(window, digital_pdf, tmp_path, monkeypatch):
    destination = tmp_path / 'exports'
    destination.mkdir()
    job = window.store.create(digital_pdf, 'markdown', [], output_directory=destination)
    result = window.store.job_dir(job) / 'result'
    result.mkdir(parents=True)
    (result / 'document.md').write_text('Hello')
    (result / 'manifest.json').write_text(json.dumps({'artifacts': [
        {'path': 'result/document.md', 'kind': 'markdown'}], 'metadata': {}}))
    window.store.complete(job)
    opened = []
    monkeypatch.setattr(window, 'open_path', opened.append)
    window.open_artifact(job, 'markdown')
    window.open_job_folder(job)
    assert opened == [result / 'document.md', result]


def test_rounded_popup_supports_keyboard_mouse_and_escape(window):
    window.show()
    app = QApplication.instance()
    combo = window.performance
    combo.showPopup()
    app.processEvents()
    QTest.keyClick(combo.view(), Qt.Key.Key_Down)
    QTest.keyClick(combo.view(), Qt.Key.Key_Return)
    assert combo.currentData() == 'high'
    assert not combo.popup.isVisible()
    combo.showPopup()
    app.processEvents()
    index = combo.model().index(0, 0)
    QTest.mouseClick(combo.view().viewport(), Qt.MouseButton.LeftButton,
                     pos=combo.view().visualRect(index).center())
    assert combo.currentData() == 'low'
    combo.showPopup()
    app.processEvents()
    QTest.keyClick(combo.view(), Qt.Key.Key_Escape)
    assert not combo.popup.isVisible()
    assert combo.currentData() == 'low'


def test_process_button_click_queues_each_file_once(window, digital_pdf):
    window.add_files([str(digital_pdf)])
    window.start_button.click()
    assert len(window.store.jobs()) == 1
    assert not window.start_button.isEnabled()
    window.start_button.click()
    assert len(window.store.jobs()) == 1


def test_split_only_settings_and_retry(window, digital_pdf):
    window.operations['ocr'].setChecked(False)
    window.operations['split'].setChecked(True)
    window.languages['eng'].setChecked(False)
    window.split_direction.setCurrentIndex(window.split_direction.findData('bt'))
    window.split_position.setValue(45)
    window.add_files([str(digital_pdf)])
    assert window.start_button.isEnabled()
    assert window.language_row.isHidden()
    assert not window.split_row.isHidden()
    window.enqueue()
    job=window.store.jobs()[0]
    assert job['mode']=='split'
    assert json.loads(job['split_settings'])=={'direction':'bt','position':45,'pages':'','parts':2}
    window.store.update(job['id'],'failed','Failed','Fixture')
    window.split_position.setValue(50)
    window.retry_job(job['id'])
    assert window.split_position.value()==45
    assert window.split_direction.currentData()=='bt'


def test_dropdowns_use_readable_light_popup_colors(window):
    for combo in (window.compression, window.performance):
        popup = combo.view()
        for group in (QPalette.Active, QPalette.Inactive):
            assert popup.palette().color(group, QPalette.Base).name() == '#ffffff'
            assert popup.palette().color(group, QPalette.Text).name() == COLORS['text']
            assert popup.window().palette().color(group, QPalette.Window).name() == '#ffffff'


def test_tool_wheel_toggles_with_mouse_and_keyboard(window):
    window.show();QApplication.instance().processEvents()
    card=window.operations['markdown']
    assert card.accessibleName()=='Markdown'
    QTest.mouseClick(card,Qt.MouseButton.LeftButton,pos=card.hit_point.toPoint())
    assert card.isChecked()
    card.setFocus();QTest.keyClick(card,Qt.Key.Key_Space)
    assert card.isChecked()
    QTest.keyClick(card,Qt.Key.Key_Space,Qt.KeyboardModifier.ShiftModifier)
    assert not card.isChecked()
    assert card.accessibleDescription()


def test_contextual_run_action_and_progressive_options(window,digital_pdf):
    for box in window.operations.values():box.setChecked(False)
    assert window.ready_label.text()=='Add PDFs to begin'
    window.operations['markdown'].setChecked(True)
    window.add_files([str(digital_pdf)])
    assert window.start_button.text()=='Export Markdown'
    assert window.ready_label.text()=='1 PDF ready'
    assert window.compression_row.isHidden()
    window.operations['compress'].setChecked(True)
    assert not window.compression_row.isHidden()
    assert window.start_button.text()=='Process PDFs'
    window.operations['markdown'].setChecked(False)
    assert window.language_row.isHidden()
    assert window.start_button.text()=='Compress PDFs'
    window.output_path.setFocus()
    for button in window.findChildren(QPushButton,'iconButton'):
        assert button.accessibleName() and button.toolTip()


def test_window_fits_screen_and_compact_home_scrolls_vertically(window):
    app = QApplication.instance()
    available = window.screen().availableGeometry()
    assert window.width() <= available.width()
    assert window.height() <= available.height()
    window.resize(720, 540)
    window.show()
    app.processEvents()
    scroll = window.tabs.widget(0)
    assert scroll.area.geometry().bottom()<scroll.dock.geometry().top()
    assert scroll.horizontalScrollBar().maximum() == 0
    assert scroll.verticalScrollBar().maximum() > 0
    before=window.start_button.mapTo(window,window.start_button.rect().center())
    for value in (scroll.verticalScrollBar().maximum(),0):
        scroll.verticalScrollBar().setValue(value)
        app.processEvents()
        assert window.rect().contains(window.start_button.mapTo(window,window.start_button.rect().center()))
        assert window.start_button.mapTo(window,window.start_button.rect().center())==before

@pytest.fixture
def window(store, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr('yuzufile.ui.installed_languages', lambda: ['eng', 'fra'])
    view = Window(store)
    view.timer.stop()
    yield view
    view.supervisor.shutdown()
    view.deleteLater()
    app.processEvents()


def test_initial_languages_are_available_only_and_english_is_selected(window):
    assert list(window.languages) == ['eng', 'fra']
    assert window.languages['eng'].isChecked()
    assert not window.languages['fra'].isChecked()
    assert window.operations['ocr'].isChecked()
    assert not window.start_button.isEnabled()
    assert window.home_link.isChecked()
    window.home_link.click()
    assert window.home_link.isChecked()
    assert window.tabs.currentIndex() == 0


def test_performance_selection_is_per_batch_and_recalled_for_retry(window, digital_pdf):
    assert window.performance.currentData() == "balanced"
    window.performance.setCurrentIndex(window.performance.findData("low"))
    window.add_files([str(digital_pdf)])
    window.enqueue()
    job = window.store.jobs()[0]
    assert job["performance"] == "low"
    assert window.performance.currentData() == "balanced"
    window.store.update(job["id"], "failed", "Failed", "Test failure")
    window.retry_job(job["id"])
    assert window.performance.currentData() == "low"
    dialog = window.view_details(job["id"])
    assert "Performance: Low usage" in dialog.findChild(QTextBrowser).toPlainText()
    dialog.close()


def test_selected_files_have_remove_actions_and_button_gating(window, digital_pdf):
    window.add_files([str(digital_pdf), str(digital_pdf)])
    assert window.files.count() == 1
    assert window.start_button.isEnabled()
    window.languages['eng'].setChecked(False)
    assert not window.start_button.isEnabled()
    window.operations['ocr'].setChecked(False)
    window.operations['compress'].setChecked(True)
    assert window.start_button.isEnabled()
    assert window.language_row.isHidden()
    assert not window.compression_row.isHidden()
    assert window.compression.currentData() == 'balanced'
    row = window.files.itemWidget(window.files.item(0))
    remove = next(b for b in row.findChildren(QPushButton) if b.accessibleName().startswith('Remove '))
    remove.click()
    assert not window.pending
    assert not window.start_button.isEnabled()


def test_combined_operations_and_per_batch_language_choices(window, digital_pdf):
    window.languages['fra'].setChecked(True)
    window.operations['markdown'].setChecked(True)
    window.operations['compress'].setChecked(True)
    window.compression.setCurrentIndex(window.compression.findData('maximum'))
    window.add_files([str(digital_pdf)])
    window.enqueue()
    job = window.store.jobs()[0]
    assert job['mode'] == 'all'
    assert job['compression'] == 'maximum'
    assert json.loads(job['languages']) == ['eng', 'fra']
    assert window.languages['eng'].isChecked()
    assert not window.languages['fra'].isChecked()
    assert job['id'] in window.cards
    assert not window.cards[job['id']]['cancel'].isHidden()
    window.operations['ocr'].setChecked(False)
    window.operations['markdown'].setChecked(False)
    window.operations['compress'].setChecked(False)
    window.add_files([str(digital_pdf)])
    assert not window.start_button.isEnabled()


def test_markdown_without_languages_is_disabled(window, digital_pdf):
    window.operations['ocr'].setChecked(False)
    window.operations['markdown'].setChecked(True)
    window.languages['eng'].setChecked(False)
    window.add_files([str(digital_pdf)])
    assert not window.language_row.isHidden()
    assert not window.start_button.isEnabled()


def test_compression_mode_queues_without_languages(window, digital_pdf):
    window.operations['ocr'].setChecked(False)
    window.operations['compress'].setChecked(True)
    window.languages['eng'].setChecked(False)
    window.add_files([str(digital_pdf)])
    window.enqueue()
    job = window.store.jobs()[0]
    assert job['mode'] == 'compress'
    assert job['languages'] == '[]'
    window.cancel_job(job['id'])
    assert window.store.get(job['id'])['state'] == 'cancelled'
    assert window.cards[job['id']]['cancel'].isHidden()




def test_compression_options_follow_tool_selection_and_remove_all(window, digital_pdf):
    assert window.compression_row.isHidden()
    assert not window.compression.isEnabled()
    window.operations['compress'].setChecked(True)
    assert window.compression.isEnabled()
    assert not window.compression_row.isHidden()
    window.add_files([str(digital_pdf)])
    assert window.remove_all.isEnabled()
    window.remove_all.click()
    assert not window.pending
    assert not window.start_button.isEnabled()


def test_clear_finished_keeps_history_and_queued_items(window, digital_pdf):
    finished = window.store.create(digital_pdf, 'pdf', ['eng'])
    waiting = window.store.create(digital_pdf, 'compress', [])
    window.store.update(finished, 'cancelled', 'Cancelled')
    window.session_jobs = [finished, waiting]
    window.refresh_queue()
    window.clear_finished()
    assert window.session_jobs == [waiting]
    assert window.store.get(finished)['state'] == 'cancelled'
    assert window.store.get(waiting)['state'] == 'queued'




def test_language_unavailable_does_not_show_or_select_it(window, monkeypatch, digital_pdf):
    monkeypatch.setattr('yuzufile.ui.installed_languages', lambda: ['fra'])
    window.refresh_languages()
    assert list(window.languages) == ['fra']
    assert not window.languages['fra'].isChecked()
    window.add_files([str(digital_pdf)])
    assert not window.start_button.isEnabled()




def test_clear_completed_keeps_outputs_and_missing_file_menu_is_disabled(window, digital_pdf):
    job = window.store.create(digital_pdf, 'pdf', ['eng'])
    result = window.store.job_dir(job) / 'result'
    result.mkdir(parents=True)
    output = result / 'document.pdf'
    output.write_bytes(digital_pdf.read_bytes())
    (result / 'manifest.json').write_text(json.dumps({
        'artifacts': [{'path': 'result/document.pdf', 'kind': 'pdf'}], 'metadata': {}}))
    window.store.complete(job)
    window.session_jobs.append(job)
    window.refresh_queue()
    window.clear_finished_button.click()
    assert window.store.get(job)['state'] == 'succeeded'
    assert output.exists()
    assert digital_pdf.exists()
    assert not window.session_jobs
    menu = window.create_job_menu(job)
    assert next(a for a in menu.actions() if a.text() == 'Open PDF').isEnabled()
    output=window.artifact_path(job,'pdf')
    output.unlink()
    menu = window.create_job_menu(job)
    assert not next(a for a in menu.actions() if a.text() == 'Open PDF').isEnabled()
