"""Tray residency must not stop conversions or strand a hidden window."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from types import SimpleNamespace
import pytest
from PySide6.QtCore import QObject,QPoint,Signal
from PySide6.QtGui import QIcon,QPixmap,QColor
from PySide6.QtWidgets import QApplication,QWidget,QSystemTrayIcon
from yuzufile import system_tray


class FakeTray(QObject):
    activated=Signal(object)
    ActivationReason=QSystemTrayIcon.ActivationReason
    available=True
    @staticmethod
    def isSystemTrayAvailable():return FakeTray.available
    def __init__(self,icon,parent):
        super().__init__(parent);self.icon=icon;self.visible=False;self.tooltip='';self.menu=None
    def setToolTip(self,text):self.tooltip=text
    def setContextMenu(self,menu):self.menu=menu
    def show(self):self.visible=True
    def hide(self):self.visible=False


class FakeApp(QObject):
    aboutToQuit=Signal()
    def __init__(self,previous=True):
        super().__init__();self.quit_flag=previous;self.quit_calls=0;self.modal=None
    def quitOnLastWindowClosed(self):return self.quit_flag
    def setQuitOnLastWindowClosed(self,value):self.quit_flag=value
    def activeModalWidget(self):return self.modal
    def quit(self):self.quit_calls+=1


class FakeShell(QWidget):
    def __init__(self):
        super().__init__();self.synced=0;self.quit_requests=0;self.accept_quit=False
        self.mode='idle';self.has_current=False;self.has_draft=False;self.choices=[];self.resident_entries=0;self.progress_calls=0
        pixmap=QPixmap(24,24);pixmap.fill(QColor('#3388cc'));self.setWindowIcon(QIcon(pixmap))
    def sync_from_controller(self):self.synced+=1
    def enter_resident_mode(self):self.resident_entries+=1;self.mode='idle';self.hide()
    def choose_tool_menu(self,position=None,paths=None):self.choices.append((position,paths))
    def show_current(self):
        self.synced+=1
        if not self.has_current:return False
        self.showNormal();self.raise_();self.activateWindow();return True
    def show_progress(self):self.progress_calls+=1;self.mode='progress';self.has_current=True
    def request_quit(self):self.quit_requests+=1;return self.accept_quit


@pytest.fixture
def tray(monkeypatch):
    qt=QApplication.instance() or QApplication([])
    monkeypatch.setattr(system_tray,'QSystemTrayIcon',FakeTray);FakeTray.available=True
    app=FakeApp();shell=FakeShell();history=QWidget()
    view=SimpleNamespace(history_dialog=history,history_calls=0,session_jobs=[],jobs=[],artifacts={},opened=[])
    view.store=SimpleNamespace(jobs=lambda:list(view.jobs))
    view.artifact_path=lambda job,kind:view.artifacts.get((job,kind))
    view.open_path=view.opened.append
    def history_show():view.history_calls+=1;shell.hide();history.show()
    view.show_history=history_show
    controller=system_tray.TrayController(app,view,shell)
    yield controller,app,shell,history,view
    controller.shutdown();history.hide();shell.hide();history.deleteLater();shell.deleteLater();controller.deleteLater();qt.processEvents()


def test_available_tray_retains_app_and_exposes_only_resident_actions(tray):
    controller,app,shell,history,view=tray
    assert controller.available and controller.start() and controller.active
    assert controller.icon.visible and not app.quit_flag and not shell.isVisible()
    assert [a.text() for a in controller.menu.actions() if a.isVisible() and not a.isSeparator()]==[
        'Process PDFs…','Processing && results',
        'Enable drag + Shift','Quit YuzuFile']
    assert controller.gesture_enabled and 'Shift' in controller.icon.tooltip
    assert not controller.icon.icon.isNull()
    assert shell.resident_entries==1 and shell.mode=='idle'
    assert not controller.processing_action.isEnabled()
    assert not controller.resume_action.isVisible() and not controller.resume_action.isEnabled()
    controller.start();controller.shutdown();controller.shutdown()
    assert not controller.active and not controller.icon.visible and app.quit_flag


def test_unavailable_tray_preserves_regular_window_lifetime(tray):
    controller,app,shell,history,view=tray
    FakeTray.available=False
    assert not controller.start() and not controller.available and not controller.active
    shell.show();assert not controller.hide_window() and shell.isVisible()
    assert app.quit_flag and not controller.icon.visible


def test_click_and_double_click_open_menu_without_revealing_a_main_window(tray,monkeypatch):
    controller,app,shell,history,view=tray;controller.start();shown=[]
    monkeypatch.setattr(controller.menu,'popup',lambda position:shown.append(position))
    controller.icon.activated.emit(FakeTray.ActivationReason.Trigger)
    controller.icon.activated.emit(FakeTray.ActivationReason.DoubleClick)
    controller.icon.activated.emit(FakeTray.ActivationReason.Context)
    assert len(shown)==2 and not shell.isVisible() and not history.isVisible()
    assert not shell.choices and not app.quit_calls


def test_second_launch_restores_a_task_but_opens_only_menu_when_idle(tray,monkeypatch):
    controller,app,shell,history,view=tray;controller.start();shown=[]
    monkeypatch.setattr(controller.menu,'popup',lambda position:shown.append(position))
    controller.show_window()
    assert shown and not shell.isVisible()
    shell.has_current=True;shell.mode='tray';shell.show()
    assert controller.hide_window() and not shell.isVisible()
    controller.show_window()
    assert shell.isVisible() and shell.synced and not app.quit_calls and not shell.choices


def test_resume_task_is_exposed_only_for_a_preserved_draft(tray,monkeypatch):
    controller,app,shell,history,view=tray;controller.start()
    monkeypatch.setattr(system_tray.QFileDialog,'getOpenFileNames',lambda *args:pytest.fail('Resuming must not reopen the file picker'))
    assert not controller.resume_action.isVisible()
    shell.has_draft=True;shell.has_current=True;shell.mode='tray'
    controller.refresh_actions()
    assert controller.resume_action.isVisible() and controller.resume_action.isEnabled()
    controller.resume_action.trigger()
    assert shell.isVisible() and shell.mode=='tray' and not shell.choices and not app.quit_calls
    controller.hide_window();controller.refresh_actions()
    assert controller.resume_action.isVisible()
    shell.has_draft=False;controller.refresh_actions()
    assert not controller.resume_action.isVisible() and not controller.resume_action.isEnabled()




def test_cancelled_file_picker_does_not_reveal_wheel_or_replace_open_history(tray,monkeypatch):
    controller,app,shell,history,view=tray;controller.start()
    monkeypatch.setattr(system_tray.QFileDialog,'getOpenFileNames',lambda *args:([],''))
    controller.add_pdfs()
    assert not history.isVisible() and not shell.isVisible() and shell.choices==[]




def test_tray_actions_return_to_an_open_modal_editor(tray):
    controller,app,shell,history,view=tray;controller.start()
    modal=QWidget();modal.show();app.modal=modal
    try:
        controller.show_window();controller.add_pdfs();controller.show_processing()
        assert modal.isVisible() and not shell.isVisible() and not shell.choices and not view.history_calls
        assert not controller.hide_window() and modal.isVisible()
    finally:modal.hide();modal.deleteLater();app.modal=None


def test_disabling_gesture_emits_only_modifier_preference(tray):
    controller,app,shell,history,view=tray;changes=[]
    controller.gesture_enabled_changed.connect(changes.append)
    controller.gesture_action.trigger();controller.gesture_action.trigger()
    assert changes==[False,True] and controller.gesture_enabled
    assert not app.quit_calls and not shell.choices and not view.history_calls


def test_processing_entry_restores_existing_session_jobs_only(tray):
    controller,app,shell,history,view=tray;controller.start()
    controller.show_processing();assert shell.progress_calls==0 and not shell.isVisible()
    view.jobs=[{'id':'old','state':'succeeded'},{'id':'running','state':'running'}]
    controller.refresh_actions();assert not controller.processing_action.isEnabled()
    view.session_jobs=['running'];controller.refresh_actions()
    assert controller.processing_action.isEnabled()
    controller.processing_action.trigger()
    assert shell.isVisible() and shell.mode=='progress' and shell.progress_calls==1
    assert not history.isVisible() and not app.quit_calls






def test_cancelled_quit_leaves_residency_and_work_owner_untouched(tray):
    controller,app,shell,history,view=tray;controller.start();calls=[]
    controller.quitting.connect(lambda:calls.append('accepted'))
    assert not controller.quit_app()
    assert shell.quit_requests==1 and controller.active and controller.icon.visible
    assert not app.quit_calls and not app.quit_flag and not calls


@pytest.mark.parametrize('previous',[True,False])
def test_confirmed_quit_stops_tray_and_restores_previous_lifetime(tray,previous):
    controller,app,shell,history,view=tray;app.quit_flag=previous;controller.start()
    shell.accept_quit=True;calls=[];controller.quitting.connect(lambda:calls.append('accepted'))
    assert controller.quit_app() and app.quit_calls==1 and shell.quit_requests==1
    assert calls==['accepted'] and not controller.active and not controller.icon.visible
    assert app.quit_flag==previous and not controller.quit_app() and app.quit_calls==1


def test_external_quit_also_cleans_resident_icon(tray):
    controller,app,shell,history,view=tray;controller.start()
    app.aboutToQuit.emit()
    assert not controller.active and not controller.icon.visible and app.quit_flag
