from __future__ import annotations

import json
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QUrl, QSize, QRect, QRectF, QPoint
from PySide6.QtGui import QDesktopServices, QPainter, QColor, QPen, QPainterPath,QLinearGradient
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMenu, QMessageBox, QPushButton, QProgressBar, QScrollArea, QSizePolicy, QListView, QStyledItemDelegate,
    QStackedWidget, QStyle, QStyleOptionButton, QTextBrowser, QVBoxLayout, QWidget, QDoubleSpinBox, QAbstractSpinBox,QSpinBox,QLayout,
)
from yuzufile import __version__
from yuzufile.compression import LEVELS, compression_summary, size_label
from yuzufile.icons import icon, pdf_icon
from yuzufile.languages import installed_languages, NAMES
from yuzufile.operations import MODES, mode_for, mode_label
from yuzufile.performance import PROFILES
from yuzufile.storage import Store, owned_path
from yuzufile.supervisor import Supervisor
from yuzufile.ui_style import STYLE, COLORS, POPUP_STYLE, light_palette
from yuzufile.spreads import DIRECTIONS, settings as split_settings
from yuzufile.ui_components import IconButton, WorkspaceScroll,OptionSegments
from yuzufile.tool_wheel import ToolWheel

TERMINAL = {"succeeded", "failed", "cancelled", "interrupted"}
STATUS = {"succeeded": "Completed", "failed": "Failed", "cancelled": "Cancelled",
          "interrupted": "Interrupted", "queued": "Waiting", "running": "Processing"}


def label(text="", role=None, wrap=False):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    if role:
        widget.setObjectName(role)
    widget.setWordWrap(wrap)
    return widget


def separator(layout):
    line = QFrame()
    line.setObjectName("divider")
    line.setFixedHeight(1)
    layout.addWidget(line)


class CheckBox(QCheckBox):
    def __init__(self, text):
        super().__init__(text)
        self.check = icon("check", 18, COLORS['on_accent'])

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.isChecked():
            option = QStyleOptionButton()
            self.initStyleOption(option)
            rect = self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, self)
            painter = QPainter(self)
            self.check.paint(painter, rect)


class SegmentedProgressBar(QProgressBar):
    """Native progress semantics with the reference's rounded tick rendering."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(22)
        self.setAccessibleName("Processing progress")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        count = max(1, int(self.width() / 5.5))
        pitch = self.width() / count
        span = self.maximum() - self.minimum()
        fraction = max(0.0, min(1.0, (self.value() - self.minimum()) / span)) if span else 0.0
        filled = round(count * fraction)
        height = min(18.0, float(self.height()))
        width = min(2.5, pitch * 0.55)
        for index in range(count):
            position = count - 1 - index if self.layoutDirection() == Qt.LayoutDirection.RightToLeft else index
            painter.setBrush(QColor(COLORS["progress"] if index < filled else COLORS["progress_track"]))
            painter.drawRoundedRect(QRectF(position * pitch + (pitch - width) / 2,
                                          (self.height() - height) / 2, width, height), width / 2, width / 2)


class DropZone(QPushButton):
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        hovered = self.underMouse() or self.hasFocus()
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        fill=QLinearGradient(rect.topLeft(),rect.bottomLeft())
        fill.setColorAt(0,QColor('#ffffff'));fill.setColorAt(1,QColor('#eeefea'))
        painter.setBrush(fill)
        painter.setPen(QPen(QColor('#bd957c' if hovered else '#c7cac0'),1))
        painter.drawEllipse(rect)
        painter.setBrush(QColor('#fafafa'));painter.setPen(QPen(QColor('#ffffff'),1))
        painter.drawEllipse(rect.adjusted(7,7,-7,-7))


class RoundedPopup(QFrame):
    def __init__(self, parent):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        palette = light_palette()
        palette.setColor(palette.ColorRole.Window, QColor(COLORS['surface']))
        self.setPalette(palette)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(COLORS['border']), 1))
        painter.setBrush(QColor(COLORS['surface']))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 14, 14)


class CompressionBox(QComboBox):
    def __init__(self):
        super().__init__()
        # Own the popup surface so native rectangular menu frames cannot show.
        self.popup = RoundedPopup(self)
        layout = QVBoxLayout(self.popup)
        layout.setContentsMargins(6, 6, 6, 6)
        view = QListView(self.popup)
        view.setItemDelegate(QStyledItemDelegate(view))
        view.setPalette(light_palette())
        view.viewport().setPalette(light_palette())
        view.viewport().setAutoFillBackground(True)
        view.setStyleSheet(POPUP_STYLE)
        view.setModel(self.model())
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.popup_view = view
        layout.addWidget(view)
        view.clicked.connect(self.choose_item)
        view.activated.connect(self.choose_item)

    def view(self):
        return self.popup_view

    def choose_item(self, index):
        if index.isValid() and index.flags() & Qt.ItemFlag.ItemIsEnabled:
            self.setCurrentIndex(index.row())
            self.activated.emit(index.row())
            self.hidePopup()
            self.setFocus(Qt.FocusReason.PopupFocusReason)

    def showPopup(self):
        if not self.isEnabled() or not self.count():
            return
        self.popup.ensurePolished()
        self.popup_view.setCurrentIndex(self.model().index(self.currentIndex(), self.modelColumn()))
        row_height = max(36, self.popup_view.sizeHintForRow(0))
        height = min(self.count(), 8) * row_height + 12
        screen = self.screen().availableGeometry()
        width = min(max(self.width(), self.popup_view.sizeHintForColumn(0) + 28), screen.width())
        below = self.mapToGlobal(QPoint(0, self.height() + 4))
        y = below.y() if below.y() + height <= screen.bottom() else self.mapToGlobal(QPoint(0, -height - 4)).y()
        self.popup.setGeometry(max(screen.left(), min(below.x(), screen.right() - width + 1)),
                               max(screen.top(), y), width, min(height, screen.height()))
        self.popup.show()
        self.popup_view.setFocus(Qt.FocusReason.PopupFocusReason)
        self.popup_view.scrollTo(self.popup_view.currentIndex())

    def hidePopup(self):
        self.popup.hide()
        super().hidePopup()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        icon("chevron-down", 14).paint(painter, QRect(self.width() - 24, (self.height() - 14) // 2, 14, 14))


class Window(QMainWindow):
    def __init__(self, store: Store):
        super().__init__()
        self.store = store
        self.shell = None
        self._closed = False
        self.supervisor = Supervisor(store)
        self.pending = []
        self.cleanup_visual = {}
        self.split_cuts = None
        self.output_directory = None
        self.session_jobs = []
        self.cards = {}
        self.detail_dialog = None
        self.last_revealed_job = None
        self.setWindowTitle(f"YuzuFile {__version__}")
        # Top-level dialogs and selected thumbnail icons also need the palette;
        # they do not consistently inherit a QMainWindow's palette on Windows.
        QApplication.instance().setPalette(light_palette())
        self.setPalette(light_palette())
        available = self.screen().availableGeometry()
        width = min(720, int(available.width() * 0.9))
        height = min(760, int(available.height() * 0.9))
        self.setMinimumSize(min(720, width), min(420, height))
        self.resize(width, height)
        self.move(available.center() - self.rect().center())
        self.setWindowIcon(icon("yuzu"))
        self.setAcceptDrops(True)
        root = QWidget()
        root.setObjectName("root")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        navigation = QWidget()
        navigation.setObjectName("navigation")
        nav = QHBoxLayout(navigation)
        nav.setContentsMargins(22, 8, 22, 8)
        logo = label()
        logo.setObjectName("brandmark")
        logo.setFixedSize(28,28)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setPixmap(icon("file-text", 18, COLORS['on_accent']).pixmap(QSize(18,18)))
        nav.addWidget(logo)
        nav.addWidget(label("yuzufile", "brand"))
        nav.addStretch()
        self.home_link = self.button("Home", lambda: self.tabs.setCurrentIndex(0), nav, "house", role="nav")
        for button in (self.home_link,):
            button.setCheckable(True)
            button.clicked.connect(self.update_navigation)
        outer.addWidget(navigation)
        self.tabs = QStackedWidget()
        outer.addWidget(self.tabs, 1)
        self.build_convert()
        self.tabs.currentChanged.connect(self.update_navigation)
        self.update_navigation()
        self.setCentralWidget(root)
        self.setStyleSheet(STYLE)
        self.refresh_languages()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(200)

    def ui_owner(self):
        return self.shell if self.shell is not None else self


    def exec_tool(self,dialog):
        visible=self.shell is not None and self.shell.isVisible()
        if visible:self.shell.hide()
        try:return dialog.exec()
        finally:
            if visible and not self.shell._closed:self.shell.sync_from_controller();self.shell.show()

    def reveal_tools(self):
        if self.shell is not None:
            self.shell.show_tray();self.shell.showNormal()
            self.shell.raise_()

    def button(self, text, action, layout, symbol=None, role=None):
        button = QPushButton(text)
        if symbol:
            button.setIcon(icon(symbol, 16, COLORS["accent"] if role in {"link", "retry"} else COLORS["icon"]))
        if role:
            button.setObjectName(role)
        button.clicked.connect(action)
        layout.addWidget(button)
        return button

    def update_navigation(self):
        self.home_link.setChecked(self.tabs.currentIndex() == 0)
        for button,glyph in ((self.home_link,'house'),):
            button.setIcon(icon(glyph,16,COLORS['accent'] if button.isChecked() else COLORS['icon']))

    def build_convert(self):
        scroll = WorkspaceScroll()
        self.workspace = scroll
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 18, 24, 20)
        layout.setSpacing(10)
        intro = QVBoxLayout()
        intro.setSpacing(4)
        heading=label('PDF tools','hero');heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        intro.addWidget(heading)
        hint=label('Drop PDFs in the center. Select one tool or combine a few.','muted',True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter);intro.addWidget(hint)
        layout.addLayout(intro)
        self.upload = DropZone()
        self.upload.setObjectName('upload')
        self.upload.setAccessibleName('Browse or drop PDF files')
        self.upload.setCursor(Qt.CursorShape.PointingHandCursor)
        self.upload.clicked.connect(self.pick_files)
        drop = QVBoxLayout(self.upload)
        drop.setContentsMargins(10,12,10,12)
        drop.setSpacing(2);drop.setAlignment(Qt.AlignmentFlag.AlignCenter)
        upload_icon=label()
        self.drop_icon=upload_icon
        upload_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        upload_icon.setPixmap(icon('file-plus',30,COLORS['icon']).pixmap(30,30))
        drop.addWidget(upload_icon)
        self.drop_title=label('Add PDFs','section');self.drop_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop.addWidget(self.drop_title)
        self.drop_hint=label('or drop here','muted');self.drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop.addWidget(self.drop_hint)
        for widget in self.upload.findChildren(QWidget):
            widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.tool_wheel=ToolWheel(self.upload)
        self.operations={}
        for code,title,caption,glyph,short in (
                ('ocr','Searchable PDF','Search and copy scanned text','scan-text','OCR'),
                ('docx','Word document','Export editable text, tables and figures','file-text','WORD'),
                ('compress','Smaller PDF','Reduce PDF file size','minimize-2','COMPRESS'),
                ('cleanup','Clean up scans','Straighten pages and trim margins','sliders-horizontal','CLEAN'),
                ('split','Split spreads','Divide pages into sections','columns-2','SPLIT'),
                ('markdown','Markdown','Export editable Markdown text','file-code-2','MARKDOWN'),
                ('remove_ocr','Remove OCR','Create an image-only PDF with no searchable or selectable text','eraser','No OCR')):
            button=self.tool_wheel.add_tool(title,caption,glyph,short)
            button.setChecked(code=='ocr')
            button.toggled.connect(lambda checked,c=code:self.operation_changed(c,checked))
            button.clicked.connect(lambda checked=False,c=code:self.choose_operation(c))
            button.setToolTip(caption+' · Click to open · Shift-click to combine')
            self.operations[code]=button
        self.merge_button=self.tool_wheel.add_action('Merge PDFs','Combine PDFs in document order',
            'files','MERGE',self.merge_pdfs)
        self.organize_button=self.tool_wheel.add_action('Organize pages','Merge, reorder, rotate and extract pages',
            'panels-top-left','ARRANGE',self.organize_pages)
        layout.addWidget(self.tool_wheel)
        self.files=QListWidget()
        self.files.setAccessibleName('Selected PDFs')
        self.files.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.files.hide()
        layout.addWidget(self.files)
        file_actions=QHBoxLayout()
        self.file_count=label('No files added','muted')
        file_actions.addWidget(self.file_count)
        file_actions.addStretch()
        self.button('Add files',self.pick_files,file_actions,'plus','text')
        self.remove_all=IconButton('trash-2','Remove all files',self.clear_files)
        self.remove_all.setEnabled(False)
        file_actions.addWidget(self.remove_all)
        layout.addLayout(file_actions)
        self.options_panel=QFrame()
        self.options_panel.setObjectName('optionsPanel')
        options=QVBoxLayout(self.options_panel)
        options.setContentsMargins(18,14,18,14)
        options.setSpacing(14)
        self.remove_ocr_row=label('Creates an image-only PDF. Text will not be searchable or selectable.','muted',True)
        options.addWidget(self.remove_ocr_row)
        self.cleanup_row=QWidget()
        cleanup=QVBoxLayout(self.cleanup_row)
        cleanup.setContentsMargins(0,0,0,0)
        clean_controls=QHBoxLayout()
        self.cleanup_straighten=CheckBox('Auto straighten')
        self.cleanup_straighten.setChecked(True)
        self.cleanup_trim=CheckBox('Trim margins')
        self.cleanup_trim.setChecked(True)
        clean_controls.addWidget(self.cleanup_straighten)
        clean_controls.addWidget(self.cleanup_trim)
        clean_controls.addStretch()
        self.cleanup_padding=QSpinBox(self.cleanup_row)
        self.cleanup_padding.setRange(1,20)
        self.cleanup_padding.setValue(3)
        self.cleanup_padding.setPrefix('Padding: ')
        self.cleanup_padding.setSuffix(' mm')
        self.cleanup_padding.setAccessibleName('Margin padding in millimetres')
        self.cleanup_padding.hide()
        cleanup.addLayout(clean_controls)
        clean_scope=QHBoxLayout()
        self.cleanup_ranges=QLineEdit(self.cleanup_row)
        self.cleanup_ranges.setPlaceholderText('All pages, or 2-15, 18')
        self.cleanup_ranges.setAccessibleName('Pages to clean')
        self.cleanup_ranges.hide()
        clean_scope.addWidget(label('Drag to crop, straighten and rotate pages.','muted'),1)
        self.cleanup_preview=self.button('Edit pages',self.preview_cleanup,clean_scope,'sliders-horizontal','text')
        cleanup.addLayout(clean_scope)
        options.addWidget(self.cleanup_row)
        self.cleanup_straighten.toggled.connect(self.update_mode)
        self.cleanup_trim.toggled.connect(self.update_mode)
        self.cleanup_padding.valueChanged.connect(self.update_mode)
        self.cleanup_ranges.textChanged.connect(self.update_mode)
        self.split_row=QWidget()
        split_layout=QVBoxLayout(self.split_row)
        split_layout.setContentsMargins(0,0,0,0)
        split_controls=QHBoxLayout()
        self.split_direction=CompressionBox()
        self.split_direction.setAccessibleName('Split order')
        for code,title in DIRECTIONS.items(): self.split_direction.addItem(title,code)
        self.split_direction.setCurrentIndex(self.split_direction.findData('lr'))
        split_controls.addWidget(self.split_direction)
        self.split_parts=QSpinBox()
        self.split_parts.setRange(2,12)
        self.split_parts.setValue(2)
        self.split_parts.setPrefix('Parts: ')
        self.split_parts.setMinimumWidth(110)
        self.split_parts.lineEdit().setTextMargins(12,0,12,0)
        self.split_parts.setAccessibleName('Parts per page')
        self.split_parts.setToolTip('Output parts per page. Drag each cut line in Preview split.')
        split_controls.addWidget(self.split_parts)
        self.split_position=QDoubleSpinBox(self.split_row)
        self.split_position.lineEdit().setTextMargins(12,0,12,0)
        self.split_position.setMinimumWidth(90)
        self.split_position.setDecimals(1)
        self.split_position.setRange(5,95)
        self.split_position.setSuffix('%')
        self.split_position.setValue(50)
        self.split_position.setAccessibleName('Split position')
        self.split_position.setToolTip('Position of the dividing line')
        self.split_position.hide()
        self.split_ranges=QLineEdit()
        self.split_ranges.setPlaceholderText('All pages')
        self.split_ranges.setToolTip('Pages to split, for example 2-15, 18. Leave blank for all pages.')
        self.split_ranges.setAccessibleName('Pages to split')
        self.split_ranges.setMinimumWidth(0)
        split_controls.addWidget(self.split_ranges,1)
        split_layout.addLayout(split_controls)
        self.split_preview=self.button('Preview split',self.preview_spreads,split_layout,'sliders-horizontal','text')
        options.addWidget(self.split_row)
        self.language_row=QWidget()
        languages=QHBoxLayout(self.language_row)
        languages.setContentsMargins(0,0,0,0)
        symbol=label();symbol.setPixmap(icon('languages',18).pixmap(18,18));languages.addWidget(symbol)
        languages.addWidget(label('Languages','section'))
        self.language_options=QGridLayout()
        self.language_options.setHorizontalSpacing(12)
        for column in range(3): self.language_options.setColumnStretch(column,1)
        languages.addLayout(self.language_options,1)
        self.languages={}
        options.addWidget(self.language_row)
        self.compression_row=QWidget()
        compression=QHBoxLayout(self.compression_row)
        compression.setContentsMargins(0,0,0,0)
        compression.addWidget(label('Quality','section'))
        self.compression=CompressionBox()
        self.compression.setAccessibleName('Compression level')
        self.compression.setMinimumWidth(160)
        for code,(title,_,_) in LEVELS.items(): self.compression.addItem(title,code)
        self.compression.setCurrentIndex(self.compression.findData('balanced'))
        self.compression.currentIndexChanged.connect(self.update_mode)
        self.compression.hide()
        self.compression_segments=OptionSegments(self.compression)
        compression.addWidget(self.compression_segments)
        self.compression_hint=label('','muted',True)
        compression.addWidget(self.compression_hint,1)
        options.addWidget(self.compression_row)
        layout.addWidget(self.options_panel)
        self.activity=label('','muted',True)
        self.activity.hide();layout.addWidget(self.activity)
        dock=QFrame()
        dock.setObjectName('actionDock')
        dock_layout=QVBoxLayout(dock)
        dock_layout.setContentsMargins(22,10,22,10)
        dock_layout.setSpacing(8)
        destination=QHBoxLayout()
        self.output_path=QLineEdit()
        self.output_path.setReadOnly(True)
        self.output_path.setPlaceholderText('Beside each original PDF')
        self.output_path.setAccessibleName('Output folder')
        self.output_path.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        self.output_path.addAction(icon('folder-open',17),QLineEdit.ActionPosition.LeadingPosition)
        self.output_path.setToolTip('Where your completed files will be saved')
        destination.addWidget(self.output_path,1)
        self.output_choose=IconButton('ellipsis','Choose output folder',self.choose_output_directory)
        destination.addWidget(self.output_choose)
        self.output_reset=IconButton('x','Reset output folder',lambda:self.set_output_directory(None))
        self.output_reset.setEnabled(False);self.output_reset.hide()
        destination.addWidget(self.output_reset)
        self.performance=CompressionBox()
        self.performance.setAccessibleName('Performance level')
        self.performance.setMinimumWidth(155)
        for code,profile in PROFILES.items(): self.performance.addItem(icon('gauge',16),profile.title,code)
        self.performance.setCurrentIndex(self.performance.findData('balanced'))
        self.performance.currentIndexChanged.connect(self.update_mode)
        destination.addWidget(self.performance)
        self.performance_hint=label('','muted',True)
        self.performance_hint.hide()
        dock_layout.addLayout(destination)
        run=QHBoxLayout()
        self.ready_label=label('Add PDFs to begin','section')
        self.ready_label.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        run.addWidget(self.ready_label,1)
        self.start_button=QPushButton('Process PDFs')
        self.start_button.setObjectName('primary')
        self.start_button.setAccessibleName('Process PDFs')
        self.start_button.clicked.connect(self.enqueue)
        self.start_button.setMinimumHeight(34)
        self.start_button.setMinimumWidth(150)
        run.addWidget(self.start_button)
        dock_layout.addLayout(run)
        scroll.set_dock(dock)
        self.split_position.valueChanged.connect(self.update_mode)
        self.split_parts.valueChanged.connect(self.update_split_parts)
        self.split_ranges.textChanged.connect(self.update_mode)
        self.queue = QFrame()
        self.queue.setObjectName("panel")
        queue = QVBoxLayout(self.queue)
        queue.setContentsMargins(0, 0, 0, 0)
        queue.setSpacing(0)
        header = QHBoxLayout()
        header.setContentsMargins(14, 5, 9, 5)
        self.queue_title = label("Processing", "filename")
        header.addWidget(self.queue_title)
        header.addStretch()
        self.clear_finished_button = self.button("Clear finished", self.clear_finished, header, "trash-2", "link")
        queue.addLayout(header)
        separator(queue)
        self.active_queue = QWidget()
        self.active_queue_layout = QVBoxLayout(self.active_queue)
        self.active_queue_layout.setContentsMargins(0, 0, 0, 0)
        self.active_queue_layout.setSpacing(0)
        queue.addWidget(self.active_queue)
        self.finished_heading = label("Completed", "filename")
        self.finished_heading.setContentsMargins(14, 10, 14, 5)
        queue.addWidget(self.finished_heading)
        self.finished_queue = QWidget()
        self.finished_queue_layout = QVBoxLayout(self.finished_queue)
        self.finished_queue_layout.setContentsMargins(0, 0, 0, 0)
        self.finished_queue_layout.setSpacing(0)
        queue.addWidget(self.finished_queue)
        self.queue.hide()
        layout.addWidget(self.queue)
        layout.addStretch()
        scroll.setWidget(page)
        self.tabs.addWidget(scroll)
        self.update_mode()

    def selected_operations(self):
        return {code for code, box in self.operations.items() if box.isChecked()}

    def choose_operation(self,code):
        # The wheel launches a task. Combining operations is an explicit action
        # from the task window, or a Shift-click for keyboard/mouse power users.
        if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.update_mode();return
        for name,button in self.operations.items():button.setChecked(name==code)
        self.update_mode()

    def merge_pdfs(self,checked=False,plan=None):
        from yuzufile.merge_ui import MergeDialog
        dialog=MergeDialog(self.ui_owner(),self.pending,plan=plan)
        try:
            while self.exec_tool(dialog)==QDialog.DialogCode.Accepted and dialog.result_plan:
                try:
                    self.set_output_directory(dialog.output_directory)
                    self.enqueue_organization({**dialog.result_plan,'action':'merge'});break
                except (OSError,ValueError) as error:dialog.message.setText(str(error));dialog.message.show()
        finally:dialog.deleteLater()

    def organize_pages(self, checked=False, plan=None):
        from yuzufile.organize_ui import OrganizeDialog
        dialog = OrganizeDialog(self.ui_owner(), self.pending, plan=plan)
        try:
            while self.exec_tool(dialog) == QDialog.DialogCode.Accepted and dialog.result_plan:
                try:
                    self.set_output_directory(dialog.output_directory)
                    self.enqueue_organization(dialog.result_plan)
                    break
                except (OSError,ValueError) as error:
                    # Keep edits available when a folder becomes unavailable.
                    dialog.message.setText(str(error))
        finally:
            dialog.deleteLater()

    def enqueue_organization(self, plan):
        job = self.store.create(Path(plan['sources'][0]['path']), 'organize', [],
                               performance=self.performance.currentData(), output_directory=self.output_directory,
                               page_plan=plan)
        self.session_jobs.append(job)
        self.performance.setCurrentIndex(self.performance.findData('balanced'))
        used={item['path'] for item in plan['sources']}
        self.pending=[path for path in self.pending if str(path) not in used]
        self.render_files()
        self.activity.hide()
        self.refresh_queue()
        QTimer.singleShot(0,self.scroll_to_results)
        return job

    def scroll_to_results(self):
        if self.queue.isVisible():
            self.workspace.widget().layout().activate()
            self.workspace.ensureWidgetVisible(self.queue,0,18)

    def current_split_settings(self):
        return split_settings({'direction': self.split_direction.currentData(),
                               'position': self.split_position.value(), 'pages': self.split_ranges.text(),
                               'parts': self.split_parts.value(),'cuts':self.split_cuts})

    def update_split_parts(self, *args):
        self.split_cuts=None
        self.update_mode()

    def preview_spreads(self):
        from yuzufile.spread_preview import SpreadPreview
        if not self.pending:
            return
        try:
            dialog = SpreadPreview(self.ui_owner(), self.pending, self.current_split_settings(), CompressionBox,
                                   self.current_cleanup_settings() if 'cleanup' in self.selected_operations() else None)
            if self.exec_tool(dialog) == QDialog.DialogCode.Accepted:
                config = dialog.config()
                self.split_direction.setCurrentIndex(self.split_direction.findData(config['direction']))
                self.split_position.setValue(config['position'])
                self.split_parts.setValue(config['parts'])
                self.split_ranges.setText(config['pages'])
                self.split_cuts=deepcopy(config.get('cuts'))
            dialog.deleteLater()
        except (OSError, ValueError) as error:
            self.error(str(error))

    def current_cleanup_settings(self):
        from yuzufile.cleanup import settings
        return settings(dict(straighten=self.cleanup_straighten.isChecked(),trim=self.cleanup_trim.isChecked(),
                             padding_mm=self.cleanup_padding.value(),pages=self.cleanup_ranges.text(),visual=deepcopy(self.cleanup_visual)))

    def preview_cleanup(self):
        from yuzufile.cleanup_preview import CleanupPreview
        if not self.pending:return
        try:
            dialog=CleanupPreview(self.ui_owner(),self.pending,self.current_cleanup_settings(),CompressionBox)
            if self.exec_tool(dialog)==QDialog.DialogCode.Accepted:
                config=dialog.config()
                self.cleanup_straighten.setChecked(config['straighten'])
                self.cleanup_trim.setChecked(config['trim'])
                self.cleanup_padding.setValue(round(config['padding_mm']))
                self.cleanup_ranges.setText(config['pages'])
                self.cleanup_visual=deepcopy(config.get('visual',{}))
                self.update_mode()
            dialog.deleteLater()
        except (OSError,ValueError) as error:
            self.error(str(error))

    def choose_output_directory(self):
        directory = QFileDialog.getExistingDirectory(self.ui_owner(), "Choose output folder",
                    str(self.output_directory or Path.home()))
        if directory:
            self.set_output_directory(Path(directory))

    def set_output_directory(self, directory):
        self.output_directory = Path(directory).absolute() if directory else None
        text = str(self.output_directory) if self.output_directory else ""
        self.output_path.setText(text)
        self.output_path.setToolTip(text or "Each output is saved beside its original PDF, even across different folders.")
        self.output_reset.setEnabled(self.output_directory is not None)
        self.output_reset.setVisible(self.output_directory is not None)

    def operation_changed(self,code,checked):
        if checked:
            conflicts={'ocr','markdown','docx'} if code=='remove_ocr' else {'remove_ocr'} if code in {'ocr','markdown','docx'} else set()
            for conflict in conflicts:
                button=self.operations.get(conflict)
                if button is not None and button.isChecked():button.setChecked(False)
        self.update_mode()

    def update_mode(self):
        selected = self.selected_operations()
        self.remove_ocr_row.setVisible('remove_ocr' in selected)
        self.split_row.setVisible('split' in selected)
        self.cleanup_row.setVisible('cleanup' in selected)
        self.cleanup_preview.setEnabled(bool(self.pending))
        self.cleanup_padding.setEnabled(self.cleanup_trim.isChecked())
        self.split_preview.setEnabled(bool(self.pending))
        needs_languages = bool(selected & {"ocr", "markdown", "docx"})
        self.language_row.setVisible(needs_languages)
        self.compression.setEnabled("compress" in selected)
        self.compression_row.setVisible("compress" in selected)
        self.options_panel.setVisible(bool(selected & {"ocr","markdown","docx","compress","split","cleanup","remove_ocr"}))
        level = self.compression.currentData()
        self.compression.setToolTip(LEVELS[level][1])
        self.compression_hint.setText({"lossless": "Keep original image quality",
            "balanced": "Good balance between size and quality",
            "maximum": "Smallest size, lower image quality"}[level])
        profile = PROFILES[self.performance.currentData()]
        self.performance_hint.setText(profile.hint)
        self.performance.setToolTip("Performance: "+profile.hint+". Recognition quality stays the same.")
        valid = not needs_languages or any(box.isChecked() for box in self.languages.values())
        split_error = ''
        if 'split' in selected:
            try:
                self.current_split_settings()
            except ValueError as error:
                split_error = str(error)
                valid = False
        if 'cleanup' in selected:
            try:self.current_cleanup_settings()
            except ValueError as error:
                split_error=str(error)
                valid=False
        self.start_button.setEnabled(bool(self.pending and selected and valid))
        self.start_button.setToolTip(split_error or ("Select a language for scanned text." if not valid else ""))
        action={frozenset({'ocr'}):'Make searchable',frozenset({'markdown'}):'Export Markdown',
                frozenset({'cleanup'}):'Clean PDFs',frozenset({'docx'}):'Export Word',frozenset({'compress'}):'Compress PDFs',frozenset({'split'}):'Split spreads',frozenset({'remove_ocr'}):'Remove OCR'}.get(frozenset(selected),'Process PDFs')
        self.start_button.setText(action)
        self.ready_label.setText(('Add PDFs to begin' if not self.pending else
            'Choose a tool' if not selected else 'Check options' if split_error else 'Choose a language' if not valid else
            f"{len(self.pending)} {'PDF' if len(self.pending)==1 else 'PDFs'} ready"))


    def refresh_languages(self):
        while self.language_options.count():
            item = self.language_options.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.languages.clear()
        available = installed_languages()
        ordered = [code for code in ("eng", "fra", "ara") if code in available]
        ordered += [code for code in available if code not in ordered]
        for index, code in enumerate(ordered):
            box = CheckBox(NAMES.get(code, code))
            box.setChecked(code == "eng")
            box.toggled.connect(self.update_mode)
            self.language_options.addWidget(box, index // 3, index % 3)
            self.languages[code] = box
        if not available:
            self.language_options.addWidget(label("No OCR languages available", "muted"), 0, 0, 1, 3)
        self.update_mode()

    def pick_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self.ui_owner(), "Choose PDFs", "", "PDF files (*.pdf)")
        self.add_files(paths)

    def add_files(self, paths):
        for value in paths:
            path = Path(value).resolve()
            if path.suffix.lower() == ".pdf" and path.is_file() and path not in self.pending:
                self.pending.append(path)
        self.render_files()

    def render_files(self):
        self.files.clear()
        for path in self.pending:
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 38))
            row = QWidget()
            content = QHBoxLayout(row)
            content.setContentsMargins(9, 2, 7, 2)
            document_icon = QLabel()
            document_icon.setPixmap(pdf_icon(22).pixmap(QSize(22, 22)))
            content.addWidget(document_icon)
            filename = QLabel(path.name)
            filename.setToolTip(str(path))
            filename.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            content.addWidget(filename, 1)
            try:
                size = size_label(path.stat().st_size)
            except OSError:
                size = "File unavailable"
            size_text = QLabel(size)
            size_text.setObjectName("muted")
            content.addWidget(size_text)
            remove = self.button("", lambda checked=False, file=path: self.remove_file(file), content)
            remove.setIcon(icon("x", 15))
            remove.setObjectName("remove")
            remove.setFixedSize(29, 29)
            remove.setAccessibleName(f"Remove {path.name}")
            remove.setToolTip("Remove file")
            self.files.addItem(item)
            self.files.setItemWidget(item, row)
        self.files.setFixedHeight(min(4, len(self.pending)) * 38 + 2)
        self.file_count.setText(f"{len(self.pending)} {'document' if len(self.pending) == 1 else 'documents'}" if self.pending else "PDF files · Multiple files supported")
        count=len(self.pending)
        self.drop_title.setText(f"{count} {'PDF' if count==1 else 'PDFs'}" if count else 'Add PDFs')
        self.drop_hint.setText('+ add more' if count else 'or drop here')
        self.drop_icon.setPixmap(icon('file-text' if count else 'file-plus',30,COLORS['icon']).pixmap(30,30))
        self.remove_all.setEnabled(bool(self.pending))
        self.files.setVisible(bool(self.pending))
        self.update_mode()

    def remove_file(self, path):
        if path in self.pending:
            self.pending.remove(path)
        self.render_files()

    def clear_files(self):
        self.pending.clear()
        self.render_files()

    def enqueue(self):
        self.update_mode()
        if not self.start_button.isEnabled():
            return
        selected = self.selected_operations()
        languages = [code for code, box in self.languages.items() if box.isChecked()] if selected & {"ocr", "markdown", "docx"} else []
        try:
            for path in list(self.pending):
                job = self.store.create(path, mode_for(selected), languages, self.compression.currentData(),
                                        self.performance.currentData(), self.output_directory,
                                        self.current_split_settings() if 'split' in selected else None,
                                        cleanup_settings=self.current_cleanup_settings() if 'cleanup' in selected else None)
                self.session_jobs.append(job)
                self.pending.remove(path)
            self.activity.hide()
        except (OSError, ValueError) as error:
            self.activity.setText(str(error))
            self.activity.show()
        self.render_files()
        # Initial choices are fixed, never persisted between sessions or batches.
        for code, box in self.languages.items():
            box.setChecked(code == "eng")
        self.performance.setCurrentIndex(self.performance.findData("balanced"))
        self.refresh_queue()
        QTimer.singleShot(0,self.scroll_to_results)


    def operation_caption(self, job):
        titles={'OCR':'Searchable PDF','Compress':'Smaller PDF','Organize pages':'Arrange pages'}
        text = ' + '.join(titles.get(part,part) for part in mode_label(job['mode']).split(' + '))
        if job['mode']=='organize':
            plan=json.loads(job['page_plan'])
            if plan.get('action')=='merge':text='Merge PDFs'
            text+=f" · {len(plan['pages'])} pages · {len(plan['sources'])} PDF(s)"
        if 'split' in MODES[job['mode']]:
            config = split_settings(json.loads(job['split_settings']))
            text += f" · {config['parts']} parts · " + DIRECTIONS[config['direction']]
        if "compress" in MODES[job["mode"]]:
            text += f" ({LEVELS[job['compression']][0]})"
        return text

    def job_name(self,job):
        name=Path(job['source']).name
        if job['mode']=='organize':
            count=len(json.loads(job['page_plan'])['sources'])
            if count>1:
                name+=f' + {count-1} PDF(s)'
        return name

    def job_search_names(self,job):
        if job['mode']=='organize':
            return '\n'.join(Path(source['path']).name for source in json.loads(job['page_plan'])['sources'])
        return Path(job['source']).name

    def create_card(self, job):
        card = QFrame()
        card.setObjectName("queueRow")
        content = QVBoxLayout(card)
        content.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        content.setContentsMargins(14, 5, 14, 5)
        content.setSpacing(5)
        top = QHBoxLayout()
        top.setSpacing(10)
        symbol = label()
        symbol.setFixedSize(22, 24)
        top.addWidget(symbol)
        info = QVBoxLayout()
        info.setSpacing(1)
        filename = label(self.job_name(job))
        filename.setToolTip(job["source"])
        filename.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        info.addWidget(filename)
        caption = label(self.operation_caption(job), "muted")
        caption.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        info.addWidget(caption)
        top.addLayout(info, 2)
        meter = QWidget()
        meter_layout = QHBoxLayout(meter)
        meter_layout.setContentsMargins(0, 0, 0, 0)
        progress = SegmentedProgressBar()
        progress.setRange(0, 100)
        progress.setTextVisible(False)
        progress.setMinimumWidth(105)
        meter_layout.addWidget(progress, 1)
        status = label("Waiting…", "muted")
        status.setFixedWidth(72)
        status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        meter_layout.addWidget(status)
        top.addWidget(meter, 2)
        cancel = self.button("Cancel", lambda checked=False, jid=job["id"]: self.cancel_job(jid), top)
        actions = QWidget()
        action_layout = QHBoxLayout(actions)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(6)
        top.addWidget(actions)
        content.addLayout(top)
        savings = label("", "muted")
        savings.setTextFormat(Qt.TextFormat.RichText)
        content.addWidget(savings)
        details_row = QHBoxLayout()
        details_toggle = self.button("Show details", lambda: None, details_row, "chevron-right", "link")
        details_toggle.setCheckable(True)
        details_toggle.setAccessibleName(f"Processing details for {self.job_name(job)}")
        details_toggle.toggled.connect(lambda expanded, jid=job["id"]: self.toggle_card_details(jid))
        details_row.addStretch()
        content.addLayout(details_row)
        details = label("", "muted", True)
        details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        details.hide()
        details_toggle.hide()
        content.addWidget(details)
        self.active_queue_layout.addWidget(card)
        data = {"widget": card, "icon": symbol, "caption": caption, "status": status,
                "cancel": cancel, "progress": progress, "meter": meter, "details": details,
                "actions": actions, "layout": action_layout, "signature": None, "finished": False,
                "savings": savings, "details_toggle": details_toggle, "message_count": 0}
        self.cards[job["id"]] = data
        return data

    def toggle_card_details(self, job_id):
        card = self.cards[job_id]
        toggle = card["details_toggle"]
        expanded = toggle.isChecked()
        toggle.setText(f"{'Hide' if expanded else 'Show'} details ({card['message_count']})")
        toggle.setIcon(icon("chevron-down" if expanded else "chevron-right", 16, COLORS["accent"]))
        card["details"].setVisible(expanded and bool(card["message_count"]))

    def refresh_queue(self):
        active_count = finished_count = completed_count = 0
        for job_id in list(self.session_jobs):
            try:
                job = self.store.get(job_id)
            except KeyError:
                self.discard_card(job_id)
                continue
            card = self.cards.get(job_id) or self.create_card(job)
            finished = job["state"] in TERMINAL
            if finished != card["finished"]:
                (self.finished_queue_layout if finished else self.active_queue_layout).addWidget(card["widget"])
                card["finished"] = finished
            active_count += not finished
            finished_count += finished
            completed_count += job["state"] == "succeeded"
            symbol, color = ("circle-check", COLORS["success"]) if job["state"] == "succeeded" else ("info", COLORS["error"]) if finished else ("refresh-cw", COLORS["accent"]) if job["state"] == "running" else ("clock", COLORS["icon"])
            card["icon"].setPixmap(icon(symbol, 21, color).pixmap(QSize(21, 21)))
            card["meter"].setVisible(not finished)
            card["cancel"].setVisible(not finished)
            percent = self.supervisor.progress if self.supervisor.active == job_id else 0
            card["progress"].setValue(percent)
            card["status"].setText(f"{percent}%" if job["state"] == "running" else "Waiting…")
            card["caption"].setText(job["stage"] if job["state"] == "running" else self.operation_caption(job))
            card["caption"].setToolTip(self.operation_caption(job) + " · " + job["stage"])
            metadata = json.loads(job["metadata"])
            messages = [job["error"] or STATUS[job["state"]]] if finished and job["state"] != "succeeded" else []
            if "compression" in metadata:
                change = metadata['saved_percent']
                larger = metadata['output_bytes'] > metadata['input_bytes']
                color = COLORS["error"] if larger else COLORS["success"]
                direction = "larger" if larger else "smaller"
                card["savings"].setText(f"Original: {size_label(metadata['input_bytes'])} &nbsp; "
                    f"Output: {size_label(metadata['output_bytes'])} &nbsp; "
                    f"<span style='color:{color}'>({abs(change):.1f}% {direction})</span>")
            card["savings"].setVisible("compression" in metadata)
            messages.extend(metadata.get("warnings", []))
            card["details"].setText("\n".join(messages))
            card["message_count"] = len(messages)
            card["details_toggle"].setVisible(bool(messages))
            if not messages:
                card["details_toggle"].setChecked(False)
            self.toggle_card_details(job_id)
            signature = (job["state"], self.artifact_signature(job_id))
            if signature != card["signature"]:
                card["signature"] = signature
                while card["layout"].count():
                    item = card["layout"].takeAt(0)
                    if item.widget():
                        item.widget().hide()
                        item.widget().deleteLater()
                if finished:
                    if job["state"] == "succeeded":
                        for kind, title, glyph in (("pdf", "Open PDF", "file-text"), ("markdown", "Open Markdown", "file-text"), ("docx", "Open Word", "file-text")):
                            if self.artifact_path(job_id, kind):
                                self.button(title, lambda checked=False, jid=job_id, k=kind: self.open_artifact(jid, k), card["layout"], glyph)
                        folder = self.button("Open Folder", lambda checked=False, jid=job_id: self.open_job_folder(jid), card["layout"], "folder-open")
                        folder.setEnabled((self.store.job_dir(job_id) / "result").is_dir())
                    else:
                        self.button("Process Again", lambda checked=False, jid=job_id: self.retry_job(jid), card["layout"], "refresh-cw", "retry")
                    more = self.button("", lambda: None, card["layout"], "ellipsis")
                    more.setFixedWidth(30)
                    more.setAccessibleName(f"More actions for {Path(job['source']).name}")
                    more.clicked.connect(lambda checked=False, jid=job_id, b=more: self.show_job_menu(jid, b))
                card["actions"].setVisible(finished)
        if not self.pending:
            self.ready_label.setText(f"{active_count} {'PDF' if active_count==1 else 'PDFs'} processing" if active_count else
                f"{completed_count} {'PDF' if completed_count==1 else 'PDFs'} completed" if completed_count else
                'Review processing results' if finished_count else 'Add PDFs to begin')
        self.queue_title.setText(f"Processing ({active_count} {'file' if active_count == 1 else 'files'})" if active_count else "Processing")
        self.clear_finished_button.setEnabled(bool(finished_count))
        self.finished_heading.setText(f"Completed ({completed_count})" if completed_count == finished_count else f"Finished ({finished_count})")
        self.finished_heading.setVisible(bool(finished_count))
        self.finished_queue.setVisible(bool(finished_count))
        self.queue.setVisible(bool(self.session_jobs))

    def discard_card(self, job_id):
        if job_id in self.session_jobs:
            self.session_jobs.remove(job_id)
        card = self.cards.pop(job_id, None)
        if card:
            card["widget"].hide()
            card["widget"].deleteLater()

    def clear_finished(self):
        for job_id in list(self.session_jobs):
            try:
                finished = self.store.get(job_id)["state"] in TERMINAL
            except KeyError:
                finished = True
            if finished:
                self.discard_card(job_id)
        self.refresh_queue()

    def poll(self):
        self.supervisor.tick()
        self.refresh_queue()
        if self.supervisor.last_finished and self.supervisor.last_finished != self.last_revealed_job:
            self.last_revealed_job=self.supervisor.last_finished
            if not self.pending:
                QTimer.singleShot(0,self.scroll_to_results)

    def cancel_job(self, job_id):
        try:
            self.supervisor.cancel(job_id)
            self.refresh_queue()
        except Exception as error:
            self.error(f"Could not cancel processing: {error}")


    def artifact_path(self, job_id, kind):
        for artifact in self.store.artifacts(job_id):
            if artifact["kind"] == kind and not artifact["deleted"]:
                path = self.store.artifact_path(job_id,artifact)
                if path.is_file():
                    return path
        return None

    def artifact_signature(self, job_id):
        return tuple((a["path"], a["deleted"], self.store.artifact_path(job_id,a).is_file()) for a in self.store.artifacts(job_id))

    def status_badge(self, state):
        badge = label(STATUS[state], "badge")
        foreground, background = (COLORS["success"], COLORS["success_soft"]) if state == "succeeded" else (COLORS["error"], COLORS["error_soft"]) if state in {"failed", "cancelled"} else (COLORS["accent_hover"], COLORS["accent_soft"]) if state == "running" else (COLORS["muted"], COLORS["hover"])
        badge.setStyleSheet(f"color: {foreground}; background: {background};")
        return badge

    def result_size(self, job):
        metadata = json.loads(job["metadata"])
        if "compression" in metadata:
            def compact(value):
                return f"{value / 1_000_000:.1f} MB" if value >= 1_000_000 else f"{value / 1000:.0f} KB"
            larger = metadata['output_bytes'] > metadata['input_bytes']
            color = COLORS["error"] if larger else COLORS["success"]
            change = "larger" if larger else f"{metadata['saved_percent']:.0f}%"
            return (f"{compact(metadata['input_bytes'])} → {compact(metadata['output_bytes'])} "
                    f"<span style='color:{color}'>({change})</span>")
        try:
            original = size_label(Path(job["source"]).stat().st_size)
        except OSError:
            original = "—"
        return original + (" → —" if job["state"] != "succeeded" else "")


    def create_job_menu(self, job_id):
        job = self.store.get(job_id)
        active = job["state"] in {"queued", "running"}
        menu = QMenu(self.ui_owner())
        def entry(text, glyph, callback, enabled=True, danger=False):
            action = menu.addAction(icon(glyph, 16, COLORS['error'] if danger else COLORS["icon"]), text)
            action.setEnabled(enabled)
            action.triggered.connect(lambda checked=False: callback())
        entry("View Details", "info", lambda: self.view_details(job_id))
        entry("Process Again", "play", lambda: self.retry_job(job_id), not active)
        if active:
            entry("Cancel", "x", lambda: self.cancel_job(job_id))
        menu.addSeparator()
        entry("Open PDF", "file-text", lambda: self.open_artifact(job_id, "pdf"), bool(self.artifact_path(job_id, "pdf")))
        entry("Open Markdown", "file-text", lambda: self.open_artifact(job_id, "markdown"), bool(self.artifact_path(job_id, "markdown")))
        entry("Open Word", "file-text", lambda: self.open_artifact(job_id, "docx"), bool(self.artifact_path(job_id, "docx")))
        entry("Open Folder", "folder-open", lambda: self.open_job_folder(job_id), (self.store.job_dir(job_id) / "result").is_dir())
        menu.addSeparator()
        entry("Move Generated Files to Recycle Bin", "trash-2", lambda: self.delete_outputs(job_id),
              not active and any(not a["deleted"] for a in self.store.artifacts(job_id)), True)
        return menu

    def show_job_menu(self, job_id, button):
        menu = self.create_job_menu(job_id)
        menu.aboutToHide.connect(menu.deleteLater)
        self.job_menu = menu
        menu.popup(button.mapToGlobal(button.rect().bottomRight()) - QPoint(menu.sizeHint().width(), 0))

    def view_details(self, job_id):
        job = self.store.get(job_id)
        lines = [job["source"], f"Status: {STATUS[job['state']]}", f"Operations: {self.operation_caption(job)}",
                 "Performance: " + PROFILES[job["performance"]].title,
                 "Languages: " + (", ".join(NAMES.get(c, c) for c in json.loads(job["languages"])) or "None")]
        if job["error"]:
            lines.append(job["error"])
        metadata = json.loads(job["metadata"])
        if job['mode']=='organize':
            plan=json.loads(job['page_plan'])
            lines.append(f"Organized {len(plan['pages'])} pages from {len(plan['sources'])} PDF(s)")
            lines.extend(source['path'] for source in plan['sources'])
        if metadata:
            lines.append(f"Pages: {metadata.get('pages')} · Time: {metadata.get('seconds')} s")
            if "compression" in metadata:
                lines.append(compression_summary(metadata))
            if 'cleanup' in metadata:
                clean=metadata['cleanup']
                lines.append(f"Cleanup: {clean['straightened_pages']} straightened · {clean['trimmed_pages']} trimmed")
            lines.extend(metadata.get("warnings", []))
        for artifact in self.store.artifacts(job_id):
            path = self.store.artifact_path(job_id,artifact)
            state = "deleted" if artifact["deleted"] else "available" if path.is_file() else "missing"
            lines.append(f"{artifact['kind']}: {path} [{state}]")
        dialog = QDialog(self.ui_owner())
        dialog.setWindowTitle("Processing details")
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.resize(640, 430)
        layout = QVBoxLayout(dialog)
        browser = QTextBrowser()
        browser.setPlainText("\n\n".join(lines))
        layout.addWidget(browser)
        self.button("Close", dialog.accept, layout)
        self.detail_dialog = dialog
        dialog.open()
        return dialog

    def retry_job(self, job_id):
        job = self.store.get(job_id)
        self.tabs.setCurrentIndex(0)
        if job['mode']=='organize':
            self.set_output_directory(job['output_directory'] or None)
            self.performance.setCurrentIndex(self.performance.findData(job['performance']))
            plan=json.loads(job['page_plan'])
            if self.shell is not None and self.shell.resident:
                self.shell.open_tool('merge' if plan.get('action')=='merge' else 'arrange',plan=plan)
                return
            self.reveal_tools()
            self.merge_pdfs(plan=plan) if plan.get('action')=='merge' else self.organize_pages(plan=plan)
            return
        self.reveal_tools()
        if not Path(job["source"]).is_file():
            self.activity.setText("The original PDF is no longer available. Add it again to process a new copy.")
            self.activity.show()
            return
        self.add_files([job["source"]])
        for code, box in self.operations.items():
            box.setChecked(code in MODES[job["mode"]])
        self.refresh_languages()
        requested_languages=set(json.loads(job['languages']))
        for code,box in self.languages.items():
            box.setChecked(code in requested_languages)
        self.compression.setCurrentIndex(self.compression.findData(job["compression"]))
        self.performance.setCurrentIndex(self.performance.findData(job["performance"]))
        self.set_output_directory(job["output_directory"] or None)
        config = split_settings(json.loads(job['split_settings']))
        self.split_direction.setCurrentIndex(self.split_direction.findData(config['direction']))
        self.split_position.setValue(config['position'])
        self.split_parts.setValue(config['parts'])
        self.split_ranges.setText(config['pages'])
        self.split_cuts=deepcopy(config.get('cuts'))
        from yuzufile.cleanup import settings as cleanup_settings
        clean=cleanup_settings(json.loads(job['cleanup_settings']))
        self.cleanup_straighten.setChecked(clean['straighten'])
        self.cleanup_trim.setChecked(clean['trim'])
        self.cleanup_padding.setValue(round(clean['padding_mm']))
        self.cleanup_ranges.setText(clean['pages'])
        self.cleanup_visual=deepcopy(clean.get('visual',{}))
        self.activity.hide()
        self.update_mode()

    def open_path(self, path):
        if not Path(path).exists() or not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            self.error("This file or folder could not be opened. It may have been moved or deleted.")

    def open_artifact(self, job_id, kind):
        path = self.artifact_path(job_id, kind)
        if path:
            self.open_path(path)
        else:
            self.error("This generated file is missing or has been deleted.")

    def open_job_folder(self, job_id):
        self.open_path(self.store.result_directory(job_id))


    def delete_outputs(self, job_id):
        paths = [str(self.store.artifact_path(job_id,a)) for a in self.store.artifacts(job_id) if not a["deleted"]]
        if QMessageBox.question(self.ui_owner(), "Delete generated files?", "Move these generated files to the Recycle Bin?\n\n" + "\n".join(paths)) == QMessageBox.StandardButton.Yes:
            try:
                self.store.delete_outputs(job_id)
            except Exception as error:
                self.error(f"Some files could not be deleted: {error}")
            self.refresh_queue()

    def error(self, message):
        QMessageBox.warning(self.ui_owner(), "yuzufile", message)

    def dragEnterEvent(self, event):
        from yuzufile.desktop_drag import pdf_paths,accept_copy
        if pdf_paths(event.mimeData()):accept_copy(event)

    def dropEvent(self, event):
        from yuzufile.desktop_drag import pdf_paths,accept_copy
        paths=pdf_paths(event.mimeData())
        if paths and accept_copy(event):
            self.add_files(paths)
            self.tabs.setCurrentIndex(0)

    def closeEvent(self, event):
        if self._closed:event.accept();return
        if self.shell is not None and not self.shell.closing:
            if self.shell.resident:self.shell.dismiss_to_tray()
            else:self.shell.show()
            self.hide();event.ignore();return
        active = any(job["state"] in {"queued", "running"} for job in self.store.jobs())
        if active and QMessageBox.question(self.ui_owner(), "Close yuzufile?", "Cancel unfinished conversions and close?") != QMessageBox.StandardButton.Yes:
            event.ignore()
            return
        self.timer.stop()
        self.supervisor.shutdown()
        self._closed = True
        self.store.close()
        event.accept()


def main(home: Path | None = None) -> int:
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName("yuzufile")
    app.setStyle("Fusion")
    store = None
    window = None
    instance = None
    tray = None
    gesture = None
    try:
        from yuzufile.desktop_instance import DesktopInstance
        from yuzufile.storage import default_home
        instance = DesktopInstance((home or default_home()).resolve())
        if instance.request_show():return 0
        try:
            store = Store(home)
        except ValueError:
            # Another desktop instance may still be building its widgets before
            # its activation listener is ready. Keep the library lock intact.
            if instance.request_show(timeout_ms=1500,retry=True):return 0
            raise
        store.recover()
        window = Window(store)
        from yuzufile.shaped_shell import FloatingShell
        shell = FloatingShell(window)
        from yuzufile.system_tray import TrayController
        from yuzufile.desktop_drag import DesktopDragController
        tray = TrayController(app, window, shell)
        shell.tray_controller = tray
        gesture = DesktopDragController(app, window, shell)
        tray.gesture_enabled_changed.connect(gesture.set_enabled)
        tray.quitting.connect(gesture.shutdown)
        tray.gesture_action.setEnabled(gesture.available)
        instance.listen(tray.show_window)
        app.aboutToQuit.connect(instance.shutdown)
        if tray.start():
            # Normal launch is a resident utility, summoned by the tray or a
            # PDF drag. No terminal, startup registration or extra setup.
            gesture.start()
        else:
            shell.show()
            gesture.start()
    except Exception as error:
        if gesture is not None:gesture.shutdown()
        if tray is not None:tray.shutdown()
        if instance is not None:instance.shutdown()
        if window is not None:window.timer.stop()
        if store is not None:store.close()
        QMessageBox.critical(None, "yuzufile could not start", str(error))
        return 1
    try:return app.exec()
    finally:
        gesture.shutdown();tray.shutdown();instance.shutdown()
        if not window._closed:
            window.timer.stop();window.supervisor.shutdown();store.close()


if __name__ == "__main__":
    raise SystemExit(main())
