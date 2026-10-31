"""Resident yuzufile controls in the Windows notification area."""
from PySide6.QtCore import QObject,Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QFileDialog,QMenu,QSystemTrayIcon
from yuzufile.icons import icon


class TrayController(QObject):
    gesture_enabled_changed=Signal(bool)
    quitting=Signal()

    def __init__(self,app,view,shell):
        super().__init__(app)
        self.app,self.view,self.shell=app,view,shell
        self.available=bool(QSystemTrayIcon.isSystemTrayAvailable())
        self._active=False;self._closed=False;self._quitting=False
        self._previous_quit=None
        self.icon=QSystemTrayIcon(shell.windowIcon(),self)
        self.icon.setToolTip('YuzuFile\nDrop files. Get things done. (Drag + Shift)')
        self.menu=QMenu(shell)
        self.add_action=self.menu.addAction('Process PDFs…',self.add_pdfs)
        self.resume_action=self.menu.addAction('Resume task',self.resume_task)
        self.processing_action=self.menu.addAction('Processing && results',self.show_processing)
        self.menu.addSeparator()
        self.gesture_action=self.menu.addAction('Enable drag + Shift')
        self.gesture_action.setCheckable(True);self.gesture_action.setChecked(True)
        self.gesture_action.toggled.connect(self.gesture_enabled_changed.emit)
        self.menu.addSeparator()
        self.quit_action=self.menu.addAction('Quit YuzuFile',self.quit_app)
        for action,glyph in ((self.add_action,'file-plus'),(self.resume_action,'play'),
                             (self.processing_action,'files'),(self.quit_action,'x')):
            action.setIcon(icon(glyph,16))
        self.icon.setContextMenu(self.menu)
        self.menu.aboutToShow.connect(self.refresh_actions)
        self.icon.activated.connect(self._activated)
        self.app.aboutToQuit.connect(self.shutdown)
        self.refresh_actions()

    @property
    def active(self):return self._active

    @property
    def gesture_enabled(self):return self.gesture_action.isChecked()

    def start(self):
        if self._closed:return False
        self.available=bool(QSystemTrayIcon.isSystemTrayAvailable())
        if not self.available:return False
        if not self._active:
            self._previous_quit=self.app.quitOnLastWindowClosed()
            self.app.setQuitOnLastWindowClosed(False)
            self.icon.show();self._active=True
            if hasattr(self.shell,'enter_resident_mode'):self.shell.enter_resident_mode()
        return True

    def _activated(self,reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_menu()

    def show_menu(self,position=None):
        if self._closed:return
        if self.menu.isVisible():return
        self.refresh_actions()
        self.menu.popup(position or QCursor.pos())

    def _modal(self):
        modal=self.app.activeModalWidget()
        return modal if modal is not None and modal.isVisible() else None

    @staticmethod
    def _reveal(window):
        window.showNormal();window.raise_();window.activateWindow()

    def show_window(self,*_):
        if self._closed:return
        # A modal editor owns the interaction until it is accepted or cancelled.
        # Summoning another window behind it would make the tray feel unresponsive.
        modal=self._modal()
        if modal is not None:
            self._reveal(modal);return
        if self.shell.isVisible() and self.shell.show_current():
            return
        if not self.shell.show_current():self.show_menu()

    def hide_window(self,*_):
        if self._closed or not self._active:return False
        modal=self._modal()
        if modal is not None:
            self._reveal(modal);return False
        self.shell.hide()
        return True

    def resume_task(self,*_):
        if self._closed:return
        modal=self._modal()
        if modal is not None:
            self._reveal(modal);return
        self.shell.show_current()

    def add_pdfs(self,*_):
        if self._closed:return
        modal=self._modal()
        if modal is not None:
            self._reveal(modal);return
        paths,_=QFileDialog.getOpenFileNames(self.shell,'Choose PDFs','','PDF files (*.pdf)')
        if not paths:return
        self.shell.choose_tool_menu(paths=paths)

    def show_processing(self,*_):
        if self._closed:return
        modal=self._modal()
        if modal is not None:
            self._reveal(modal);return
        self.refresh_actions()
        if not self.processing_action.isEnabled():return
        self.shell.show_progress();self._reveal(self.shell)

    def refresh_actions(self):
        """Update the compact menu from existing jobs, without opening a page."""
        if self._closed:return
        draft=bool(getattr(self.shell,'has_draft',False))
        self.resume_action.setVisible(draft);self.resume_action.setEnabled(draft)
        store=getattr(self.view,'store',None)
        jobs=store.jobs() if store is not None else []
        session=set(getattr(self.view,'session_jobs',()))
        self.processing_action.setEnabled(any(job['id'] in session for job in jobs))

    def quit_app(self,*_):
        if self._closed or self._quitting:return False
        self._quitting=True
        try:accepted=bool(self.shell.request_quit())
        finally:self._quitting=False
        if not accepted:return False
        self.quitting.emit();self.shutdown();self.app.quit()
        return True

    def shutdown(self,*_):
        if self._closed:return
        self._closed=True;self.icon.hide();self.menu.close()
        if self._active and self._previous_quit is not None:
            self.app.setQuitOnLastWindowClosed(self._previous_quit)
        self._active=False
