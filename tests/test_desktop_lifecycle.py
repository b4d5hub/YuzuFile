"""Resident desktop lifetime with real yuzufile windows and backend ownership."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject,Signal
from PySide6.QtWidgets import QApplication,QMenu,QMessageBox,QSystemTrayIcon

from yuzufile import system_tray
from yuzufile.shaped_shell import FloatingShell
from yuzufile.ui import Window


class FakeTray(QObject):
    """Keep the native Windows notification area untouched by the tests."""
    activated=Signal(object)
    ActivationReason=QSystemTrayIcon.ActivationReason
    available=True

    @staticmethod
    def isSystemTrayAvailable():return FakeTray.available

    def __init__(self,icon,parent):
        super().__init__(parent)
        self.visible=False

    def setToolTip(self,text):self.tooltip=text
    def setContextMenu(self,menu):self.menu=menu
    def show(self):self.visible=True
    def hide(self):self.visible=False


@pytest.fixture
def desktop(store,monkeypatch):
    app=QApplication.instance() or QApplication([])
    previous=app.quitOnLastWindowClosed()
    monkeypatch.setattr('yuzufile.ui.installed_languages',lambda:['eng','fra','ara'])
    monkeypatch.setattr(system_tray,'QSystemTrayIcon',FakeTray)
    FakeTray.available=True
    view=Window(store)
    # Keep the real timers active but let tests drive polling deterministically.
    view.timer.setInterval(60_000)
    shell=FloatingShell(view)
    shell.timer.setInterval(60_000)
    tray=system_tray.TrayController(app,view,shell)
    shell.tray_controller=tray
    quit_calls=[]
    monkeypatch.setattr(app,'quit',lambda:quit_calls.append(True))
    assert tray.start()
    shell.open_tool('compress')
    app.processEvents()
    yield SimpleNamespace(app=app,view=view,shell=shell,tray=tray,quit_calls=quit_calls)
    tray.shutdown()
    view.timer.stop()
    shell.shutdown()
    if not store.lock.closed:view.supervisor.shutdown()
    shell.hide()
    view.hide()
    tray.deleteLater()
    shell.deleteLater()
    view.deleteLater()
    app.setQuitOnLastWindowClosed(previous)
    app.processEvents()


@pytest.mark.parametrize('action',['close','minimize'])
def test_resident_hide_preserves_queue_pending_files_and_backend_polling(desktop,digital_pdf,monkeypatch,action):
    d=desktop
    d.view.add_files([str(digital_pdf)])
    job=d.view.store.create(digital_pdf,'compress',[])
    d.view.session_jobs.append(job)
    started=[]
    monkeypatch.setattr(d.view.supervisor,'_start',lambda item:started.append(item['id']))
    monkeypatch.setattr(QMessageBox,'question',lambda *args:pytest.fail('Hiding must not ask to cancel conversions'))
    d.shell.sync_from_controller()
    assert d.shell.mode=='progress'
    if action=='close':assert not d.shell.close()
    else:d.shell.showMinimized()
    d.app.processEvents()
    assert not d.shell.isVisible() and d.tray.active and d.tray.icon.visible
    assert not d.shell._closed and not d.shell.closing and not d.view._closed
    assert d.view.timer.isActive() and d.shell.timer.isActive()
    assert d.view.pending==[digital_pdf] and not d.view.store.lock.closed
    assert d.view.store.get(job)['state']=='queued' and not d.quit_calls
    d.view.poll()
    assert started==[job] and d.view.store.get(job)['state']=='queued'
    d.tray.show_window()
    assert d.shell.isVisible() and not d.shell.isMinimized()


def test_hidden_real_controller_continues_receiving_worker_progress(desktop,digital_pdf):
    d=desktop
    job=d.view.store.create(digital_pdf,'compress',[])
    d.view.session_jobs.append(job)
    d.view.store.update(job,'running','Starting conversion')
    d.view.supervisor.active=job
    d.shell.sync_from_controller()
    assert d.tray.hide_window()
    d.view.supervisor.events.put({'version':1,'progress':67,'stage':'Compressing page 3'})
    d.view.poll()
    d.shell.sync_from_controller()
    assert not d.shell.isVisible() and not d.view.store.lock.closed
    assert d.view.supervisor.progress==67
    assert d.view.store.get(job)['stage']=='Compressing page 3'
    assert d.shell.progress.value()==67 and d.view.timer.isActive()
    d.tray.show_window()
    assert d.shell.isVisible() and d.shell.progress.value()==67


def test_cancelled_quit_preserves_jobs_then_confirmed_quit_closes_real_owners(desktop,digital_pdf,monkeypatch):
    d=desktop
    job=d.view.store.create(digital_pdf,'compress',[])
    d.view.session_jobs.append(job)
    d.shell.sync_from_controller()
    prompts=[]
    def reject(*args):
        prompts.append(args)
        return QMessageBox.StandardButton.No
    monkeypatch.setattr(QMessageBox,'question',reject)
    assert not d.tray.quit_app()
    assert len(prompts)==1 and not d.quit_calls
    assert d.tray.active and d.tray.icon.visible and not d.app.quitOnLastWindowClosed()
    assert d.shell.isVisible() and not d.shell.closing and not d.shell._closed
    assert not d.view._closed and not d.view.store.lock.closed
    assert d.view.timer.isActive() and d.shell.timer.isActive()
    assert d.view.store.get(job)['state']=='queued'
    cancelled=[]
    original=d.view.supervisor.cancel
    def cancel(job_id):
        cancelled.append(job_id)
        original(job_id)
    monkeypatch.setattr(d.view.supervisor,'cancel',cancel)
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.Yes)
    assert d.tray.quit_app()
    assert cancelled==[job] and d.quit_calls==[True]
    assert d.view._closed and d.shell._closed and d.view.store.lock.closed
    assert not d.view.timer.isActive() and not d.shell.timer.isActive()
    assert not d.tray.active and not d.tray.icon.visible and not d.shell.isVisible()
    assert not d.tray.quit_app() and d.quit_calls==[True]




@pytest.mark.parametrize('previous',[False,True])
def test_residency_restores_real_application_quit_preference(desktop,previous):
    d=desktop
    d.tray.shutdown()
    d.app.setQuitOnLastWindowClosed(previous)
    tray=system_tray.TrayController(d.app,d.view,d.shell)
    d.shell.tray_controller=tray
    try:
        assert tray.start() and not d.app.quitOnLastWindowClosed()
        tray.shutdown()
        assert d.app.quitOnLastWindowClosed()==previous
    finally:
        tray.shutdown()
        tray.deleteLater()


@pytest.mark.parametrize('available',[False,True])
def test_main_starts_hidden_only_when_native_tray_is_available(tmp_path,monkeypatch,available):
    from yuzufile import desktop_drag,desktop_instance,shaped_shell,ui
    app=QApplication.instance() or QApplication([])
    previous=app.quitOnLastWindowClosed()
    captured={}
    monkeypatch.setattr(ui,'installed_languages',lambda:['eng'])
    monkeypatch.setattr(system_tray,'QSystemTrayIcon',FakeTray)
    FakeTray.available=available
    original_shell=shaped_shell.FloatingShell
    original_tray=system_tray.TrayController

    def build_shell(view):
        captured['view']=view
        captured['shell']=original_shell(view)
        view.timer.setInterval(60_000)
        captured['shell'].timer.setInterval(60_000)
        return captured['shell']

    def build_tray(*args):
        captured['tray']=original_tray(*args)
        return captured['tray']

    class FakeInstance:
        def __init__(self,home):self.closed=False;captured['instance']=self
        def request_show(self,*args,**kwargs):return False
        def listen(self,callback):self.callback=callback;return True
        def shutdown(self):self.closed=True

    class FakeGesture:
        available=True
        def __init__(self,*args):self.started=0;self.closed=False;captured['gesture']=self
        def start(self):self.started+=1;return True
        def set_enabled(self,value):self.enabled=value
        def shutdown(self):self.closed=True

    def event_loop():
        tray=captured['tray']
        assert tray.active==available and tray.icon.visible==available
        assert captured['shell'].isVisible()==(not available)
        assert app.quitOnLastWindowClosed()==(False if available else previous)
        assert captured['gesture'].started==1
        assert captured['view'].timer.isActive()
        return 23

    monkeypatch.setattr(shaped_shell,'FloatingShell',build_shell)
    monkeypatch.setattr(system_tray,'TrayController',build_tray)
    monkeypatch.setattr(desktop_instance,'DesktopInstance',FakeInstance)
    monkeypatch.setattr(desktop_drag,'DesktopDragController',FakeGesture)
    monkeypatch.setattr(app,'exec',event_loop)
    monkeypatch.setattr(QMessageBox,'critical',lambda *args:pytest.fail(str(args)))
    try:
        assert ui.main(tmp_path/'startup-library')==23
        assert app.quitOnLastWindowClosed()==previous
        assert captured['instance'].closed and captured['gesture'].closed
        assert not captured['tray'].active and captured['view'].store.lock.closed
        assert not captured['view'].timer.isActive()
    finally:
        if 'shell' in captured:
            for menu in captured['shell'].findChildren(QMenu):menu.close()
            captured['shell'].shutdown()
            captured['shell'].hide()
            captured['shell'].deleteLater()
        if 'view' in captured:
            captured['view'].timer.stop()
            captured['view'].hide()
            captured['view'].deleteLater()
        if 'tray' in captured:
            captured['tray'].shutdown()
            captured['tray'].deleteLater()
        if 'instance' in captured:
            try:app.aboutToQuit.disconnect(captured['instance'].shutdown)
            except RuntimeError:pass
        app.setQuitOnLastWindowClosed(previous)
        app.processEvents()
