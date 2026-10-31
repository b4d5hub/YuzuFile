"""Real controller workflows through the nonrectangular desktop shell."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
import pytest
from PySide6.QtCore import Qt,QPoint,QPointF,QRect,QMimeData,QUrl
from PySide6.QtGui import QDragEnterEvent,QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QFileDialog,QMessageBox,QPushButton
from yuzufile.ui import Window
from yuzufile.shaped_shell import FloatingShell


@pytest.fixture
def shell(store,monkeypatch):
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr('yuzufile.ui.installed_languages',lambda:['eng','fra','ara'])
    controller=Window(store);controller.timer.stop()
    result=FloatingShell(controller)
    result.show();result.activateWindow();app.processEvents()
    yield result
    result.shutdown();controller.timer.stop()
    if not store.lock.closed:controller.supervisor.shutdown()
    result.hide();controller.hide();result.deleteLater();controller.deleteLater();app.processEvents()


def only(controller,operation):
    for code,button in controller.operations.items():button.setChecked(code==operation)


def test_actual_window_shape_leaves_corners_clear_and_controls_clickable(shell):
    assert shell.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert shell.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert not shell.mask().isEmpty()
    for point in (QPoint(0,0),QPoint(shell.width()-1,0),QPoint(0,shell.height()-1)):
        assert not shell.mask().contains(point)
    controller=shell.controller
    center=controller.upload.mapTo(shell,controller.upload.rect().center())
    assert shell.mask().contains(center)
    for button in controller.tool_wheel.buttons:
        point=button.mapTo(shell,button.hit_point.toPoint())
        assert shell.mask().contains(point)
    for button in (shell.files_button,shell.minimize_button,shell.close_button):
        assert shell.mask().contains(button.mapTo(shell,button.rect().center()))
    # The attached grip overlaps the circular body; this must remain a union,
    # otherwise an odd/even shape path creates an invisible input hole here.
    assert shell.mask().contains(shell.grip.mapTo(shell,QPoint(shell.grip.width()//2,5)))


def test_clicking_real_tool_opens_options_and_escape_returns_to_wheel(shell,digital_pdf):
    controller=shell.controller
    only(controller,'ocr');controller.add_files([str(digital_pdf)])
    compress=controller.operations['compress']
    QTest.mouseClick(compress,Qt.MouseButton.LeftButton,pos=compress.hit_point.toPoint())
    QApplication.processEvents()
    assert controller.selected_operations()=={'compress'}
    assert shell.mode=='tray' and shell.tray.isVisible()
    assert shell.isAncestorOf(controller.options_panel) and not controller.language_row.isVisible()
    assert not shell.wheel.isVisible() and shell.task_header.isVisible()
    assert shell.isAncestorOf(controller.workspace.dock)
    assert controller.start_button.isVisible() and controller.output_choose.isVisible()
    assert shell.mask().contains(controller.start_button.mapTo(shell,controller.start_button.rect().center()))
    shell.setFocus();QTest.keyClick(shell,Qt.Key.Key_Escape);QApplication.processEvents()
    assert shell.mode=='wheel' and not shell.tray.isVisible()
    assert controller.pending==[digital_pdf] and controller.selected_operations()=={'compress'}


def test_drop_adds_pdfs_once_and_rejects_other_files(shell,digital_pdf,tmp_path):
    text=tmp_path/'notes.txt';text.write_text('not a PDF')
    mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(digital_pdf)),QUrl.fromLocalFile(str(text))])
    center=shell.controller.upload.mapTo(shell,shell.controller.upload.rect().center())
    enter=QDragEnterEvent(center,Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(shell,enter);assert enter.isAccepted()
    drop=QDropEvent(QPointF(center),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(shell,drop);assert drop.isAccepted()
    assert shell.controller.pending==[digital_pdf] and shell.mode=='tray'
    shell.controller.add_files([str(digital_pdf)]);assert shell.controller.pending==[digital_pdf]
    other=QMimeData();other.setUrls([QUrl.fromLocalFile(str(text))])
    enter=QDragEnterEvent(QPoint(10,10),Qt.DropAction.CopyAction,other,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(shell,enter);assert not enter.isAccepted()


def test_folder_performance_and_start_keep_real_conversion_settings(shell,digital_pdf,tmp_path,monkeypatch):
    controller=shell.controller;only(controller,'compress');controller.add_files([str(digital_pdf)])
    shell.show_tray();QApplication.processEvents()
    destination=tmp_path/'exports';destination.mkdir()
    monkeypatch.setattr(QFileDialog,'getExistingDirectory',lambda *args:str(destination))
    controller.output_choose.click()
    controller.compression.setCurrentIndex(controller.compression.findData('maximum'))
    controller.performance.setCurrentIndex(controller.performance.findData('low'))
    assert shell.output_directory==destination
    assert controller.start_button.isVisible() and controller.start_button.isEnabled()
    QTest.mouseClick(controller.start_button,Qt.MouseButton.LeftButton);QApplication.processEvents()
    job=controller.store.jobs()[0]
    assert job['mode']=='compress' and job['compression']=='maximum'
    assert job['performance']=='low' and job['output_directory']==str(destination)
    assert json.loads(job['languages'])==[] and controller.pending==[]
    assert shell.mode=='progress' and shell.cancel_button.isVisible()
    shell.cancel_button.click();shell.sync_from_controller();QApplication.processEvents()
    assert controller.store.get(job['id'])['state']=='cancelled'
    assert shell.mode=='progress' and not shell.progress_row.isVisible()
    assert 'cancelled' in shell.pill_title.text().lower()
    retry=next(b for b in shell.result_actions.findChildren(QPushButton) if b.text()=='Process again')
    retry.click();shell.sync_from_controller();QApplication.processEvents()
    assert shell.mode=='tray' and controller.pending==[digital_pdf]
    assert controller.compression.currentData()=='maximum' and controller.performance.currentData()=='low'


def test_close_cancel_preserves_active_job_and_library(shell,digital_pdf,monkeypatch):
    controller=shell.controller
    job=controller.store.create(digital_pdf,'compress',[]);controller.session_jobs.append(job)
    shell.sync_from_controller()
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.No)
    assert not shell.close()
    assert shell.isVisible() and not shell.closing and not shell._closed
    assert controller.store.get(job)['state']=='queued' and not controller.store.lock.closed
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.Yes)
    assert shell.close()
    assert not shell.timer.isActive() and controller.store.lock.closed


def test_mixed_batch_keeps_failure_visible_and_retry_targets_the_failed_file(shell,digital_pdf):
    controller=shell.controller;store=controller.store
    failed=store.create(digital_pdf,'compress',[])
    store.update(failed,'failed','Failed','The PDF could not be decoded')
    completed=store.create(digital_pdf,'compress',[])
    result=store.job_dir(completed)/'result';result.mkdir(parents=True)
    (result/'document.pdf').write_bytes(digital_pdf.read_bytes())
    (result/'manifest.json').write_text(json.dumps({'artifacts':[{'path':'result/document.pdf','kind':'pdf'}],'metadata':{}}))
    store.complete(completed);controller.session_jobs.extend([failed,completed])
    shell.sync_from_controller();QApplication.processEvents()
    assert shell.mode=='progress'
    title=shell.pill_title.text().lower()
    assert 'completed' in title and ('failed' in title or 'attention' in title)
    assert shell._job_id==failed
    assert 'could not be decoded' in shell.pill_caption.toolTip()
    retry=next(b for b in shell.result_actions.findChildren(QPushButton) if b.text()=='Process again')
    retry.click();shell.sync_from_controller()
    assert shell.mode=='tray' and controller.pending==[digital_pdf]
    assert store.get(completed)['state']=='succeeded'


@pytest.mark.parametrize('size',[(580,520),(1100,800),(720,460)])
def test_all_options_keep_start_and_window_inside_small_work_area(shell,digital_pdf,monkeypatch,size):
    controller=shell.controller
    for code,operation in controller.operations.items():operation.setChecked(code!='remove_ocr')
    controller.add_files([str(digital_pdf)])
    area=QRect(100,50,*size)
    monkeypatch.setattr(shell,'_available',lambda:area)
    shell._anchor=area.center();shell.show_tray();QApplication.processEvents()
    assert area.contains(shell.geometry())
    assert controller.start_button.isVisible()
    start=controller.start_button.mapTo(shell,controller.start_button.rect().center())
    assert shell.rect().contains(start) and shell.mask().contains(start)
    assert shell.form_scroll.horizontalScrollBar().maximum()==0
    assert controller.options_panel.minimumSizeHint().width()<=shell.form_scroll.viewport().width()
    for control in (controller.cleanup_preview,controller.split_direction,controller.split_parts,
                    *controller.languages.values(),*controller.compression_segments.buttons):
        left=control.mapTo(shell.form,QPoint()).x()
        assert left>=0 and left+control.width()<=shell.form.width()+1
    shell.show_wheel();QApplication.processEvents();assert area.contains(shell.geometry())




def test_wheel_context_button_returns_to_processing_and_terminal_results(shell,digital_pdf):
    controller=shell.controller
    job=controller.store.create(digital_pdf,'compress',[])
    controller.session_jobs.append(job);shell.sync_from_controller()
    shell.show_wheel();QApplication.processEvents()
    assert shell.mode=='wheel' and shell.files_button.isVisible()
    assert shell.files_button.accessibleName()=='Show processing'
    shell.files_button.click();QApplication.processEvents()
    assert shell.mode=='progress' and shell.pill.isVisible() and shell.cancel_button.isVisible()
    controller.cancel_job(job);shell.sync_from_controller()
    shell.show_wheel();QApplication.processEvents()
    assert shell.files_button.accessibleName()=='Show results'
    shell.files_button.click();QApplication.processEvents()
    assert shell.mode=='progress' and shell.result_actions.isVisible()
    assert 'cancelled' in shell.pill_title.text()
    controller.clear_finished();shell.sync_from_controller();QApplication.processEvents()
    assert shell.files_button.accessibleName()=='Added PDFs and options'
    shell.files_button.click();assert shell.mode=='tray'


def complete_with_outputs(controller,job,source,kinds=('pdf',),metadata=None):
    result=controller.store.job_dir(job)/'result';result.mkdir(parents=True)
    files={'pdf':'document.pdf','docx':'document.docx','markdown':'document.md'}
    artifacts=[]
    for kind in kinds:
        name=files[kind];(result/name).write_bytes(source.read_bytes())
        artifacts.append({'path':'result/'+name,'kind':kind})
    (result/'manifest.json').write_text(json.dumps({'artifacts':artifacts,'metadata':metadata or {}}))
    controller.store.complete(job)


def test_success_has_visible_back_to_tools_and_can_start_a_new_batch(shell,digital_pdf,tmp_path):
    controller=shell.controller;only(controller,'compress')
    job=controller.store.create(digital_pdf,'compress',[]);controller.session_jobs.append(job)
    shell.sync_from_controller();QApplication.processEvents()
    assert shell.pill_tools.text()=='Back to tools' and shell.pill_tools.isVisible()
    complete_with_outputs(controller,job,digital_pdf)
    shell.sync_from_controller();QApplication.processEvents()
    assert shell.result_actions.isVisible() and shell.pill_tools.isVisible()
    assert next(button for button in shell._result_buttons if button.text()=='Open PDF').objectName()=='primary'
    assert shell.mask().contains(shell.pill_tools.mapTo(shell,shell.pill_tools.rect().center()))
    QTest.mouseClick(shell.pill_tools,Qt.MouseButton.LeftButton);QApplication.processEvents()
    assert shell.mode=='wheel' and shell.wheel.isVisible()
    assert controller.store.get(job)['state']=='succeeded'
    second=tmp_path/'Next document.pdf';second.write_bytes(digital_pdf.read_bytes())
    controller.add_files([str(second)]);shell.show_tray()
    controller.performance.setCurrentIndex(controller.performance.findData('low'))
    controller.start_button.click();shell.sync_from_controller();QApplication.processEvents()
    assert len(controller.session_jobs)==2 and shell.mode=='progress'
    next_job=controller.store.get(controller.session_jobs[-1])
    assert next_job['performance']=='low' and next_job['source']==str(second)
    assert controller.store.get(job)['state']=='succeeded'


def test_dragged_processing_window_stays_put_through_updates_and_completion(shell,digital_pdf,monkeypatch):
    area=QRect(0,0,1920,1080);monkeypatch.setattr(shell,'_available',lambda:area)
    controller=shell.controller
    job=controller.store.create(digital_pdf,'compress',[]);controller.session_jobs.append(job)
    shell.sync_from_controller();QApplication.processEvents()
    shell.move(700,250);QApplication.processEvents()
    # Exercise the same title drag surface used by the native system move;
    # the fallback path is deterministic in the offscreen Qt test platform.
    monkeypatch.setattr(shell,'windowHandle',lambda:None)
    point=QPoint(20,shell.pill_title.height()//2)
    original=QPoint(shell.pos())
    QTest.mousePress(shell.pill_title,Qt.MouseButton.LeftButton,pos=point)
    QTest.mouseMove(shell.pill_title,point+QPoint(40,20))
    QTest.mouseRelease(shell.pill_title,Qt.MouseButton.LeftButton,pos=point+QPoint(40,20))
    QApplication.processEvents();moved=QPoint(shell.pos())
    assert moved!=original
    controller.store.update(job,'running','Compressing page 1')
    shell.sync_from_controller();QApplication.processEvents();assert shell.pos()==moved
    complete_with_outputs(controller,job,digital_pdf,metadata={
        'compression':{},'input_bytes':10000,'output_bytes':6000,'saved_percent':40})
    shell.sync_from_controller();QApplication.processEvents()
    assert shell.pos()==moved and shell.pill_savings.isVisible()
    centre=shell.geometry().center()
    shell.pill_tools.click();QApplication.processEvents()
    wheel_centre=shell.wheel.mapToGlobal(shell.wheel.rect().center())
    assert (wheel_centre-centre).manhattanLength()<=2


@pytest.mark.parametrize('width',[360,580])
def test_all_result_formats_and_back_action_fit_small_capsules(shell,digital_pdf,monkeypatch,width):
    area=QRect(0,0,width,620);monkeypatch.setattr(shell,'_available',lambda:area)
    shell._anchor=area.center();controller=shell.controller
    job=controller.store.create(digital_pdf,'all_word',['eng']);controller.session_jobs.append(job)
    complete_with_outputs(controller,job,digital_pdf,('pdf','docx','markdown'))
    shell.sync_from_controller();QApplication.processEvents()
    assert area.contains(shell.geometry())
    controls=[*shell.result_actions.findChildren(QPushButton),shell.pill_tools]
    assert {'Open PDF','Open Word','Open Markdown','Open Folder','Back to tools'}<={button.text() for button in controls}
    rectangles=[]
    for button in controls:
        assert button.isVisible()
        assert button.height()>=32
        rect=QRect(button.mapTo(shell,QPoint()),button.size())
        assert shell.rect().contains(rect)
        assert shell.mask().contains(rect.center())
        assert all(not rect.intersects(other) for other in rectangles)
        rectangles.append(rect)
    more=next(button for button in controls if button.accessibleName()=='Result details and actions')
    assert abs(more.mapTo(shell.result_actions,more.rect().topRight()).x()-shell.result_actions.rect().right())<=2
