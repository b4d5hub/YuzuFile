"""Focused tools retain the real conversion and navigation contracts."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json,hashlib
import pymupdf,pytest
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QApplication,QDialog,QMenu
from PySide6.QtTest import QTest
from yuzufile.ui import Window
from yuzufile.shaped_shell import FloatingShell
from yuzufile.tool_window import ToolDialog


@pytest.fixture
def shell(store,monkeypatch):
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr('yuzufile.ui.installed_languages',lambda:['eng','fra','ara'])
    view=Window(store);view.timer.stop();shell=FloatingShell(view)
    shell.show();app.processEvents()
    yield shell
    shell.shutdown();view.supervisor.shutdown()
    shell.hide();view.hide();shell.deleteLater();view.deleteLater();app.processEvents()


def test_tool_launch_is_single_and_combining_is_explicit(shell,digital_pdf,monkeypatch):
    view=shell.controller;view.add_files([digital_pdf])
    button=view.operations['compress'];QTest.mouseClick(button,Qt.MouseButton.LeftButton,pos=button.hit_point.toPoint())
    QApplication.processEvents()
    assert view.selected_operations()=={'compress'} and not shell.wheel.isVisible()
    assert shell.task_header.title.text()=='Compress PDF' and shell.combine_button.isVisible()
    shell.combine_button.click();QApplication.processEvents()
    menu=shell.tool_menu
    next(a for a in menu.actions() if a.text()=='Word document').trigger();menu.close()
    assert view.selected_operations()=={'compress','docx'} and view.language_row.isVisible()
    shell.collapse_button.click();assert shell.mode=='wheel' and view.pending==[digital_pdf]


def test_shift_click_combines_without_accidentally_running_a_tool(shell,digital_pdf):
    view=shell.controller;view.add_files([digital_pdf])
    button=view.operations['compress']
    QTest.mouseClick(button,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.ShiftModifier,pos=button.hit_point.toPoint())
    assert view.selected_operations()=={'ocr','compress'}
    assert not view.store.jobs()


def test_focused_dialog_hides_launcher_and_restores_it_on_close(shell):
    dialog=ToolDialog(shell,title='Focused tool');seen=[]
    assert not dialog.testAttribute(Qt.WidgetAttribute.WA_QuitOnClose)
    def inspect():
        seen.append((shell.isVisible(),dialog.isVisible(),dialog.header.height()))
        dialog.accept()
    QTimer.singleShot(0,inspect)
    assert shell.controller.exec_tool(dialog)==QDialog.DialogCode.Accepted
    assert seen==[(False,True,48)] and shell.isVisible()
    dialog.deleteLater()


def test_batch_results_can_select_every_file_without_opening_history(shell,digital_pdf):
    view=shell.controller
    first=view.store.create(digital_pdf,'compress',[]);second=view.store.create(digital_pdf,'compress',[])
    for job in (first,second):view.store.update(job,'failed','Failed','Fixture')
    view.session_jobs.extend([first,second]);shell.sync_from_controller();QApplication.processEvents()
    assert shell.job_picker.isVisible() and shell.job_picker.count()==2
    shell.job_picker.setCurrentIndex(shell.job_picker.findData(first))
    assert shell._job_id==first and shell.pill_tools.isVisible()
    shell.job_picker.setCurrentIndex(shell.job_picker.findData(second))
    assert shell._job_id==second and shell.pill_tools.isVisible()


def test_merge_uses_document_order_names_output_and_keeps_originals(shell,digital_pdf,tmp_path):
    from yuzufile.merge_ui import MergeDialog
    from yuzufile.worker import convert
    other=tmp_path/'Meeting notes.pdf'
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((30,60),'MEETING FIRST');pdf.save(other)
    before={p:hashlib.sha256(p.read_bytes()).digest() for p in (digital_pdf,other)}
    dialog=MergeDialog(shell,[digital_pdf,other]);dialog.move_document(1,-1);dialog.finish()
    plan=dialog.result_plan;assert plan['action']=='merge'
    view=shell.controller;job_id=view.enqueue_organization(plan);job=view.store.get(job_id)
    assert json.loads(job['page_plan'])['action']=='merge'
    root=view.store.job_dir(job_id)
    convert(dict(root=str(root),source=job['source'],mode='organize',languages=[],page_plan=plan,performance='low'))
    view.store.complete(job_id);job=view.store.get(job_id)
    output=view.artifact_path(job_id,'pdf')
    assert output.name=='Meeting notes_merge.pdf' and 'Merge PDFs' in view.operation_caption(job)
    with pymupdf.open(output) as pdf:
        assert len(pdf)==2 and 'MEETING FIRST' in pdf[0].get_text() and 'Hello world' in pdf[1].get_text()
    assert all(hashlib.sha256(p.read_bytes()).digest()==digest for p,digest in before.items())
    dialog.deleteLater()
