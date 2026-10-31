"""On-demand, single-page preview; no OCR or full-document rasterization."""
import math
from PySide6.QtCore import Qt, QRectF, QPointF,QSizeF,QTimer,Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QDoubleSpinBox, QHBoxLayout,
                              QLabel, QLineEdit, QSpinBox, QVBoxLayout, QWidget, QPushButton,QSizePolicy,QFrame)
import pymupdf

from yuzufile.spreads import DIRECTIONS, selected_pages, settings
from yuzufile.ui_style import COLORS
from yuzufile.split_viewport import SplitViewport
from yuzufile.tool_window import ToolDialog
from yuzufile.preview_tools import ZoomControls
from yuzufile.ui_components import IconButton


class SplitCanvas(QWidget):
    moved = Signal(float)
    cuts_moved = Signal(object)
    line_selected = Signal(int)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(240, 180)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.pixmap = QPixmap()
        self.config = settings()
        self.selected = True
        self.page_rect = QRectF()
        self.active_cut=None
        self.focused_cut=0;self.display_size=None;self.viewport_owner=None
        self.pan_start=None;self.space_down=False
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName('Drag dividing lines to split the page')

    def fit_rect(self):
        if self.pixmap.isNull() and self.display_size is None:return QRectF()
        size=self.display_size
        if size is None:
            available=self.rect().adjusted(16,16,-16,-16)
            size=QSizeF(self.pixmap.size().scaled(available.size(),Qt.AspectRatioMode.KeepAspectRatio))
        return QRectF((self.width()-size.width())/2,(self.height()-size.height())/2,size.width(),size.height())

    def visible_rect(self):
        return self.viewport_owner.visible_canvas_rect() if self.viewport_owner else QRectF(self.rect())

    def handle_rects(self):
        rect=self.fit_rect();visible=self.visible_rect().intersected(rect)
        if visible.isEmpty():return []
        if self.config['direction'] in {'lr','rl'}:
            y=visible.center().y()
            return [QRectF(rect.left()+rect.width()*c/100-9,y-26,18,52) for c in self.cuts()]
        x=visible.center().x()
        return [QRectF(x-26,rect.top()+rect.height()*c/100-9,52,18) for c in self.cuts()]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(COLORS['canvas']))
        if self.pixmap.isNull():
            return
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.page_rect=self.fit_rect()
        painter.drawPixmap(self.page_rect.toRect(), self.pixmap)
        if not self.selected:
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(COLORS['accent']), 2))
        rect = self.page_rect
        count = self.config['parts']
        boundaries = [0,*[c/100 for c in self.cuts()],1]
        labels = [str(n) for n in range(1, count+1)]
        if self.config['direction'] in {'rl','bt'}:
            labels.reverse()
        if self.config['direction'] in {'lr', 'rl'}:
            for index,fraction in enumerate(boundaries[1:-1]):
                cut = rect.left() + rect.width()*fraction
                painter.setPen(QPen(QColor(COLORS['accent']),3 if index==self.focused_cut else 2))
                painter.drawLine(int(cut), int(rect.top()), int(cut), int(rect.bottom()))
                painter.setBrush(QColor('white'));painter.drawRoundedRect(self.handle_rects()[index],7,7)
            positions = [rect.left()+rect.width()*(a+b)/2 for a,b in zip(boundaries,boundaries[1:])]
            for x, text in zip(positions, labels):
                y=max(rect.top()+8,self.visible_rect().top()+8)
                painter.drawText(QRectF(x-14, y, 28, 24), Qt.AlignmentFlag.AlignCenter, text)
        else:
            for index,fraction in enumerate(boundaries[1:-1]):
                cut = rect.top() + rect.height()*fraction
                painter.setPen(QPen(QColor(COLORS['accent']),3 if index==self.focused_cut else 2))
                painter.drawLine(int(rect.left()), int(cut), int(rect.right()), int(cut))
                painter.setBrush(QColor('white'));painter.drawRoundedRect(self.handle_rects()[index],7,7)
            positions = [rect.top()+rect.height()*(a+b)/2 for a,b in zip(boundaries,boundaries[1:])]
            for y, text in zip(positions, labels):
                x=max(rect.left()+8,self.visible_rect().left()+8)
                painter.drawText(QRectF(x, y-12, 28, 24), Qt.AlignmentFlag.AlignCenter, text)

    def cuts(self):
        return self.config.get('cuts',[self.config['position']] if self.config['parts']==2 else [100*n/self.config['parts'] for n in range(1,self.config['parts'])])

    def emit_cut(self,value):
        cuts=list(self.cuts());index=self.active_cut if self.active_cut is not None else min(self.focused_cut,len(cuts)-1)
        minimum=5 if self.config['parts']==2 else 2
        cuts[index]=max((cuts[index-1] if index else 0)+minimum,
                        min((cuts[index+1] if index+1<len(cuts) else 100)-minimum,value))
        self.config={**self.config,'cuts':cuts}
        if len(cuts)==1:self.config['position']=cuts[0];self.moved.emit(cuts[0])
        self.cuts_moved.emit(cuts);self.update()

    def move_line(self, event):
        if self.selected and self.active_cut is not None:
            rect = self.fit_rect()
            fraction = ((event.position().x()-rect.left())/rect.width() if self.config['direction'] in {'lr','rl'}
                        else (event.position().y()-rect.top())/rect.height())
            value=fraction*100
            self.emit_cut(value)

    def hit_cut(self,point):
        rect=self.fit_rect()
        if not self.selected or not rect.contains(point):return None
        vertical=self.config['direction'] in {'lr','rl'}
        distances=[abs((point.x()-rect.left())-rect.width()*c/100) if vertical else
                   abs((point.y()-rect.top())-rect.height()*c/100) for c in self.cuts()]
        index=min(range(len(distances)),key=distances.__getitem__)
        return index if distances[index]<=12 else None

    def mousePressEvent(self, event):
        self.setFocus()
        if self.viewport_owner and (event.button()==Qt.MouseButton.MiddleButton or
                event.button()==Qt.MouseButton.LeftButton and self.space_down):
            self.pan_start=QPointF(event.globalPosition());self.setCursor(Qt.CursorShape.ClosedHandCursor);return
        if event.button() == Qt.MouseButton.LeftButton:
            self.active_cut=self.hit_cut(event.position())
            if self.active_cut is not None:
                self.focused_cut=self.active_cut;self.line_selected.emit(self.focused_cut)
                self.move_line(event)
            elif self.viewport_owner:
                self.pan_start=QPointF(event.globalPosition());self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self.pan_start is not None and self.viewport_owner:
            point=QPointF(event.globalPosition());self.viewport_owner.pan_by(point-self.pan_start)
            self.pan_start=point;return
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.move_line(event)
        elif self.hit_cut(event.position()) is not None and not self.space_down:
            self.setCursor(Qt.CursorShape.SizeHorCursor if self.config['direction'] in {'lr','rl'} else Qt.CursorShape.SizeVerCursor)
        else:self.setCursor(Qt.CursorShape.OpenHandCursor if self.viewport_owner else Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self,event):
        self.active_cut=None;self.pan_start=None
        self.setCursor(Qt.CursorShape.OpenHandCursor if self.viewport_owner else Qt.CursorShape.ArrowCursor)

    def wheelEvent(self,event):
        if self.viewport_owner and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            anchor=self.mapTo(self.viewport_owner.viewport(),event.position().toPoint())
            self.viewport_owner.set_zoom(self.viewport_owner.zoom*(1.2 if event.angleDelta().y()>0 else 1/1.2),anchor)
            event.accept()
        else:event.ignore()

    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Space:
            self.space_down=True;self.setCursor(Qt.CursorShape.OpenHandCursor);event.accept();return
        if self.selected and event.key() in (Qt.Key.Key_Left,Qt.Key.Key_Right,Qt.Key.Key_Up,Qt.Key.Key_Down):
            delta=-1 if event.key() in (Qt.Key.Key_Left,Qt.Key.Key_Up) else 1
            if not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:delta*=.1
            self.emit_cut(self.cuts()[min(self.focused_cut,len(self.cuts())-1)]+delta);event.accept()
        else:super().keyPressEvent(event)

    def keyReleaseEvent(self,event):
        if event.key()==Qt.Key.Key_Space:self.space_down=False;event.accept()
        else:super().keyReleaseEvent(event)

    def focusOutEvent(self,event):
        self.space_down=False;self.pan_start=None;super().focusOutEvent(event)


class SpreadPreview(ToolDialog):
    def __init__(self, parent, paths, config, combo_factory, cleanup_config=None):
        super().__init__(parent,title='Split spreads')
        self.cleanup_config=cleanup_config
        self.cuts=config.get('cuts')
        screen = self.screen().availableGeometry()
        self.resize(min(1320, int(screen.width()*.94)), min(1000, int(screen.height()*.94)))
        self.setMinimumSize(560,400)
        self.document = None
        self.preview_document=None;self.closed=False
        self.raster_timer=QTimer(self);self.raster_timer.setSingleShot(True)
        self.raster_timer.timeout.connect(self.render_raster)
        self.paths = list(paths)
        layout = self.body_layout;layout.setSpacing(6)
        self.canvas = SplitCanvas();self.viewport=SplitViewport(self.canvas);self.viewport.setMinimumSize(0,120)
        files = QHBoxLayout();files.setSpacing(6)
        self.files = combo_factory()
        self.files.setAccessibleName('PDF to split');self.files.setMinimumWidth(100)
        self.files.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        for path in paths:
            self.files.addItem(path.name)
        files.addWidget(self.files, 1)
        files.addWidget(QLabel('Page'))
        self.page = QSpinBox()
        self.page.lineEdit().setTextMargins(12, 0, 12, 0)
        self.page.setFixedWidth(65);self.page.setAccessibleName('Preview page')
        self.page.setToolTip('Type a page number, or use the up/down arrow keys.')
        self.page.setMinimum(1)
        files.addWidget(self.page)
        self.zoom_controls=ZoomControls(self.viewport,compact=True);files.addWidget(self.zoom_controls)
        self.fit_width=self.zoom_controls.fit_width;self.fit_page=self.zoom_controls.fit_page
        self.zoom_out=self.zoom_controls.minus;self.zoom_in=self.zoom_controls.plus;self.zoom_percent=self.zoom_controls.percent
        layout.addLayout(files)
        controls = QHBoxLayout();controls.setSpacing(6)
        self.direction = combo_factory()
        for code, title in DIRECTIONS.items():
            self.direction.addItem(title, code)
        self.direction.setCurrentIndex(self.direction.findData(config['direction']))
        self.direction.setFixedWidth(130);self.direction.setAccessibleName('Output page order')
        controls.addWidget(self.direction)
        self.parts = QSpinBox()
        self.parts.lineEdit().setTextMargins(12,0,12,0)
        self.parts.setRange(2,12)
        self.parts.setValue(config['parts'])
        self.parts.setPrefix('Parts: ')
        self.parts.setFixedWidth(92)
        self.parts.setAccessibleName('Parts per page')
        self.parts.setToolTip('3 parts = 2 draggable cut lines.')
        controls.addWidget(self.parts)
        self.position = QDoubleSpinBox()
        self.position.lineEdit().setTextMargins(12, 0, 12, 0)
        self.position.setMinimumWidth(90)
        self.position.setDecimals(1)
        self.position.setRange(5,95)
        self.position.setSuffix('%')
        self.position.setValue(config['position'])
        self.position.hide()
        self.equal=QPushButton('Equal');self.equal.setAccessibleName('Equal spacing');self.equal.setToolTip('Space all dividing lines equally')
        self.equal.setStyleSheet('padding:5px 7px;');controls.addWidget(self.equal)
        self.ranges = QLineEdit(config['pages'])
        self.ranges.setPlaceholderText('All pages, or 2-15, 18')
        self.ranges.setAccessibleName('Pages to split')
        self.cut_selector=combo_factory();self.cut_selector.setAccessibleName('Selected dividing line');self.cut_selector.setFixedWidth(96)
        self.cut_position=QDoubleSpinBox();self.cut_position.setDecimals(1);self.cut_position.setSingleStep(.1)
        self.cut_position.setSuffix('%');self.cut_position.setFixedWidth(78);self.cut_position.setAccessibleName('Selected dividing line position')
        for widget in (self.cut_selector,self.cut_position):controls.addWidget(widget)
        controls.addStretch();layout.addLayout(controls);layout.addWidget(self.viewport,1)
        self.maximize_button=self.header.maximize
        self.status = QLabel()
        self.status.setWordWrap(True);self.status.setObjectName('muted')
        layout.addWidget(self.status)
        self.note = QLabel(self);self.note.hide()
        separator=QFrame();separator.setObjectName('toolDivider');separator.setFixedHeight(1)
        layout.addWidget(separator)
        footer=QHBoxLayout();footer.setSpacing(6);footer.addWidget(QLabel('Pages'));footer.addWidget(self.ranges,1)
        self.help_button=IconButton('info','How to split a page');footer.addWidget(self.help_button)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        self.apply = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.apply.setText('Apply')
        self.apply.setObjectName('primary')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        footer.addWidget(buttons);layout.addLayout(footer)
        self.files.currentIndexChanged.connect(self.load_file)
        self.page.valueChanged.connect(self.render_page)
        self.direction.currentIndexChanged.connect(self.update_settings)
        self.position.valueChanged.connect(self.update_settings)
        self.parts.valueChanged.connect(self.reset_cuts)
        self.ranges.textChanged.connect(self.update_settings)
        self.canvas.cuts_moved.connect(self.set_cuts)
        self.equal.clicked.connect(self.reset_cuts)
        self.viewport.view_changed.connect(self.view_changed)
        self.cut_selector.currentIndexChanged.connect(self.select_cut)
        self.cut_position.valueChanged.connect(self.adjust_cut)
        self.canvas.line_selected.connect(self.select_cut)
        self.load_file()

    def toggle_maximized(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def changeEvent(self,event):
        super().changeEvent(event)
        if hasattr(self,'maximize_button'):
            self.maximize_button.setToolTip('Restore tool window' if self.isMaximized() else 'Maximize tool window')

    def view_changed(self,zoom):
        self.zoom_percent.blockSignals(True);self.zoom_percent.setValue(round(zoom*100));self.zoom_percent.blockSignals(False)
        if not self.closed and self.document is not None:self.raster_timer.start(140)

    def select_cut(self,index):
        self.canvas.focused_cut=max(0,min(index,len(self.canvas.cuts())-1))
        self.sync_cut_controls();self.ensure_cut_visible();self.canvas.update()

    def ensure_cut_visible(self):
        handles=self.canvas.handle_rects()
        if not handles:return
        point=handles[min(self.canvas.focused_cut,len(handles)-1)].center()
        visible=self.canvas.visible_rect()
        if not visible.adjusted(20,20,-20,-20).contains(point):
            self.viewport.pan_by(visible.center()-point)

    def adjust_cut(self,value):
        if self.canvas.selected:self.canvas.emit_cut(value)

    def sync_cut_controls(self):
        cuts=self.canvas.cuts();index=min(self.canvas.focused_cut,len(cuts)-1)
        self.canvas.focused_cut=index
        self.cut_selector.blockSignals(True)
        if self.cut_selector.count()!=len(cuts):
            self.cut_selector.clear()
            for n in range(len(cuts)):self.cut_selector.addItem(f'Divider {n+1}')
        self.cut_selector.setCurrentIndex(index);self.cut_selector.blockSignals(False)
        minimum=5 if len(cuts)==1 else 2
        self.cut_position.blockSignals(True)
        self.cut_position.setRange((cuts[index-1] if index else 0)+minimum,(cuts[index+1] if index+1<len(cuts) else 100)-minimum)
        self.cut_position.setValue(cuts[index]);self.cut_position.blockSignals(False)
        self.cut_selector.setEnabled(self.canvas.selected);self.cut_position.setEnabled(self.canvas.selected)

    def config(self):
        return settings({'direction': self.direction.currentData(), 'position': self.position.value(),
                         'pages': self.ranges.text(), 'parts': self.parts.value(),'cuts':self.cuts})

    def set_cuts(self,cuts):
        self.cuts=list(cuts)
        if len(cuts)==1:
            self.position.blockSignals(True);self.position.setValue(cuts[0]);self.position.blockSignals(False)
        self.update_settings()

    def reset_cuts(self,*args):
        self.cuts=[100*n/self.parts.value() for n in range(1,self.parts.value())]
        self.set_cuts(self.cuts)

    def load_file(self, *args):
        self.raster_timer.stop();self.release_preview()
        if self.document is not None:
            self.document.close()
            self.document = None
        try:
            self.document = pymupdf.open(self.paths[self.files.currentIndex()])
            if self.document.needs_pass or not 0 < len(self.document) <= 2000:
                raise ValueError('Preview requires an unlocked PDF with 1–2,000 pages.')
            self.page.blockSignals(True)
            self.page.setRange(1, len(self.document))
            self.page.setValue(1)
            self.page.blockSignals(False)
            self.render_page()
        except Exception as error:
            if self.document is not None:
                self.document.close()
            self.document = None
            self.canvas.pixmap = QPixmap()
            self.viewport.set_page_size(QSizeF())
            self.canvas.update()
            self.status.setText(str(error))
            self.apply.setEnabled(False)

    def render_page(self, *args):
        if self.document is None:
            return
        self.raster_timer.stop();self.release_preview()
        try:
            page = self.document[self.page.value()-1]
            if self.cleanup_config:
                from yuzufile.cleanup import page_selection,transform_page,file_options
                selected=page_selection(file_options(self.cleanup_config,self.paths[self.files.currentIndex()]).get('pages',self.cleanup_config['pages']),len(self.document))
                if self.page.value()-1 in selected:
                    self.preview_document,_,_=transform_page(self.document,self.page.value()-1,self.cleanup_config,self.paths[self.files.currentIndex()])
                    page=self.preview_document[0]
            self.viewport.set_page_size(QSizeF(page.rect.width,page.rect.height))
            self.update_settings()
            self.ensure_cut_visible()
            self.render_raster()
        except Exception as error:
            self.status.setText(str(error))
            self.apply.setEnabled(False)

    def release_preview(self):
        if self.preview_document is not None:self.preview_document.close()
        self.preview_document=None

    def render_raster(self):
        self.raster_timer.stop()
        if self.closed or self.document is None:return
        try:
            page=self.preview_document[0] if self.preview_document is not None else self.document[self.page.value()-1]
            # Re-render only this page after zoom settles. Bound both pixel count
            # and the largest raster dimension, including on high-DPI displays.
            scale=min(max(1,self.viewport.zoom*96/72*self.devicePixelRatioF()),
                      math.sqrt(8_000_000/max(1,page.rect.get_area())),6000/max(page.rect.width,page.rect.height))
            pixmap=page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),colorspace=pymupdf.csRGB,alpha=False)
            self.raster_size=(pixmap.width,pixmap.height)
            image=QImage(pixmap.samples,pixmap.width,pixmap.height,pixmap.stride,QImage.Format.Format_RGB888).copy()
            self.canvas.pixmap=QPixmap.fromImage(image);self.canvas.update()
        except Exception as error:
            self.status.setText(str(error));self.apply.setEnabled(False)

    def update_settings(self, *args):
        if self.document is None:
            return
        try:
            config = self.config()
            selected = selected_pages(config['pages'], len(self.document))
            previous_direction=self.canvas.config['direction']
            self.canvas.config = config
            self.canvas.setCursor(Qt.CursorShape.OpenHandCursor)
            self.note.setText('Drag a line to split. Drag the page to pan · Ctrl + wheel to zoom · Arrows nudge the selected divider.')
            self.help_button.setToolTip(self.note.text());self.canvas.setAccessibleDescription(self.note.text())
            self.canvas.selected = self.page.value()-1 in selected
            self.sync_cut_controls()
            if previous_direction!=config['direction']:self.ensure_cut_visible()
            output_count = len(self.document)+len(selected)*(config['parts']-1)
            if output_count > 4000:
                raise ValueError('Splitting would exceed 4,000 output pages. Choose fewer pages or parts.')
            self.status.setText(f'{len(self.document)} input pages → {output_count} output pages. '
                                + ('This page will be split.' if self.canvas.selected else 'This page stays unchanged.'))
            self.apply.setEnabled(True)
        except ValueError as error:
            self.status.setText(str(error))
            self.apply.setEnabled(False)
            self.canvas.selected=False;self.cut_selector.setEnabled(False);self.cut_position.setEnabled(False)
        self.canvas.update()

    def done(self, result):
        self.closed=True;self.raster_timer.stop();self.release_preview()
        if self.document is not None:
            self.document.close()
            self.document = None
        self.canvas.pixmap=QPixmap()
        super().done(result)
