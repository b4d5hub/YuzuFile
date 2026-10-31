"""Image-only output remains distinct from fresh recognition in UI and history."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import itertools,json
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from yuzufile.operations import MODES,mode_for,mode_label
from yuzufile.ui import Window


@pytest.fixture
def window(store,monkeypatch):
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr('yuzufile.ui.installed_languages',lambda:['eng','fra','ara'])
    result=Window(store);result.timer.stop();result.show();app.processEvents()
    yield result
    result.supervisor.shutdown();result.deleteLater();app.processEvents()


def test_image_only_combinations_have_stable_unique_history_modes():
    original={'pdf':{'ocr'},'both':{'ocr','markdown'},'all':{'ocr','markdown','compress'},
              'word':{'docx'},'split':{'split'},'cleanup':{'cleanup'},'organize':{'organize'}}
    for name,operations in original.items():assert MODES[name]==operations
    generated=[]
    for count in range(4):
        for additions in itertools.combinations(('cleanup','split','compress'),count):
            selected={'remove_ocr',*additions};mode=mode_for(selected)
            assert MODES[mode]==selected and 'Remove OCR' in mode_label(mode)
            generated.append(mode)
    assert len(set(generated))==8
    assert all(not (ops & {'ocr','markdown','docx'}) for ops in MODES.values() if 'remove_ocr' in ops)
    assert mode_for({'remove_ocr'})=='remove_ocr'


@pytest.mark.parametrize('recognition',['ocr','markdown','docx'])
def test_image_only_cannot_be_combined_with_recognition(recognition):
    with pytest.raises(ValueError,match='image-only'):
        mode_for({'remove_ocr',recognition})


def test_remove_ocr_is_language_free_and_clearly_labeled(window,digital_pdf):
    for language in window.languages.values():language.setChecked(False)
    assert window.operations['ocr'].isChecked()
    button=window.operations['remove_ocr']
    QTest.mouseClick(button,Qt.MouseButton.LeftButton,pos=button.hit_point.toPoint())
    assert window.selected_operations()=={'remove_ocr'}
    assert window.language_row.isHidden() and not window.remove_ocr_row.isHidden()
    assert 'image-only' in window.remove_ocr_row.text() and 'selectable' in button.toolTip()
    assert window.start_button.text()=='Remove OCR'
    assert not window.start_button.isEnabled()
    window.add_files([digital_pdf]);assert window.start_button.isEnabled()
    before=digital_pdf.read_bytes();window.start_button.click()
    job=window.store.jobs()[0]
    assert job['mode']=='remove_ocr' and json.loads(job['languages'])==[]
    assert window.operation_caption(job)=='Remove OCR'
    assert digital_pdf.read_bytes()==before


@pytest.mark.parametrize('recognition',['ocr','markdown','docx'])
def test_selecting_recognition_switches_off_image_only(window,recognition):
    window.operations['remove_ocr'].setChecked(True)
    window.operations[recognition].setChecked(True)
    assert window.selected_operations()=={recognition}
    assert not window.language_row.isHidden() and window.remove_ocr_row.isHidden()


def test_remove_with_page_tools_and_compression_queues_and_retries(window,digital_pdf,tmp_path):
    window.operations['remove_ocr'].setChecked(True)
    for code in ('cleanup','split','compress'):window.operations[code].setChecked(True)
    destination=tmp_path/'image-only output';destination.mkdir()
    window.set_output_directory(destination)
    window.split_parts.setValue(3);window.performance.setCurrentIndex(window.performance.findData('low'))
    window.add_files([digital_pdf]);window.start_button.click()
    job=window.store.jobs()[0]
    assert MODES[job['mode']]=={'remove_ocr','cleanup','split','compress'}
    assert json.loads(job['languages'])==[] and json.loads(job['split_settings'])['parts']==3
    assert job['output_directory']==str(destination) and job['performance']=='low'
    window.store.update(job['id'],'failed','Failed','Fixture')
    window.operations['docx'].setChecked(True)
    assert not window.operations['remove_ocr'].isChecked()
    window.retry_job(job['id'])
    assert window.selected_operations()=={'remove_ocr','cleanup','split','compress'}
    assert window.output_directory==destination and window.performance.currentData()=='low'
    assert not any(window.operations[c].isChecked() for c in ('ocr','markdown','docx'))
    assert 'Remove OCR' in window.operation_caption(window.store.get(job['id']))
    assert window.store.get(job['id'])


def test_all_wheel_segments_keep_center_and_click_targets_separate(window):
    assert len(window.tool_wheel.buttons)==9
    center=window.tool_wheel.rect().center()
    assert window.tool_wheel.childAt(center) is window.upload
    for button in window.tool_wheel.buttons:
        point=button.mapTo(window.tool_wheel,button.hit_point.toPoint())
        assert window.tool_wheel.childAt(point) is button
        assert not button.hitButton(button.mapFrom(window.tool_wheel,center))


@pytest.mark.parametrize('languages',[['ara'],['ara','fra'],['missing'],[]])
def test_retry_recognition_recalls_only_the_job_languages(window,digital_pdf,languages):
    job=window.store.create(digital_pdf,'word',languages)
    window.store.update(job,'failed','Failed','Fixture')
    window.retry_job(job)
    selected={code for code,box in window.languages.items() if box.isChecked()}
    assert selected==set(languages)&{'eng','fra','ara'}
    assert window.start_button.isEnabled()==bool(selected)
    # The job selection is recalled for this retry, not saved as a default.
    if selected:
        window.enqueue()
        assert window.languages['eng'].isChecked() and not window.languages['ara'].isChecked()


def test_cli_documents_image_only_format(monkeypatch,capsys):
    from yuzufile.cli import main
    monkeypatch.setattr('sys.argv',['yuzufile','convert','--help'])
    with pytest.raises(SystemExit) as result:main()
    assert result.value.code==0
    help_text=capsys.readouterr().out
    assert 'remove_ocr' in help_text and 'image-only PDF' in help_text
