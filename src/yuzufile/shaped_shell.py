"""A real shaped desktop shell around yuzufile's existing conversion controller.

The wheel and forms are the original bound widgets.  This layer owns only their
placement, native window shape and compact processing presentation.
"""
import json

from PySide6.QtCore import Qt,QEvent,QPoint,QPointF,QRect,QRectF,QSize,QTimer,Signal
from PySide6.QtGui import (QColor,QCursor,QGuiApplication,QKeySequence,QLinearGradient,
                          QPainter,QPainterPath,QPen,QRegion,QShortcut)
from PySide6.QtWidgets import (QApplication,QBoxLayout,QGridLayout,QHBoxLayout,QLabel,QPushButton,
                              QScrollArea,QSizePolicy,QVBoxLayout,QWidget,QMenu,QFrame,QComboBox)

from yuzufile.icons import icon
from yuzufile import ui_style
from yuzufile.ui_components import IconButton
from yuzufile.ui_style import COLORS,STYLE,light_palette
from yuzufile.tool_window import ToolHeader


class SilverSurface(QWidget):
    def __init__(self,parent=None,radius=24):
        super().__init__(parent);self.radius=radius
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,False)

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect=QRectF(self.rect()).adjusted(1,1,-1,-1)
        fill=QLinearGradient(rect.topLeft(),rect.bottomLeft())
        fill.setColorAt(0,QColor('#fafafa'));fill.setColorAt(1,QColor('#f5f5f5'))
        painter.setPen(QPen(QColor('#d7d7d7'),1));painter.setBrush(fill)
        painter.drawRoundedRect(rect,self.radius,self.radius)
        painter.setBrush(Qt.BrushStyle.NoBrush);painter.setPen(QPen(QColor(255,255,255,160),1))
        painter.drawRoundedRect(rect.adjusted(1,1,-1,-2),self.radius-1,self.radius-1)


class DragGrip(QLabel):
    """A visible handle; native moving preserves multi-monitor/DPI behavior."""
    def __init__(self,shell):
        super().__init__('yuzufile');self.shell=shell;self.origin=None
        self.setAccessibleName('Move yuzufile window')
        self.setToolTip('Drag to move · Alt+arrow keys move the window')
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setMinimumWidth(75);self.setAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter);self.setMargin(6)

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.setFont(self.font());painter.setPen(QColor(COLORS['text']))
        rect=QRect(self.margin(),0,max(0,self.width()-self.margin()-29),self.height())
        painter.drawText(rect,Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,
                         self.fontMetrics().elidedText(self.text(),Qt.TextElideMode.ElideRight,rect.width()))
        icon('grip-vertical',13).paint(painter,QRect(self.width()-19,(self.height()-13)//2,13,13))

    def mousePressEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton:return super().mousePressEvent(event)
        self.origin=event.globalPosition().toPoint()-self.shell.pos()
        handle=self.shell.windowHandle()
        if handle is not None and handle.startSystemMove():self.origin=None
        self.setCursor(Qt.CursorShape.ClosedHandCursor);event.accept()

    def mouseMoveEvent(self,event):
        if self.origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.shell.move(event.globalPosition().toPoint()-self.origin);event.accept()
        else:super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        self.origin=None;self.setCursor(Qt.CursorShape.OpenHandCursor);event.accept()


class FloatingShell(QWidget):
    mode_changed=Signal(str)
    WHEEL=380

    def __init__(self,controller):
        super().__init__(None,Qt.WindowType.Window|Qt.WindowType.FramelessWindowHint
                         |Qt.WindowType.NoDropShadowWindowHint)
        self.controller=controller;controller.shell=self
        self.tray_controller=None
        self.mode='wheel';self.closing=False;self._closed=False;self._laying_out=False
        self._task_open=False;self._resume_editor=None;self._resume_plan=None
        self._seen_jobs=set(controller.session_jobs);self._last_signature=None
        self._action_signature=None;self._context_signature=None;self._job_id=None;self._screen_bound=None
        self._native_handle=None
        self._progress_position=None;self._task_position=None;self._result_buttons=[];self._selected_job=None;self._picker_signature=None
        available=self.screen().availableGeometry();self._anchor=available.center()
        self.setWindowTitle(controller.windowTitle());self.setWindowIcon(controller.windowIcon())
        self.setAccessibleName('yuzufile floating tool wheel')
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setPalette(light_palette());self.setAcceptDrops(True)
        self.setStyleSheet(STYLE+getattr(ui_style,'SHELL_STYLE','')+'''
            QFrame#optionsPanel { background:transparent; border:0; }
            QFrame#actionDock { background:transparent; border:0; }
            QWidget#shellForm { background:transparent; }
            QLabel#shellTitle { font-size:15px; font-weight:600; }
        ''')

        self.wheel=controller.tool_wheel;self.wheel.setParent(self)
        self.wheel.setFixedSize(self.WHEEL,self.WHEEL);self.wheel.show()
        self.grip=SilverSurface(self,22)
        grip=QHBoxLayout(self.grip);grip.setContentsMargins(7,4,7,4);grip.setSpacing(2)
        self.drag_handle=DragGrip(self);grip.addWidget(self.drag_handle,1)
        self.files_button=IconButton('files','Added PDFs and options',self.show_context);grip.addWidget(self.files_button)
        self.tools_button=IconButton('circle-dot','Return to wheel',self.show_wheel);grip.addWidget(self.tools_button)
        self.minimize_button=IconButton('minus','Minimize yuzufile',self.showMinimized);grip.addWidget(self.minimize_button)
        self.close_button=IconButton('x','Close yuzufile',self.close);grip.addWidget(self.close_button)
        # Public controls are also discoverable from the compact grip.
        for name in ('tools_button','minimize_button','close_button'):
            setattr(self.grip,name,getattr(self,name))

        self.tray=SilverSurface(self,26)
        tray=QVBoxLayout(self.tray);tray.setContentsMargins(2,2,2,2);tray.setSpacing(6)
        self.task_header=ToolHeader(self,'PDF tools')
        self.task_header.maximize.hide()
        self.task_header.close_button.setAccessibleName('Back to tools');self.task_header.close_button.setToolTip('Back to tools · Esc')
        self.tray_title=self.task_header.title;self.collapse_button=self.task_header.close_button
        tray.addWidget(self.task_header)
        self.selection_label=QLabel();self.selection_label.setObjectName('muted');self.selection_label.setWordWrap(True)
        self.selection_label.setContentsMargins(18,2,18,2)
        tray.addWidget(self.selection_label)
        self.form_scroll=QScrollArea();self.form_scroll.setWidgetResizable(True)
        self.form_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.form_scroll.setMinimumSize(0,0)
        self.form=QWidget();self.form.setObjectName('shellForm')
        form=QVBoxLayout(self.form);form.setContentsMargins(18,4,18,10);form.setSpacing(12)
        file_actions=QHBoxLayout();file_actions.addWidget(controller.file_count,1)
        self.add_button=IconButton('plus','Add PDFs',self.pick_files);file_actions.addWidget(self.add_button)
        self.combine_button=QPushButton('Add tool');self.combine_button.setIcon(icon('plus',14))
        self.combine_button.setToolTip('Combine this operation with another tool')
        self.combine_button.clicked.connect(self.show_tool_menu);file_actions.addWidget(self.combine_button)
        self.clear_button=IconButton('trash-2','Remove all added PDFs',self.clear_files);file_actions.addWidget(self.clear_button)
        form.addLayout(file_actions)
        self.empty_drop=QPushButton('Drop PDFs here\nor click to browse');self.empty_drop.setIcon(icon('file-plus',24))
        self.empty_drop.setObjectName('taskDrop');self.empty_drop.setMinimumHeight(96)
        self.empty_drop.setAccessibleName('Add PDFs to this tool');self.empty_drop.clicked.connect(self.pick_files)
        self.empty_drop.setStyleSheet('QPushButton { background:#f0f0f0; border:1px dashed #d2d2d2; border-radius:14px; font-size:14px; } QPushButton:hover { background:#eaeaea; }')
        form.addWidget(self.empty_drop)
        form.addWidget(controller.files)
        self.original_size=QLabel();self.original_size.setObjectName('filename');form.addWidget(self.original_size)
        form.addWidget(controller.options_panel)
        controller.options_panel.layout().setContentsMargins(0,2,0,2)
        form.addWidget(controller.activity);form.addStretch()
        self.form_scroll.setWidget(self.form);tray.addWidget(self.form_scroll,1)
        self.dock=controller.workspace.dock
        divider=QFrame();divider.setFixedHeight(1);divider.setStyleSheet('background:#dddddd; border:0;');tray.addWidget(divider)
        tray.addWidget(self.dock)
        self.dock.layout().setContentsMargins(18,8,18,12)
        self._prepare_options()

        self.pill=SilverSurface(self,20)
        capsule=QVBoxLayout(self.pill);capsule.setContentsMargins(16,10,16,14);capsule.setSpacing(8)
        top=QHBoxLayout();top.setSpacing(4)
        self.pill_title=DragGrip(self);self.pill_title.setObjectName('filename')
        self.pill_title.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        top.addWidget(self.pill_title,1)
        self.pill_minimize=IconButton('minus','Minimize yuzufile',self.showMinimized);top.addWidget(self.pill_minimize)
        self.pill_close=IconButton('x','Close yuzufile',self.close);top.addWidget(self.pill_close)
        capsule.addLayout(top)
        self.job_picker=QComboBox();self.job_picker.setAccessibleName('Processing and result files')
        self.job_picker.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        self.job_picker.currentIndexChanged.connect(self.pick_job);capsule.addWidget(self.job_picker)
        self.pill_caption=QLabel();self.pill_caption.setObjectName('muted')
        self.pill_caption.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        capsule.addWidget(self.pill_caption)
        self.pill_savings=QLabel();self.pill_savings.setObjectName('muted')
        self.pill_savings.setTextFormat(Qt.TextFormat.RichText);self.pill_savings.hide()
        capsule.addWidget(self.pill_savings)
        from yuzufile.ui import SegmentedProgressBar
        meter=QHBoxLayout();self.progress=SegmentedProgressBar();self.progress.setRange(0,100);self.progress.setTextVisible(False)
        meter.addWidget(self.progress,1);self.percent=QLabel();self.percent.setMinimumWidth(54);meter.addWidget(self.percent)
        self.cancel_button=QPushButton('Cancel');self.cancel_button.clicked.connect(self.cancel_current)
        self.progress_row=QWidget();self.progress_row.setLayout(meter);meter.setContentsMargins(0,0,0,0)
        capsule.addWidget(self.progress_row)
        self.result_actions=QWidget();self.result_layout=QGridLayout(self.result_actions)
        self.result_layout.setContentsMargins(0,0,0,0);self.result_layout.setSpacing(6)
        capsule.addWidget(self.result_actions)
        footer=QHBoxLayout();footer.setSpacing(8)
        self.pill_tools=QPushButton('Back to tools');self.pill_tools.setIcon(icon('arrow-left',16))
        self.pill_tools.setObjectName('backToTools');self.pill_tools.setAccessibleName('Back to tools')
        self.pill_tools.clicked.connect(self.show_wheel)
        footer.addWidget(self.pill_tools);footer.addStretch();footer.addWidget(self.cancel_button)
        capsule.addLayout(footer)

        for button in controller.operations.values():
            button.clicked.connect(self.show_tray)
        controller.upload.clicked.connect(self._after_file_picker)
        controller.start_button.clicked.connect(self._after_start)
        self.timer=QTimer(self);self.timer.setInterval(250);self.timer.timeout.connect(self.sync_from_controller);self.timer.start()
        for key,callback in (('Escape',self.show_wheel),('Ctrl+O',self.pick_files),
                             ('Ctrl+Return',self.start)):
            shortcut=QShortcut(QKeySequence(key),self);shortcut.activated.connect(callback)
        for key,delta in (('Alt+Left',QPoint(-12,0)),('Alt+Right',QPoint(12,0)),
                          ('Alt+Up',QPoint(0,-12)),('Alt+Down',QPoint(0,12))):
            shortcut=QShortcut(QKeySequence(key),self);shortcut.activated.connect(lambda d=delta:self.move_clamped(self.pos()+d))
        self.sync_from_controller();self._layout_shell()

    @property
    def resident(self):
        return self.tray_controller is not None and self.tray_controller.active

    @property
    def has_draft(self):
        return bool(self._task_open or (self._resume_editor and (self.controller.pending or self._resume_plan)))

    def enter_resident_mode(self):
        """The resident app has tasks and a transient drop wheel, without Home."""
        self.setAccessibleName('yuzufile tool window')
        self.task_header.close_button.setAccessibleName('Close tool')
        self.task_header.close_button.setToolTip('Close tool · Esc')
        self.pill_tools.setObjectName('dismissTask')
        self._set_mode('idle');self.hide()
        self.sync_from_controller()

    def reject(self):self.show_wheel()

    def dismiss_to_tray(self):
        if self.resident:self.tray_controller.hide_window()
        else:self._set_mode('wheel')

    def show_current(self):
        """Restore a real task/results window, never a persistent wheel."""
        if self._closed:return False
        self.sync_from_controller()
        if self._task_open:self.show_tray()
        elif self._resume_editor and (self.controller.pending or self._resume_plan):
            self.open_tool(self._resume_editor,plan=self._resume_plan);return True
        elif self._job_id:self.show_progress()
        else:return False
        self.showNormal();self.raise_();self.activateWindow();return True

    def choose_tool_menu(self,position=None,paths=None):
        """Keyboard/file-picker access uses a small menu, not another Home UI.

        The picked paths are staged until a tool is chosen. Cancelling the menu
        preserves the current task, selection and existing pending batch.
        """
        if self._closed:return
        anchor=QPoint(position) if position is not None else QCursor.pos()
        staged=list(paths) if paths is not None else None
        menu=QMenu(self);menu.setTitle('Process PDFs');menu.setAccessibleName('Choose a PDF tool')
        for code,button in self.controller.operations.items():
            action=menu.addAction(icon(button.glyph,16),button.title);action.setData(code)
            action.triggered.connect(lambda checked=False,c=code:QTimer.singleShot(
                0,self,lambda:self.open_tool(c,staged,anchor)))
        menu.addSeparator()
        for code,button in (('merge',self.controller.merge_button),('arrange',self.controller.organize_button)):
            action=menu.addAction(icon(button.glyph,16),button.title);action.setData(code)
            action.triggered.connect(lambda checked=False,c=code:QTimer.singleShot(
                0,self,lambda:self.open_tool(c,staged,anchor)))
        self.tool_chooser=menu
        menu.aboutToHide.connect(menu.deleteLater)
        menu.popup(anchor)
        return menu

    def open_tool(self,code,paths=None,anchor=None,plan=None):
        """One shared route for native PDF drops and the tray's manual picker."""
        if self._closed or code not in {*self.controller.operations,'merge','arrange'}:return
        modal=QApplication.activeModalWidget()
        if modal is not None:
            modal.showNormal();modal.raise_();modal.activateWindow();return
        controller=self.controller
        if paths is not None:controller.add_files(paths)
        if anchor is not None:
            self._anchor=QPoint(anchor);self._task_position=None
        if code in controller.operations:
            self._resume_editor=None;self._resume_plan=None
            for name,button in controller.operations.items():button.setChecked(name==code)
            controller.update_mode();self.show_tray()
            self.showNormal();self.raise_();self.activateWindow()
        else:
            self._task_open=False;self._resume_editor=code;self._resume_plan=plan
            self.hide()
            before=set(controller.session_jobs)
            callback=controller.merge_pdfs if code=='merge' else controller.organize_pages
            callback(plan=plan) if plan is not None else callback()
            self.sync_from_controller()
            if set(controller.session_jobs)-before:
                self._resume_editor=None;self._resume_plan=None
                self.show_progress();self.showNormal();self.raise_();self.activateWindow()

    def pick_job(self,index):
        self._selected_job=self.job_picker.itemData(index);self.sync_from_controller()

    def show_tool_menu(self):
        menu=QMenu(self);menu.setTitle('Combine tools')
        selected=self.controller.selected_operations()
        for code,button in self.controller.operations.items():
            entry=menu.addAction(icon(button.glyph,16),button.title);entry.setCheckable(True);entry.setChecked(code in selected)
            conflict=(code=='remove_ocr' and bool(selected&{'ocr','markdown','docx'})) or (code in {'ocr','markdown','docx'} and 'remove_ocr' in selected)
            entry.setEnabled(not conflict)
            if conflict:entry.setToolTip('Remove OCR is used separately from recognition tools')
            entry.toggled.connect(lambda checked,c=code:self.controller.operations[c].setChecked(checked))
        self.tool_menu=menu
        menu.aboutToHide.connect(self.sync_from_controller)
        menu.aboutToHide.connect(menu.deleteLater)
        menu.popup(self.combine_button.mapToGlobal(self.combine_button.rect().bottomLeft()))

    @property
    def output_directory(self):return self.controller.output_directory

    def _prepare_options(self):
        """Keep bound form widgets, but give the small tray its own wrapping."""
        c=self.controller
        scope=c.cleanup_row.layout().itemAt(1).layout()
        scope.itemAt(0).widget().setWordWrap(True)
        # A heading above the language grid avoids reserving half a row for it.
        row=c.language_row.layout();symbol=row.takeAt(0).widget();title=row.takeAt(0).widget()
        grid=row.takeAt(0).layout();grid.setParent(None)
        heading=QWidget();heading_row=QHBoxLayout(heading);heading_row.setContentsMargins(0,0,0,0)
        heading_row.addWidget(symbol);heading_row.addWidget(title);heading_row.addStretch()
        row.setDirection(QBoxLayout.Direction.TopToBottom);row.addWidget(heading);row.addLayout(grid)
        c.compression_row.layout().setDirection(QBoxLayout.Direction.TopToBottom)

    def _reflow_options(self,width):
        c=self.controller
        controls=c.cleanup_row.layout().itemAt(0).layout()
        horizontal=sum(w.minimumSizeHint().width() for w in (c.cleanup_straighten,c.cleanup_trim))+controls.spacing()
        controls.setDirection(QBoxLayout.Direction.TopToBottom if horizontal>width else QBoxLayout.Direction.LeftToRight)
        segments=c.compression_segments.layout()
        required=sum(b.minimumSizeHint().width() for b in c.compression_segments.buttons)+8
        segments.setDirection(QBoxLayout.Direction.TopToBottom if required>width else QBoxLayout.Direction.LeftToRight)
        columns=3 if width>=400 else 2 if width>=260 else 1
        for column in range(3):c.language_options.setColumnStretch(column,1 if column<columns else 0)
        for index,widget in enumerate(c.languages.values()):c.language_options.addWidget(widget,index//columns,index%columns)
        c.options_panel.layout().invalidate();self.form.layout().invalidate()

    def _set_mode(self,mode):
        if self._closed:return
        changed=mode!=self.mode;self.mode=mode;self._layout_shell()
        if changed:self.mode_changed.emit(mode)

    def show_wheel(self,*args):
        if self.resident:self.dismiss_to_tray()
        else:self._set_mode('wheel')
    def show_tray(self,*args):
        self._task_open=True
        self.sync_from_controller();self._set_mode('tray')
    def show_progress(self,*args):
        self.sync_from_controller()
        if self._job_id:self._set_mode('progress')
        elif self.resident:self._set_mode('idle');self.hide()
        else:self._set_mode('wheel')

    def show_context(self,*args):
        self.sync_from_controller()
        if self._job_id:self.show_progress()
        else:self.show_tray()

    def pick_files(self,*args):
        self.controller.pick_files();self._after_file_picker()

    def _after_file_picker(self,*args):
        self.sync_from_controller()
        if self.controller.pending:self.show_tray()

    def clear_files(self):self.controller.clear_files();self.sync_from_controller()

    def start(self):
        if self.controller.start_button.isEnabled():self.controller.start_button.click()
        else:self.show_tray()

    def _after_start(self,*args):
        self.sync_from_controller()
        if self._job_id:
            self._task_open=False;self._resume_editor=None;self._resume_plan=None;self.show_progress()
        else:self.show_tray()

    def _jobs(self):
        jobs=[]
        for job_id in list(self.controller.session_jobs):
            try:jobs.append(self.controller.store.get(job_id))
            except KeyError:continue
        return jobs

    def sync_from_controller(self):
        if self._closed or self.closing:return
        controller=self.controller
        try:jobs=self._jobs()
        except Exception:
            # An external application shutdown must not keep querying a closed DB.
            self.shutdown();return
        selected=controller.selected_operations()
        titles=[controller.operations[code].title for code in controller.operations if code in selected]
        task_titles={'ocr':'OCR PDF','docx':'Export to Word','markdown':'Export to Markdown','compress':'Compress PDF','cleanup':'Clean up pages','split':'Split spreads','remove_ocr':'Remove OCR'}
        self.tray_title.setText(task_titles[next(iter(selected))] if len(selected)==1 else 'Process PDFs' if titles else 'Choose a tool')
        self.selection_label.setText(' · '.join(titles) if len(titles)>1 else '')
        self.selection_label.setVisible(len(titles)>1)
        self.clear_button.setEnabled(bool(controller.pending))
        self.empty_drop.setVisible(not controller.pending)
        self.original_size.setVisible('compress' in selected and bool(controller.pending))
        if controller.pending:
            from yuzufile.ui import size_label
            try:self.original_size.setText('Original size: '+size_label(sum(path.stat().st_size for path in controller.pending)))
            except OSError:self.original_size.setText('Original size unavailable')
        active=[job for job in jobs if job['state'] in {'queued','running'}]
        attention=[job for job in jobs if job['state'] in {'failed','interrupted','cancelled'}]
        current=next((job for job in active if job['state']=='running'),active[0] if active else attention[-1] if attention else jobs[-1] if jobs else None)
        current=next((job for job in jobs if job['id']==self._selected_job),current)
        self._job_id=current['id'] if current else None
        picker_signature=tuple((job['id'],job['state']) for job in jobs)
        if picker_signature!=self._picker_signature:
            self._picker_signature=picker_signature;self.job_picker.blockSignals(True);self.job_picker.clear()
            labels={'queued':'Waiting','running':'Processing','succeeded':'Completed','failed':'Failed','cancelled':'Cancelled','interrupted':'Interrupted'}
            for job in jobs:self.job_picker.addItem(controller.job_name(job)+' · '+labels[job['state']],job['id'])
            self.job_picker.blockSignals(False)
        self.job_picker.blockSignals(True);self.job_picker.setCurrentIndex(self.job_picker.findData(self._job_id));self.job_picker.blockSignals(False)
        self.job_picker.setVisible(len(jobs)>1)
        context=(self._job_id,current['state'] if current else None)
        if context!=self._context_signature:
            self._context_signature=context
            running=current is not None and current['state'] in {'queued','running'}
            title='Show processing' if running else 'Show results' if current else 'Added PDFs and options'
            glyph='clock' if running else 'circle-check' if current and current['state']=='succeeded' else 'info' if current else 'files'
            self.files_button.setIcon(icon(glyph,18));self.files_button.setAccessibleName(title);self.files_button.setToolTip(title)
        if current:self._sync_pill(current,active,jobs)
        new={job['id'] for job in jobs}-self._seen_jobs
        self._seen_jobs={job['id'] for job in jobs}
        if new:self.mode='progress';self._task_open=False
        elif self.mode=='progress' and not jobs:self.mode='idle' if self.resident else 'wheel'
        signature=(self.mode,tuple(map(str,controller.pending)),tuple(sorted(selected)),
                   controller.activity.isHidden(),self.form.sizeHint().height(),self.dock.sizeHint().height(),
                   bool(active),bool(current),self._action_signature,self.pill_savings.isHidden())
        if signature!=self._last_signature:
            self._last_signature=signature;self._layout_shell()

    def _sync_pill(self,job,active,jobs):
        c=self.controller;running=job['state'] in {'queued','running'}
        if self.resident:
            self.pill_tools.setText('Hide' if running else 'Done')
            self.pill_tools.setAccessibleName('Hide processing' if running else 'Close results')
            self.pill_tools.setToolTip('Continue in the background' if running else 'Return to the tray')
            self.pill_tools.setIcon(icon('minus' if running else 'check',16))
        if running:title=f"{len(active)} {'PDF' if len(active)==1 else 'PDFs'} processing"
        else:
            completed=sum(j['state']=='succeeded' for j in jobs)
            failed=sum(j['state'] in {'failed','interrupted'} for j in jobs)
            cancelled=sum(j['state']=='cancelled' for j in jobs)
            counts=([f'{completed} completed'] if completed else [])+([f'{failed} failed'] if failed else [])+([f'{cancelled} cancelled'] if cancelled else [])
            title=' · '.join(counts) or job['stage']
        self.pill_title.setText(title)
        self.pill_title.setAccessibleDescription(title+'; drag to move yuzufile')
        self.pill_title.setToolTip(title+' · Drag to move yuzufile')
        caption=c.job_name(job)+' · '+(job['stage'] if running else job['error'] or c.operation_caption(job))
        metrics=self.pill_caption.fontMetrics();self.pill_caption.setText(metrics.elidedText(caption,Qt.TextElideMode.ElideMiddle,max(160,self.pill.width()-32)))
        self.pill_caption.setToolTip(caption+(('\n'+job['error']) if job['error'] else ''))
        savings='compression' in json.loads(job['metadata'])
        self.pill_savings.setVisible(savings)
        if savings:self.pill_savings.setText(c.result_size(job))
        percent=c.supervisor.progress if c.supervisor.active==job['id'] else 0
        self.progress.setValue(percent);self.percent.setText(f'{percent}%' if job['state']=='running' else 'Waiting')
        self.progress_row.setVisible(running);self.result_actions.setVisible(not running);self.cancel_button.setVisible(running)
        signature=(job['id'],job['state'],c.artifact_signature(job['id']))
        if signature==self._action_signature:return
        self._action_signature=signature
        while self.result_layout.count():
            item=self.result_layout.takeAt(0)
            if item.widget():item.widget().hide();item.widget().deleteLater()
        self._result_buttons=[]
        if running:return
        if job['state']=='succeeded':
            for kind,title in (('pdf','Open PDF'),('docx','Open Word'),('markdown','Open Markdown')):
                if c.artifact_path(job['id'],kind):
                    button=QPushButton(title)
                    if not self._result_buttons:button.setObjectName('primary')
                    button.clicked.connect(lambda checked=False,k=kind,jid=job['id']:c.open_artifact(jid,k));self._result_buttons.append(button)
            folder=QPushButton('Open Folder');folder.setIcon(icon('folder-open',16))
            folder.setEnabled((c.store.job_dir(job['id'])/'result').is_dir())
            folder.clicked.connect(lambda checked=False,jid=job['id']:c.open_job_folder(jid));self._result_buttons.append(folder)
        else:
            retry=QPushButton('Process again');retry.setObjectName('primary')
            retry.clicked.connect(lambda checked=False,jid=job['id']:c.retry_job(jid));self._result_buttons.append(retry)
        more=IconButton('ellipsis','Result details and actions')
        more.clicked.connect(lambda checked=False,jid=job['id'],button=more:c.show_job_menu(jid,button));self._result_buttons.append(more)
        self._reflow_results(max(1,self.pill.width()-32))

    def _reflow_results(self,width):
        buttons=self._result_buttons
        while self.result_layout.count():self.result_layout.takeAt(0)
        if not buttons:return
        for button in buttons:
            if button.parentWidget() is not self.result_actions:button.setParent(self.result_actions)
            button.ensurePolished();button.setMinimumHeight(max(32,button.minimumHeight()))
        columns=min(3,len(buttons))
        while columns>1:
            widths=[max(b.minimumSizeHint().width() for i,b in enumerate(buttons) if i%columns==column) for column in range(columns)]
            if sum(widths)+self.result_layout.spacing()*(columns-1)<=width:break
            columns-=1
        for column in range(3):self.result_layout.setColumnStretch(column,1 if column<columns else 0)
        for index,button in enumerate(buttons):
            if isinstance(button,IconButton):self.result_layout.addWidget(button,index//columns,index%columns,1,columns-index%columns,Qt.AlignmentFlag.AlignRight)
            else:self.result_layout.addWidget(button,index//columns,index%columns)
            button.show()
        self.result_layout.invalidate();self.result_layout.activate()

    def cancel_current(self):
        if self._job_id:self.controller.cancel_job(self._job_id);self.sync_from_controller()

    def _available(self):
        screen=QGuiApplication.screenAt(self._anchor) or self.screen()
        if screen is not self._screen_bound:
            if self._screen_bound is not None:
                try:self._screen_bound.availableGeometryChanged.disconnect(self._layout_shell)
                except (RuntimeError,TypeError):pass
            self._screen_bound=screen;screen.availableGeometryChanged.connect(self._layout_shell)
        return screen.availableGeometry()

    def _layout_shell(self,*args):
        if self._laying_out or self._closed:return
        self._laying_out=True
        try:
            if self.resident and self.mode in {'idle','wheel'}:
                self.wheel.hide();self.grip.hide();self.tray.hide();self.pill.hide();self.hide();return
            available=self._available();margin=12
            wheel=min(self.WHEEL,max(280,available.width()-24),max(280,available.height()-64))
            self.wheel.setFixedSize(wheel,wheel)
            form_width=min(540,max(280,available.width()-24))
            self._reflow_options(form_width-38)
            side=False
            need=self.form.sizeHint().height()+self.dock.sizeHint().height()+90
            if self.mode=='progress':
                width=min(560,available.width()-8)
                self._reflow_results(max(1,width-48))
                self.pill.layout().invalidate()
                height=max(164,self.pill.layout().sizeHint().height()+16)
                self.pill.setGeometry(8,8,width-16,height-16);size=QSize(width,height)
                position=self._progress_position if self._progress_position is not None else self._anchor-QPoint(width//2,height//2)
            else:
                if self.mode=='tray':
                    height=min(available.height()-8,max(340,min(need,650)))
                    size=QSize(form_width+16,height)
                    self.tray.setGeometry(8,8,form_width,height-16)
                    self.wheel.setGeometry(8,8,wheel,wheel)
                else:
                    size=QSize(wheel+24,wheel+52)
                    self.wheel.setGeometry(margin,margin,wheel,wheel)
                if self.mode=='tray' and not side:
                    position=self._task_position if self._task_position is not None else self._anchor-QPoint(size.width()//2,size.height()//2)
                else:
                    self.grip.setGeometry(self.wheel.x()+max(0,(wheel-310)//2),self.wheel.y()+wheel-24,min(310,wheel),44)
                    position=self._anchor-(self.wheel.pos()+QPoint(wheel//2,wheel//2))
            self.setFixedSize(size)
            self.move_clamped(position,available)
            if self.mode=='progress':
                self._progress_position=QPoint(self.pos());self._anchor=self.geometry().center()
            elif self.mode=='tray':self._task_position=QPoint(self.pos())
            self.wheel.setVisible(self.mode=='wheel' or (self.mode=='tray' and side))
            self.grip.setVisible(self.mode=='wheel');self.tray.setVisible(self.mode=='tray');self.pill.setVisible(self.mode=='progress')
            self.tools_button.setVisible(self.mode!='wheel')
            self.tray.raise_();self.grip.raise_();self.pill.raise_()
            path=self.shape_path();self.setMask(QRegion(path.toFillPolygon().toPolygon()))
            if self.mode!='progress' and (self.mode=='wheel' or side):
                self._anchor=self.pos()+self.wheel.pos()+QPoint(wheel//2,wheel//2)
            self.update()
        finally:self._laying_out=False

    def shape_path(self):
        path=QPainterPath()
        path.setFillRule(Qt.FillRule.WindingFill)
        if self.mode=='progress':path.addRoundedRect(QRectF(self.pill.geometry()).adjusted(-5,-5,5,5),self.pill.radius+6,self.pill.radius+6)
        else:
            if self.wheel.isVisible() or self.mode=='wheel':
                center,radius=self.wheel.geometry_values();center+=QPointF(self.wheel.pos());radius+=9
                path.addEllipse(center,radius,radius)
            if self.mode=='wheel':path.addRoundedRect(QRectF(self.grip.geometry()).adjusted(1,1,-1,-1),22,22)
            if self.mode=='tray':path.addRoundedRect(QRectF(self.tray.geometry()).adjusted(-5,-5,5,5),32,32)
        return path.simplified()

    def paintEvent(self,event):
        if self.mode not in {'tray','progress'}:return
        surface=self.tray if self.mode=='tray' else self.pill
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.setPen(Qt.PenStyle.NoPen)
        rect=QRectF(surface.geometry()).adjusted(1,1,-1,-1)
        for spread in range(6,0,-1):
            p.setBrush(QColor(0,0,0,4));p.drawRoundedRect(rect.adjusted(-spread,1-spread,spread,2+spread),surface.radius+spread,surface.radius+spread)

    def move_clamped(self,point,available=None):
        available=available or self._available()
        x=max(available.left(),min(point.x(),available.right()-self.width()+1))
        y=max(available.top(),min(point.y(),available.bottom()-self.height()+1))
        self.move(x,y)

    def moveEvent(self,event):
        super().moveEvent(event)
        if not self._laying_out and hasattr(self,'wheel'):
            if self.mode=='progress':
                self._progress_position=QPoint(self.pos());self._anchor=self.geometry().center()
            else:
                self._anchor=self.geometry().center() if self.mode=='tray' else self.pos()+self.wheel.pos()+self.wheel.rect().center()
                if self.mode=='tray':self._task_position=QPoint(self.pos())
                self._progress_position=None

    def showEvent(self,event):
        super().showEvent(event)
        handle=self.windowHandle()
        if handle is not None and handle is not self._native_handle:
            self._native_handle=handle;handle.screenChanged.connect(self._native_screen_changed)
        self._layout_shell()

    def setVisible(self,visible):
        # Old controller paths may try to reveal their owner after closing a
        # dialog. Idle residence has no window to reveal.
        if visible and getattr(self,'tray_controller',None) is not None and self.resident and self.mode in {'idle','wheel'}:
            return
        super().setVisible(visible)

    def _native_screen_changed(self,screen):
        if self._closed or self._laying_out:return
        if self.mode=='progress':
            anchor=self.geometry().center();self._progress_position=QPoint(self.pos())
        elif self.wheel.isVisible():anchor=self.pos()+self.wheel.geometry().center()
        else:anchor=self.geometry().center()
        area=screen.availableGeometry()
        self._anchor=QPoint(max(area.left()+1,min(anchor.x(),area.right()-1)),
                            max(area.top()+1,min(anchor.y(),area.bottom()-1)))
        self._layout_shell()

    def dragEnterEvent(self,event):
        from yuzufile.desktop_drag import pdf_paths,accept_copy
        if pdf_paths(event.mimeData()):accept_copy(event)

    def dragMoveEvent(self,event):
        from yuzufile.desktop_drag import pdf_paths,accept_copy
        if pdf_paths(event.mimeData()):accept_copy(event)

    def dropEvent(self,event):
        from yuzufile.desktop_drag import pdf_paths,accept_copy
        paths=pdf_paths(event.mimeData())
        if paths and accept_copy(event):
            self.controller.add_files(paths);self.show_tray()

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type()==QEvent.Type.WindowStateChange and self.isMinimized():
            tray=self.tray_controller
            # Qt finishes showMinimized after delivering the state event. Hide
            # on the next loop turn so it cannot make the window visible again.
            if tray is not None and tray.active:QTimer.singleShot(0,self,self._hide_minimized)

    def _hide_minimized(self):
        tray=self.tray_controller
        if not self._closed and self.isMinimized() and tray is not None and tray.active:
            tray.hide_window()

    def shutdown(self):
        self._closed=True
        if hasattr(self,'timer'):self.timer.stop()

    def request_quit(self):
        """Explicit Quit owns worker shutdown; hiding a resident window does not."""
        if self._closed:return True
        self.closing=True
        try:
            accepted=self.controller.close()
        except Exception:
            self.closing=False;raise
        if not accepted:
            self.closing=False;return False
        self.shutdown();self.hide();return True

    def closeEvent(self,event):
        if self._closed:event.accept();return
        tray=self.tray_controller
        if tray is not None and tray.active and not self.closing:
            tray.hide_window();event.ignore();return
        if self.request_quit():event.accept()
        else:event.ignore()
