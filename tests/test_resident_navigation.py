"""The tray utility exposes focused tasks without a permanent wheel window."""
import hashlib
import json
import os
from copy import deepcopy
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

import pytest
from PySide6.QtCore import QEvent,QObject,QPoint,Qt,QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QDialog,QMenu,QPushButton

from yuzufile import system_tray
from yuzufile.desktop_drag import DesktopDragController,PointerState
from yuzufile.organize import inspect_source
from yuzufile.shaped_shell import FloatingShell
from yuzufile.tool_window import ToolDialog
from yuzufile.ui import Window
from test_desktop_lifecycle import FakeTray


@pytest.fixture
def resident(store,monkeypatch):
    app=QApplication.instance() or QApplication([])
    previous=app.quitOnLastWindowClosed()
    monkeypatch.setattr('yuzufile.ui.installed_languages',lambda:['eng','fra','ara'])
    monkeypatch.setattr(system_tray,'QSystemTrayIcon',FakeTray)
    FakeTray.available=True
    view=Window(store);view.timer.stop()
    shell=FloatingShell(view);shell.timer.stop()
    tray=system_tray.TrayController(app,view,shell);shell.tray_controller=tray
    assert tray.start()
    app.processEvents()
    yield SimpleNamespace(app=app,view=view,shell=shell,tray=tray)
    for menu in shell.findChildren(QMenu):menu.close()
    tray.shutdown();shell.shutdown();view.timer.stop()
    if not store.lock.closed:view.supervisor.shutdown()
    shell.hide();view.hide();tray.deleteLater();shell.deleteLater();view.deleteLater()
    app.setQuitOnLastWindowClosed(previous);app.processEvents()


def chooser(d,paths=None):
    result=d.shell.choose_tool_menu(position=QPoint(250,200),paths=paths)
    d.app.processEvents()
    if isinstance(result,QMenu):return result
    matches=[menu for menu in d.shell.findChildren(QMenu) if menu.isVisible()
             and any(action.data()=='compress' for action in menu.actions())]
    assert len(matches)==1,'The manual entry must open one compact tool menu'
    return matches[0]


def test_resident_starts_idle_without_a_movable_launcher(resident):
    d=resident
    assert d.shell.resident and d.shell.mode=='idle'
    assert not d.shell.isVisible() and not d.shell.wheel.isVisible() and not d.shell.grip.isVisible()
    assert d.shell.show_current() is False
    assert not d.shell.isVisible() and not d.view.store.lock.closed


def test_choosing_one_tool_opens_only_its_focused_task(resident,digital_pdf):
    d=resident
    original=hashlib.sha256(digital_pdf.read_bytes()).digest()
    d.shell.open_tool('compress',paths=[str(digital_pdf)],anchor=QPoint(500,350))
    d.app.processEvents()
    assert d.view.selected_operations()=={'compress'} and d.view.pending==[digital_pdf]
    assert d.shell.isVisible() and d.shell.mode=='tray' and d.shell.tray.isVisible()
    assert not d.shell.wheel.isVisible() and not d.shell.grip.isVisible()
    assert d.shell.tray_title.text()=='Compress PDF'
    assert not d.view.store.jobs()
    assert hashlib.sha256(digital_pdf.read_bytes()).digest()==original


@pytest.mark.parametrize('action',['close','escape','old-home-route'])
def test_leaving_a_draft_hides_it_and_retains_the_files(resident,digital_pdf,action):
    d=resident;d.shell.open_tool('compress',paths=[digital_pdf]);d.app.processEvents()
    if action=='close':d.shell.collapse_button.click()
    elif action=='escape':
        d.shell.activateWindow();d.shell.setFocus();QTest.keyClick(d.shell,Qt.Key.Key_Escape)
    else:d.shell.show_wheel()
    d.app.processEvents()
    assert not d.shell.isVisible() and not d.shell.wheel.isVisible()
    assert d.view.pending==[digital_pdf] and not d.view.store.lock.closed
    assert d.shell.show_current() is True
    assert d.shell.isVisible() and d.shell.mode=='tray' and d.view.pending==[digital_pdf]
    assert not d.shell.wheel.isVisible()




def test_manual_chooser_cancellation_keeps_the_previous_batch_unchanged(resident,digital_pdf,scanned_pdf):
    d=resident;d.view.add_files([digital_pdf])
    before=set(d.view.selected_operations())
    menu=chooser(d,paths=[scanned_pdf])
    assert {a.data() for a in menu.actions() if a.data()}==set(d.view.operations)|{'merge','arrange'}
    assert not d.shell.isVisible() and not d.shell.wheel.isVisible()
    menu.close();d.app.processEvents()
    assert d.view.pending==[digital_pdf] and d.view.selected_operations()==before
    assert not d.shell.isVisible() and not d.view.store.jobs()


def test_manual_chooser_selection_preserves_batch_and_selects_one_operation(resident,digital_pdf,scanned_pdf):
    d=resident;d.view.add_files([digital_pdf])
    menu=chooser(d,paths=[scanned_pdf])
    next(action for action in menu.actions() if action.data()=='docx').trigger()
    menu.close();d.app.processEvents()
    assert d.view.pending==[digital_pdf,scanned_pdf]
    assert d.view.selected_operations()=={'docx'}
    assert d.shell.isVisible() and d.shell.mode=='tray' and not d.shell.wheel.isVisible()
    assert not d.view.store.jobs()


@pytest.mark.parametrize('code,method',[('merge','merge_pdfs'),('arrange','organize_pages')])
def test_manual_page_tool_dispatches_with_files_without_showing_a_launcher(resident,digital_pdf,monkeypatch,code,method):
    d=resident;calls=[]
    monkeypatch.setattr(d.view,method,lambda:calls.append((list(d.view.pending),d.shell.wheel.isVisible())))
    menu=chooser(d,paths=[digital_pdf])
    next(action for action in menu.actions() if action.data()==code).trigger()
    menu.close();d.app.processEvents()
    assert calls==[([digital_pdf],False)]
    assert not d.view.store.jobs() and not d.shell.wheel.isVisible()


def test_closing_an_editor_returns_to_its_task_without_a_launcher(resident,digital_pdf):
    d=resident;d.shell.open_tool('cleanup',paths=[digital_pdf]);d.app.processEvents()
    dialog=ToolDialog(d.shell,title='Visual edits');seen=[]
    def reject():
        seen.append((d.shell.isVisible(),dialog.isVisible(),d.shell.wheel.isVisible()))
        dialog.reject()
    QTimer.singleShot(0,dialog,reject)
    try:
        assert d.view.exec_tool(dialog)==QDialog.DialogCode.Rejected
        assert seen==[(False,True,False)]
        assert d.shell.isVisible() and d.shell.mode=='tray'
        assert not d.shell.wheel.isVisible() and d.view.pending==[digital_pdf]
    finally:dialog.hide();dialog.deleteLater()


def test_hidden_completion_stays_in_background_until_results_are_requested(resident,digital_pdf):
    d=resident;d.shell.open_tool('compress',paths=[digital_pdf]);d.app.processEvents()
    assert d.view.start_button.isEnabled()
    d.view.start_button.click();d.app.processEvents()
    jobs=d.view.store.jobs();assert len(jobs)==1
    job=jobs[0]['id']
    assert d.shell.mode=='progress' and d.shell.isVisible()
    assert d.shell.pill_tools.text()=='Hide'
    d.shell.pill_tools.click();d.app.processEvents()
    assert not d.shell.isVisible() and not d.view.store.lock.closed
    folder=d.view.store.job_dir(job)/'result';folder.mkdir(parents=True)
    output=folder/'document_compress.pdf';output.write_bytes(digital_pdf.read_bytes())
    (folder/'manifest.json').write_text(json.dumps({'artifacts':[{'path':'result/'+output.name,'kind':'pdf'}],'metadata':{}}))
    d.view.store.complete(job);d.shell.sync_from_controller();d.app.processEvents()
    assert not d.shell.isVisible() and not d.shell.wheel.isVisible()
    assert d.shell.show_current() is True
    assert d.shell.mode=='progress' and d.shell.isVisible()
    assert d.shell.pill_tools.text()=='Done'
    assert any(button.text()=='Open PDF' for button in d.shell.result_actions.findChildren(QPushButton))
    d.shell.pill_tools.click();d.app.processEvents()
    assert not d.shell.isVisible() and not d.shell.wheel.isVisible()
    assert d.view.store.get(job)['state']=='succeeded' and output.is_file()


def test_without_a_system_tray_the_visible_fallback_wheel_remains_usable(resident):
    d=resident;d.tray.shutdown()
    d.shell.show_wheel();d.shell.show();d.app.processEvents()
    assert not d.shell.resident and d.shell.mode=='wheel'
    assert d.shell.wheel.isVisible() and d.shell.grip.isVisible()


@pytest.fixture
def drag(resident):
    d=resident
    monitor=DesktopDragController(d.app,d.view,d.shell,
        read_state=lambda:PointerState(False,False,False,(300,250)))
    yield monitor
    monitor.shutdown();monitor.overlay.deleteLater();monitor.deleteLater()


class ShowObserver(QObject):
    """Capture the first visible frame's mode, not just its eventual state."""
    def __init__(self,shell):
        super().__init__();self.shell=shell;self.seen=[]
    def eventFilter(self,watched,event):
        if watched is self.shell and event.type()==QEvent.Type.Show:
            self.seen.append((self.shell.mode,self.shell.wheel.isVisible(),self.shell.grip.isVisible()))
        return False


def test_resident_drag_conversion_opens_the_task_without_a_wheel_flash(resident,drag,digital_pdf):
    d=resident;observer=ShowObserver(d.shell);d.shell.installEventFilter(observer)
    drag.open_drop([str(digital_pdf)],'compress',QPoint(550,350));d.app.processEvents()
    assert observer.seen and all(mode=='tray' and not wheel and not grip for mode,wheel,grip in observer.seen)
    assert d.shell.isVisible() and d.shell.mode=='tray'
    assert d.view.pending==[digital_pdf] and d.view.selected_operations()=={'compress'}
    assert not d.shell.wheel.isVisible() and not d.view.store.jobs()
    d.shell.removeEventFilter(observer)


def test_resident_drag_centre_stages_files_until_a_tool_is_selected(resident,drag,digital_pdf,scanned_pdf):
    d=resident;d.view.add_files([digital_pdf])
    drag.open_drop([str(scanned_pdf)],'',QPoint(450,300));d.app.processEvents()
    menu=d.shell.tool_chooser
    assert menu.isVisible() and not d.shell.isVisible() and not d.shell.wheel.isVisible()
    assert d.view.pending==[digital_pdf]
    next(action for action in menu.actions() if action.data()=='markdown').trigger()
    menu.close();d.app.processEvents()
    assert d.view.pending==[digital_pdf,scanned_pdf]
    assert d.view.selected_operations()=={'markdown'} and d.shell.isVisible() and d.shell.mode=='tray'
    assert not d.shell.wheel.isVisible() and not d.view.store.jobs()


def test_history_process_again_from_idle_opens_the_saved_conversion_task(resident,digital_pdf,tmp_path):
    d=resident;destination=tmp_path/'exports';destination.mkdir()
    job=d.view.store.create(digital_pdf,'compress',[],compression='maximum',performance='low',output_directory=destination)
    d.view.store.update(job,'failed','Failed','Fixture')
    d.app.processEvents()
    assert d.shell.mode=='idle' and not d.shell.isVisible()
    observer=ShowObserver(d.shell);d.shell.installEventFilter(observer)
    d.view.retry_job(job);d.app.processEvents()
    assert d.shell.isVisible() and d.shell.mode=='tray'
    assert observer.seen and all(mode=='tray' and not wheel and not grip for mode,wheel,grip in observer.seen)
    assert d.view.pending==[digital_pdf] and d.view.selected_operations()=={'compress'}
    assert d.view.output_directory==destination
    assert d.view.performance.currentData()=='low' and d.view.compression.currentData()=='maximum'
    assert d.view.start_button.isVisible() and d.view.start_button.isEnabled()
    assert len(d.view.store.jobs())==1  # Retry opens review instead of starting work.
    d.shell.removeEventFilter(observer)


def page_plan(first,second,kind):
    sources=[inspect_source(first),inspect_source(second)]
    pages=[{'source':0,'page':0,'rotation':0},{'source':1,'page':0,'rotation':0}]
    if kind=='arrange':pages=[{'source':1,'page':0,'rotation':90},{'source':0,'page':0,'rotation':0}]
    return {'version':1,'sources':sources,'pages':pages,**({'action':'merge'} if kind=='merge' else {})}


@pytest.mark.parametrize('kind,method',[('merge','merge_pdfs'),('arrange','organize_pages')])
def test_history_page_retry_preserves_original_plan_when_cancelled_and_resumed(resident,digital_pdf,scanned_pdf,monkeypatch,kind,method):
    d=resident;plan=page_plan(digital_pdf,scanned_pdf,kind)
    job=d.view.store.create(digital_pdf,'organize',[],page_plan=plan)
    plan=json.loads(d.view.store.get(job)['page_plan'])
    d.view.store.update(job,'failed','Failed','Fixture')
    calls=[]
    def cancelled(plan=None):calls.append(deepcopy(plan))
    monkeypatch.setattr(d.view,method,cancelled)
    d.view.retry_job(job);d.app.processEvents()
    assert calls==[plan]
    assert not d.shell.isVisible() and not d.shell.wheel.isVisible()
    assert d.view.pending==[] and len(d.view.store.jobs())==1
    # History loads its files through the plan, so a cancelled retry can have
    # an empty pending batch and must still retain a resumable editor.
    assert d.shell.show_current() is True
    assert calls==[plan,plan] and not d.shell.isVisible() and not d.shell.wheel.isVisible()
    assert len(d.view.store.jobs())==1


@pytest.mark.parametrize('kind,method',[('merge','merge_pdfs'),('arrange','organize_pages')])
def test_accepting_a_history_page_retry_shows_queued_progress_with_the_saved_plan(resident,digital_pdf,scanned_pdf,tmp_path,monkeypatch,kind,method):
    d=resident;plan=page_plan(digital_pdf,scanned_pdf,kind)
    destination=tmp_path/'exports';destination.mkdir()
    job=d.view.store.create(digital_pdf,'organize',[],performance='low',output_directory=destination,page_plan=plan)
    plan=json.loads(d.view.store.get(job)['page_plan'])
    d.view.store.update(job,'failed','Failed','Fixture')
    accepted=[]
    def accept(plan=None):
        accepted.append(deepcopy(plan));d.view.enqueue_organization(deepcopy(plan))
    monkeypatch.setattr(d.view,method,accept)
    d.view.retry_job(job);d.app.processEvents()
    assert accepted==[plan]
    assert d.shell.isVisible() and d.shell.mode=='progress' and not d.shell.wheel.isVisible()
    retry=next(item for item in d.view.store.jobs() if item['id']!=job)
    assert retry['state']=='queued' and json.loads(retry['page_plan'])==plan
    assert retry['performance']=='low' and retry['output_directory']==str(destination)
    assert d.shell._resume_editor is None and d.shell._resume_plan is None


@pytest.mark.parametrize('kind',['merge','arrange'])
def test_cancelling_a_direct_page_editor_returns_to_background(resident,digital_pdf,kind):
    d=resident;seen=[]
    def reject_editor():
        dialog=d.app.activeModalWidget()
        assert dialog is not None
        seen.append((dialog.windowTitle(),d.shell.isVisible(),d.shell.wheel.isVisible()))
        dialog.reject()
    QTimer.singleShot(0,d.app,reject_editor)
    d.shell.open_tool(kind,paths=[digital_pdf]);d.app.processEvents()
    assert len(seen)==1 and seen[0][1:]==(False,False)
    assert not d.shell.isVisible() and not d.shell.wheel.isVisible()
    assert d.view.pending==[digital_pdf] and not d.view.store.jobs()
