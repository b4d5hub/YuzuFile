"""Visual, page-specific geometry editor; preview and export share transforms."""
from collections import OrderedDict
from copy import deepcopy
from pathlib import Path

import pymupdf
from PySide6.QtCore import QTimer,Qt,QSize,QSizeF,QRect,QItemSelectionModel
from PySide6.QtGui import QImage,QPixmap,QIcon,QShortcut,QKeySequence
from PySide6.QtWidgets import (QDialog,QDialogButtonBox,QHBoxLayout,QLabel,QLineEdit,
    QSpinBox,QVBoxLayout,QWidget,QSlider,QPushButton,QListWidget,QListWidgetItem,
    QAbstractItemView,QMenu,QStackedWidget,QSizePolicy,QFrame)

from yuzufile.cleanup import settings,page_selection,transform_page,file_options,edit_for
from yuzufile.icons import icon
from yuzufile.page_canvas import PageCanvas
from yuzufile.spread_preview import SplitCanvas
from yuzufile.ui_components import IconButton
from yuzufile.ui_style import COLORS
from yuzufile.split_viewport import SplitViewport
from yuzufile.preview_tools import ZoomControls,raster_page
from yuzufile.tool_window import ToolDialog


def ranges_for(numbers):
    groups=[]
    for number in sorted(set(numbers)):
        if groups and number==groups[-1][-1]+1:groups[-1].append(number)
        else:groups.append([number])
    return ', '.join(str(g[0]) if len(g)==1 else f'{g[0]}-{g[-1]}' for g in groups)


class CleanupPreview(ToolDialog):
    def __init__(self,parent,paths,config,combo_factory):
        super().__init__(parent,title='Clean up pages')
        from yuzufile.ui import CheckBox
        screen=self.screen().availableGeometry()
        self.resize(min(1360,int(screen.width()*.94)),min(1000,int(screen.height()*.94)))
        self.setMinimumSize(560,400)
        self.paths=[Path(p).absolute() for p in paths]
        self.document=None
        self.detail=None
        self.visual=deepcopy(config.get('visual',{}))
        self.undo_stack=[];self.redo_stack=[];self.drag_snapshot=None;self.loading=True
        self.thumb_cache=OrderedDict()
        self.preview_document=None;self.preview_page=None;self.preview_key=None;self.rendering=False
        self.raster_timer=QTimer(self);self.raster_timer.setSingleShot(True);self.raster_timer.timeout.connect(self.render_raster)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.render_page)
        self.thumb_timer=QTimer(self);self.thumb_timer.setSingleShot(True);self.thumb_timer.timeout.connect(self.render_thumbnail)
        layout=self.body_layout;layout.setSpacing(6)
        header=QHBoxLayout();header.setSpacing(6)
        self.files=combo_factory();self.files.setAccessibleName('PDF to edit')
        self.files.setMinimumWidth(100);self.files.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        for path in self.paths:self.files.addItem(path.name)
        header.addWidget(self.files,1)
        self.undo_button=IconButton('undo-2','Undo',self.undo)
        self.redo_button=IconButton('redo-2','Redo',self.redo)
        header.addWidget(self.undo_button);header.addWidget(self.redo_button)
        self.batch=QPushButton('Apply to…');self.batch.setToolTip('Copy these page edits to selected pages, this PDF, or all added PDFs')
        header.addWidget(self.batch)
        header.addWidget(QLabel('Page'))
        self.page=QSpinBox();self.page.setRange(1,1);self.page.setFixedWidth(66)
        self.page.setAccessibleName('Preview page');header.addWidget(self.page)
        layout.addLayout(header)
        toolbar=QHBoxLayout();toolbar.setSpacing(5)
        self.crop_tool=QPushButton('Crop');self.crop_tool.setCheckable(True);self.crop_tool.setChecked(True)
        self.align_tool=QPushButton('Straighten');self.align_tool.setCheckable(True)
        self.pan_tool=QPushButton('Pan');self.pan_tool.setCheckable(True)
        self.pan_tool.setObjectName('pageTool')
        self.crop_tool.setObjectName('pageTool');self.align_tool.setObjectName('pageTool')
        for button in (self.crop_tool,self.align_tool,self.pan_tool):
            button.setStyleSheet('padding:5px 7px;');toolbar.addWidget(button)
        self.crop_context=QWidget();crop_controls=QHBoxLayout(self.crop_context)
        crop_controls.setContentsMargins(4,0,0,0);crop_controls.setSpacing(5)
        self.trim=CheckBox('Trim');self.trim.setChecked(config['trim']);crop_controls.addWidget(self.trim)
        self.fit=QPushButton('Auto fit');self.fit.setToolTip('Find the visible page content and trim the empty margins')
        self.fit.setStyleSheet('padding:5px 7px;');crop_controls.addWidget(self.fit)
        toolbar.addWidget(self.crop_context)
        self.alignment_row=QWidget();alignment=QHBoxLayout(self.alignment_row)
        alignment.setContentsMargins(4,0,0,0);alignment.setSpacing(5)
        self.auto=CheckBox('Auto');self.auto.setAccessibleName('Auto straighten');self.auto.setToolTip('Detect the page angle automatically')
        alignment.addWidget(self.auto)
        self.angle=QSlider(Qt.Orientation.Horizontal);self.angle.setRange(-450,450);self.angle.setMinimumWidth(65)
        self.angle.setAccessibleName('Straightening angle');alignment.addWidget(self.angle,1)
        self.angle_label=QLabel('0.0°');self.angle_label.setMinimumWidth(40);alignment.addWidget(self.angle_label)
        self.alignment_row.setMaximumWidth(360);toolbar.addWidget(self.alignment_row,1);self.alignment_row.hide()
        toolbar.addStretch()
        self.rotate_left=IconButton('rotate-ccw','Rotate left',lambda:self.rotate(-90))
        self.rotate_right=IconButton('rotate-cw','Rotate right',lambda:self.rotate(90))
        toolbar.addWidget(self.rotate_left);toolbar.addWidget(self.rotate_right)
        self.reset=QPushButton('Reset');self.reset.setAccessibleName('Reset page');self.reset.setToolTip('Reset this page to automatic cleanup')
        self.reset.setStyleSheet('padding:5px 7px;');self.reset.clicked.connect(self.reset_page);toolbar.addWidget(self.reset)
        layout.addLayout(toolbar)
        # Legacy inputs retained only for loading old jobs; geometry is edited on canvas.
        self.straighten=CheckBox('Auto straighten');self.straighten.setChecked(config['straighten']);self.straighten.hide()
        self.padding=QSpinBox(self);self.padding.setRange(1,20);self.padding.setValue(round(config['padding_mm']));self.padding.hide()
        self.ranges=QLineEdit(config['pages'],self);self.ranges.hide()
        self.before,self.after=PageCanvas(),SplitCanvas()
        self.after.selected=False;self.after.setCursor(Qt.CursorShape.ArrowCursor);self.after.setMinimumWidth(170)
        self.canvas_title=QLabel('Crop page')
        self.edit_view=SplitViewport(self.before);self.result_view=SplitViewport(self.after)
        for view in (self.edit_view,self.result_view):view.setMinimumSize(0,120)
        self.edit_view.setAccessibleName('Scrollable page editor');self.result_view.setAccessibleName('Scrollable edited result')
        self.views=QStackedWidget();self.views.addWidget(self.edit_view);self.views.addWidget(self.result_view)
        view_bar=QHBoxLayout()
        self.edit_tab=QPushButton('Edit');self.result_tab=QPushButton('Result')
        for button in (self.edit_tab,self.result_tab):
            button.setCheckable(True);button.setObjectName('pageTool');view_bar.addWidget(button)
        self.edit_tab.setChecked(True);self.canvas_title.hide();view_bar.addStretch()
        self.zoom_controls=ZoomControls(self.edit_view);view_bar.addWidget(self.zoom_controls)
        self.help_button=IconButton('info','How to edit this page');view_bar.addWidget(self.help_button)
        self.fit_view_button=self.zoom_controls.fit_page
        layout.addLayout(view_bar);layout.addWidget(self.views,1)
        self.edit_tab.clicked.connect(lambda:self.show_view(0));self.result_tab.clicked.connect(lambda:self.show_view(1))
        for view in (self.edit_view,self.result_view):view.view_changed.connect(self.schedule_raster)
        self.status=QLabel();self.status.setWordWrap(True);self.status.setObjectName('muted');self.status.hide();layout.addWidget(self.status)
        self.thumbnails=QListWidget();self.thumbnails.setViewMode(QListWidget.ViewMode.IconMode)
        self.thumbnails.setFlow(QListWidget.Flow.LeftToRight);self.thumbnails.setWrapping(False)
        self.thumbnails.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.thumbnails.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.thumbnails.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.thumbnails.setIconSize(QSize(42,42));self.thumbnails.setGridSize(QSize(62,54));self.thumbnails.setFixedHeight(66)
        self.thumbnails.setAccessibleName('Page thumbnails; select pages with Ctrl or Shift')
        self.thumbnails.setStyleSheet('QListWidget{border:1px solid '+COLORS['border']+';border-radius:14px;background:'+COLORS['canvas']+';} QListWidget::item{border-radius:9px;padding:3px;} QListWidget::item:selected{background:'+COLORS['accent_soft']+';color:'+COLORS['text']+';}')
        layout.addWidget(self.thumbnails);self.thumbnails.hide()
        separator=QFrame();separator.setObjectName('toolDivider');separator.setFixedHeight(1)
        layout.addWidget(separator)
        footer=QHBoxLayout();footer.setSpacing(6)
        self.scope=combo_factory();self.scope.addItems(['All pages','Selected thumbnails']);self.scope.setAccessibleName('Pages to process')
        self.scope.setMinimumWidth(130);self.scope.setMaximumWidth(170);footer.addWidget(self.scope)
        self.pages_button=QPushButton('Pages');self.pages_button.setCheckable(True)
        self.pages_button.setToolTip('Show page thumbnails · Ctrl / Shift click to select several');footer.addWidget(self.pages_button)
        self.scope_label=QLabel();self.scope_label.setObjectName('muted');footer.addWidget(self.scope_label);footer.addStretch()
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel|QDialogButtonBox.StandardButton.Ok)
        self.apply=buttons.button(QDialogButtonBox.StandardButton.Ok);self.apply.setText('Use these edits')
        self.apply.setObjectName('primary')
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);footer.addWidget(buttons);layout.addLayout(footer)
        self.files.currentIndexChanged.connect(self.load_file)
        self.page.valueChanged.connect(self.render_page)
        self.trim.toggled.connect(self.schedule);self.straighten.toggled.connect(self.schedule)
        self.padding.valueChanged.connect(self.schedule);self.ranges.textChanged.connect(self.schedule)
        self.crop_tool.clicked.connect(lambda:self.tool('crop'));self.align_tool.clicked.connect(lambda:self.tool('straighten'))
        self.pan_tool.clicked.connect(lambda:self.tool('pan'))
        self.before.started.connect(self.begin_edit);self.before.crop_changed.connect(self.crop_live)
        self.before.angle_changed.connect(self.align_line);self.before.finished.connect(self.finish_edit)
        self.angle.sliderPressed.connect(self.begin_edit);self.angle.sliderReleased.connect(self.finish_edit)
        self.angle.valueChanged.connect(self.angle_changed);self.auto.toggled.connect(self.auto_angle)
        self.fit.clicked.connect(self.auto_fit);self.batch.clicked.connect(self.batch_menu)
        self.pages_button.toggled.connect(self.toggle_pages)
        self.scope.currentIndexChanged.connect(self.scope_changed)
        self.thumbnails.itemSelectionChanged.connect(self.selection_changed)
        self.thumbnails.currentRowChanged.connect(self.thumbnail_current)
        self.thumbnails.horizontalScrollBar().valueChanged.connect(lambda:self.thumb_timer.start(15))
        for key,callback in (('Ctrl+Z',self.undo),('Ctrl+Y',self.redo),('Ctrl+Shift+Z',self.redo)):
            shortcut=QShortcut(QKeySequence(key),self);shortcut.activated.connect(callback)
        self.load_file()

    def raw_config(self):
        return dict(straighten=self.straighten.isChecked(),trim=self.trim.isChecked(),
                    padding_mm=self.padding.value(),pages=self.ranges.text(),visual=deepcopy(self.visual))

    def config(self):return settings(self.raw_config())

    def path(self):return str(self.paths[self.files.currentIndex()])

    def entry(self):return self.visual.setdefault('files',{}).setdefault(self.path(),{'edits':{}})

    def edit(self):return edit_for(self.raw_config(),self.path(),self.page.value()-1)

    def set_edit(self,**values):
        self.entry().setdefault('edits',{})[str(self.page.value())]={**self.edit(),**values}

    def snapshot(self):
        return (deepcopy(self.visual),self.ranges.text(),self.trim.isChecked(),self.straighten.isChecked(),
                self.files.currentIndex(),self.page.value())

    def history_buttons(self):
        self.undo_button.setEnabled(bool(self.undo_stack));self.redo_button.setEnabled(bool(self.redo_stack))

    def checkpoint(self):
        self.undo_stack.append(self.snapshot());self.undo_stack=self.undo_stack[-60:];self.redo_stack.clear();self.history_buttons()

    def begin_edit(self):self.drag_snapshot=self.snapshot()

    def finish_edit(self):
        if self.drag_snapshot is not None and self.drag_snapshot!=self.snapshot():
            self.undo_stack.append(self.drag_snapshot);self.undo_stack=self.undo_stack[-60:];self.redo_stack.clear()
        self.drag_snapshot=None;self.history_buttons();self.schedule()

    def restore(self,state):
        self.loading=True
        visual,pages,trim,straighten,file,page=state
        self.visual=deepcopy(visual);self.ranges.setText(pages);self.trim.setChecked(trim);self.straighten.setChecked(straighten)
        self.files.blockSignals(True);self.files.setCurrentIndex(file);self.files.blockSignals(False)
        self.load_file();self.page.setValue(page);self.render_page();self.history_buttons()

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(self.snapshot());self.restore(self.undo_stack.pop())

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(self.snapshot());self.restore(self.redo_stack.pop())

    def tool(self,name):
        self.before.tool=name;self.crop_tool.setChecked(name=='crop');self.align_tool.setChecked(name=='straighten')
        self.pan_tool.setChecked(name=='pan');self.show_view(0)
        self.crop_context.setVisible(name=='crop');self.alignment_row.setVisible(name=='straighten')
        self.canvas_title.setText('Straighten page' if name=='straighten' else 'Crop page')
        self.before.update()
        self.instructions()

    def instructions(self):
        selected=self.before.isEnabled()
        help=('Drag to move the view. ' if self.before.tool=='pan' else 'Draw along a line of text to level it. ' if self.before.tool=='straighten' else 'Drag the frame; shaded margins will be removed. ')
        help+='Scroll to read; Ctrl+scroll to zoom; Space+drag to pan.'
        self.help_button.setToolTip(help);self.before.setAccessibleDescription(help)
        message=('This page is outside the selected pages and will stay unchanged. ' if not selected else '')
        message+=' '.join((self.detail or {}).get('warnings',[]))
        self.status.setText(message.strip());self.status.setVisible(bool(message.strip()))

    def schedule(self,*args):
        if not self.loading:self.apply.setEnabled(False);self.timer.start(140)

    def crop_live(self,crop):
        self.set_edit(crop=list(crop));self.live_result(crop);self.apply.setEnabled(False)

    def live_result(self,crop):
        pix=self.before.pixmap
        if pix.isNull():return
        x0,y0,x1,y1=crop
        rect=QRect(round(x0*pix.width()),round(y0*pix.height()),max(1,round((x1-x0)*pix.width())),max(1,round((y1-y0)*pix.height())))
        self.after.pixmap=pix.copy(rect);self.after.update()
        if self.preview_page is not None:
            r=self.preview_page.rect
            self.result_view.set_page_size(QSizeF(r.width*(x1-x0),r.height*(y1-y0)),reset=False)

    def show_view(self,index):
        self.views.setCurrentIndex(index);self.edit_tab.setChecked(index==0);self.result_tab.setChecked(index==1)
        self.zoom_controls.bind(self.edit_view if index==0 else self.result_view);self.schedule_raster()

    def schedule_raster(self,*args):
        if not self.rendering and self.preview_page is not None:self.raster_timer.start(140)

    def render_raster(self):
        if self.preview_page is None:return
        try:
            if self.views.currentIndex()==0:
                self.before.pixmap=raster_page(self.preview_page,self.edit_view.zoom,self.devicePixelRatioF())
                self.before.update();self.live_result(self.before.crop)
            else:
                r=self.preview_page.rect;x0,y0,x1,y1=self.before.crop
                clip=pymupdf.Rect(r.width*x0,r.height*y0,r.width*x1,r.height*y1)
                self.after.pixmap=raster_page(self.preview_page,self.result_view.zoom,self.devicePixelRatioF(),clip)
                self.after.update()
        except (ValueError,RuntimeError) as error:self.fail(error)

    def close_preview(self):
        self.raster_timer.stop();self.preview_page=None
        if self.preview_document is not None:self.preview_document.close()
        self.preview_document=None

    def align_line(self,delta):
        angle=max(-45,min(45,(self.detail or {}).get('angle_degrees',0)+delta))
        self.set_edit(angle=angle);self.schedule()

    def angle_changed(self,value):
        if self.loading:return
        if self.drag_snapshot is None:self.checkpoint()
        self.set_edit(angle=value/10)
        self.angle_label.setText(f'{value/10:.1f}°');self.schedule()

    def auto_angle(self,checked):
        if self.loading:return
        self.checkpoint();self.set_edit(angle=None if checked else 0,straighten=checked);self.schedule()

    def auto_fit(self):
        self.checkpoint();self.trim.setChecked(True);self.set_edit(crop=None);self.schedule()

    def reset_page(self):
        self.checkpoint();self.trim.setChecked(True)
        self.entry().setdefault('edits',{})[str(self.page.value())]={'crop':None,'angle':None,'rotation':0,'straighten':True};self.schedule()

    def rotate(self,degrees):
        self.checkpoint();edit=self.edit();crop=edit.get('crop')
        if crop:
            x0,y0,x1,y1=crop
            crop=[1-y1,x0,1-y0,x1] if degrees>0 else [y0,1-x1,y1,1-x0]
        self.set_edit(rotation=(edit.get('rotation',0)+degrees)%360,crop=crop);self.schedule()

    def batch_menu(self):
        menu=QMenu(self)
        for title,scope in (('Selected thumbnails','selected'),('All pages in this PDF','file'),('All added PDFs','batch')):
            action=menu.addAction(title);action.triggered.connect(lambda checked=False,s=scope:self.apply_edit_to(s))
        menu.exec(self.batch.mapToGlobal(self.batch.rect().bottomLeft()))

    def apply_edit_to(self,scope):
        self.checkpoint();edit=self.edit()
        if self.trim.isChecked():edit['crop']=self.before.crop[:]
        if scope=='selected':
            for item in self.thumbnails.selectedItems():self.entry().setdefault('edits',{})[str(self.thumbnails.row(item)+1)]=deepcopy(edit)
        elif scope=='file':
            self.entry().update(default=deepcopy(edit),edits={})
        else:
            self.visual={'default':deepcopy(edit)};self.ranges.clear();self.load_file()
        self.schedule()

    def selected_numbers(self):return [self.thumbnails.row(i)+1 for i in self.thumbnails.selectedItems()]

    def scope_changed(self,*args):
        if not self.loading:
            self.checkpoint();self.update_scope();self.schedule()
            if self.scope.currentIndex()==1:self.pages_button.setChecked(True)
            self.toggle_pages(self.pages_button.isChecked())

    def toggle_pages(self,checked):
        self.thumbnails.setVisible(self.document is not None and checked)
        if checked:self.thumb_timer.start(15)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'scope_label'):self.scope_label.setVisible(self.width()>=700)

    def selection_changed(self):
        if not self.loading and self.scope.currentIndex()==1:self.update_scope();self.schedule()

    def update_scope(self):
        self.entry()['pages']=ranges_for(self.selected_numbers()) if self.scope.currentIndex()==1 else ''

    def thumbnail_current(self,row):
        if not self.loading and row>=0:self.before.fit_view();self.page.setValue(row+1)

    def load_file(self,*args):
        self.timer.stop();self.thumb_timer.stop();self.loading=True
        self.close_preview();self.preview_key=None
        if self.document is not None:self.document.close()
        self.document=None;self.thumb_cache.clear();self.thumbnails.clear()
        self.before.fit_view()
        try:
            path=self.paths[self.files.currentIndex()]
            if path.stat().st_size>1_000_000_000:raise ValueError('The maximum supported PDF size is 1 GB.')
            self.document=pymupdf.open(path)
            if self.document.needs_pass or not 0<len(self.document)<=2000:raise ValueError('Choose an unlocked PDF with 1–2,000 pages.')
            if self.document.get_sigflags()>0:raise ValueError('Use an unsigned copy before editing pages.')
            self.page.blockSignals(True);self.page.setRange(1,len(self.document));self.page.setValue(1);self.page.blockSignals(False)
            expression=file_options(self.raw_config(),self.path()).get('pages',self.ranges.text())
            selected=page_selection(expression,len(self.document))
            self.scope.setCurrentIndex(1 if expression and expression.lower()!='all' else 0)
            for index in range(len(self.document)):
                item=QListWidgetItem(icon('file-text'),str(index+1));item.setToolTip(f'Page {index+1}');self.thumbnails.addItem(item)
                if self.scope.currentIndex()==1 and index in selected:item.setSelected(True)
            if self.scope.currentIndex()==0:self.thumbnails.item(0).setSelected(True)
            if self.scope.currentIndex()==1:self.pages_button.setChecked(True)
            self.toggle_pages(self.pages_button.isChecked())
            self.thumbnails.setCurrentRow(0,QItemSelectionModel.SelectionFlag.NoUpdate)
            self.loading=False;self.render_page();self.thumb_timer.start(15)
        except (OSError,ValueError,RuntimeError) as error:
            if self.document is not None:self.document.close()
            self.document=None;self.before.pixmap=QPixmap();self.before.update();self.loading=False;self.fail(error)
        self.history_buttons()

    def render_thumbnail(self):
        if self.document is None:return
        viewport=self.thumbnails.viewport().rect()
        for index in range(self.thumbnails.count()):
            item=self.thumbnails.item(index)
            if index in self.thumb_cache or not self.thumbnails.visualItemRect(item).intersects(viewport):continue
            try:
                page=self.document[index];scale=min(52/page.rect.width,66/page.rect.height)
                pix=page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),colorspace=pymupdf.csRGB,alpha=False)
                image=QImage(pix.samples,pix.width,pix.height,pix.stride,QImage.Format.Format_RGB888).copy()
                item.setIcon(QIcon(QPixmap.fromImage(image)));self.thumb_cache[index]=True
                while len(self.thumb_cache)>100:self.thumb_cache.popitem(last=False)
            except (ValueError,RuntimeError):pass
            self.thumb_timer.start(15);break

    def fail(self,error):
        self.after.pixmap=QPixmap();self.after.update();self.status.setText(str(error));self.status.show();self.apply.setEnabled(False)

    def render_page(self,*args):
        self.timer.stop()
        if self.document is None:return
        self.close_preview();self.rendering=True
        try:
            config=self.config()
            if self.scope.currentIndex()==1 and not self.selected_numbers():raise ValueError('Select at least one page thumbnail to process.')
            selected=page_selection(file_options(config,self.path()).get('pages',config['pages']),len(self.document))
            index=self.page.value()-1
            if index in selected:
                self.preview_document,self.detail,_=transform_page(self.document,index,config,self.path(),preview_uncropped=True);page=self.preview_document[0]
            else:
                page=self.document[index];self.detail=None
            self.preview_page=page
            key=(self.path(),index,page.rect.width,page.rect.height)
            self.edit_view.set_page_size(QSizeF(page.rect.width,page.rect.height),reset=key!=self.preview_key)
            self.preview_key=key
            self.before.pixmap=raster_page(page,self.edit_view.zoom,self.devicePixelRatioF())
            self.before.minimum=(min(1,12/page.rect.width),min(1,12/page.rect.height))
            self.before.crop_enabled=config['trim'] and index in selected
            self.before.setEnabled(index in selected)
            crop=self.detail['crop'] if self.detail else [0,0,1,1]
            self.before.set_crop(crop);self.live_result(crop)
            if self.views.currentIndex()==1:self.render_raster()
            self.loading=True
            angle=(self.detail or {}).get('angle_degrees',0)
            self.angle.setValue(round(angle*10));self.angle_label.setText(f'{angle:.1f}°')
            self.auto.setChecked(self.edit().get('angle') is None and self.edit().get('straighten',config['straighten']))
            self.thumbnails.setCurrentRow(index,QItemSelectionModel.SelectionFlag.NoUpdate)
            self.thumbnails.scrollToItem(self.thumbnails.item(index))
            self.loading=False
            self.scope_label.setText(f'{len(selected)} of {len(self.document)} pages')
            self.instructions()
            for control in (self.rotate_left,self.rotate_right,self.fit,self.reset,self.angle,self.auto,self.align_tool):control.setEnabled(index in selected)
            self.apply.setEnabled(True);self.thumb_timer.start(15)
        except (OSError,ValueError,RuntimeError) as error:
            self.loading=False;self.fail(error)
        finally:
            self.rendering=False
            pymupdf.TOOLS.store_shrink(100)

    def done(self,result):
        if result==QDialog.DialogCode.Accepted:
            self.render_page()
            if not self.apply.isEnabled():return
        self.timer.stop();self.thumb_timer.stop()
        self.close_preview()
        if self.document is not None:self.document.close()
        self.document=None;super().done(result)
