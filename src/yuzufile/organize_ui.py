"""One reversible page workspace; thumbnails render only for visible cards."""
from collections import OrderedDict
from copy import deepcopy
from pathlib import Path

import pymupdf
from PySide6.QtCore import Qt, QSize, QTimer, Signal,QItemSelectionModel
from PySide6.QtGui import QIcon, QImage, QPixmap, QShortcut, QKeySequence, QDrag
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHBoxLayout,
                              QLabel, QListWidget, QListWidgetItem, QPushButton,
                              QVBoxLayout,QSlider,QWidget,QBoxLayout,QFrame)

from yuzufile.icons import icon
from yuzufile.ui_components import IconButton
from yuzufile.ui_style import COLORS
from yuzufile.tool_window import ToolDialog
from yuzufile.organize import (MAX_BYTES, MAX_PAGES, MAX_SOURCES, inspect_source,
                           source_unchanged, validate_plan)


from yuzufile.page_grid import PageGrid,ASPECT_ROLE,READY_ROLE
from yuzufile.page_preview import PagePreview


class WorkspaceMessage(QLabel):
    """Feedback takes space only while there is something useful to report."""
    def setText(self,text):
        super().setText(text);self.setVisible(bool(text))
    def clear(self):self.setText('')


class OrganizeDialog(ToolDialog):
    def __init__(self, parent, paths=(), plan=None):
        super().__init__(parent,title='Arrange pages')
        available = self.screen().availableGeometry()
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint,True)
        self.resize(min(1360,int(available.width()*.94)),min(1000,int(available.height()*.94)))
        self.sources = []
        self.undo_stack, self.redo_stack = [], []
        self.thumbnail_cache = OrderedDict()
        self.page_dimensions={}
        self.placeholder = icon('file-text',32)
        self.result_plan = None
        self.output_directory = getattr(parent,'output_directory',None)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.render_thumbnail)
        self.feedback_timer=QTimer(self);self.feedback_timer.setSingleShot(True)
        self.feedback_timer.timeout.connect(self.clear_landing)
        layout = self.body_layout
        layout.setContentsMargins(16,10,16,12);layout.setSpacing(8)
        self.tools=QWidget();self.tools_layout=QBoxLayout(QBoxLayout.Direction.LeftToRight,self.tools)
        self.tools_layout.setContentsMargins(0,0,0,0);self.tools_layout.setSpacing(5)
        files = QHBoxLayout();files.setSpacing(3)
        self.add_button = self.button('Add PDFs',self.pick_files,files)
        self.undo_button = self.button('Undo',self.undo,files)
        self.redo_button = self.button('Redo',self.redo,files)
        files.addStretch()
        actions = QHBoxLayout();actions.setSpacing(3)
        self.earlier = self.button('Move earlier',lambda:self.move_selected(-1),actions)
        self.later = self.button('Move later',lambda:self.move_selected(1),actions)
        self.rotate_left = self.button('Rotate left',lambda:self.rotate(-90),actions)
        self.rotate_right = self.button('Rotate right',lambda:self.rotate(90),actions)
        self.remove_button = self.button('Remove',self.remove_selected,actions)
        actions.addStretch(1)
        self.view_button=self.button('View page',self.view_page,actions)
        self.tools_layout.addLayout(files)
        self.tools_layout.addLayout(actions,1)
        self.count_label=QLabel()
        self.count_label.setObjectName("muted")
        size_bar=QHBoxLayout();size_bar.setSpacing(6)
        self.page_size_label=QLabel('Page size');self.page_size_label.setObjectName('muted');size_bar.addWidget(self.page_size_label)
        self.page_size=QSlider(Qt.Orientation.Horizontal);self.page_size.setRange(160,480);self.page_size.setValue(300)
        self.page_size.setFixedWidth(115);self.page_size.setAccessibleName('Page thumbnail size');size_bar.addWidget(self.page_size)
        summary=QHBoxLayout();summary.addWidget(self.count_label,1)
        self.selection_hint=QLabel('Drag to arrange · Ctrl/Shift to select');self.selection_hint.setObjectName('muted')
        summary.addWidget(self.selection_hint);summary.addSpacing(10);summary.addLayout(size_bar)
        layout.addLayout(summary);layout.addWidget(self.tools)
        self.grid = PageGrid(self)
        self.grid.itemSelectionChanged.connect(self.update_actions)
        self.grid.need_thumbnails.connect(self.schedule_thumbnails)
        self.grid.itemDoubleClicked.connect(lambda item:self.view_page(self.grid.row(item)))
        self.page_size.valueChanged.connect(self.resize_cards)
        layout.addWidget(self.grid,1)
        # The inherited tool font must be resolved before card heights reserve
        # their two caption lines; otherwise first-show polishing steals pixels
        # from landscape page images.
        self.grid.ensurePolished()
        self.message = WorkspaceMessage()
        self.message.setWordWrap(True)
        self.message.setObjectName('muted');self.message.hide()
        layout.addWidget(self.message)
        self.destination = QLabel('Save PDF uses all remaining pages. Extract selected uses only highlighted pages, in visible order.')
        self.destination.setObjectName('muted')
        self.destination.hide()
        divider=QFrame();divider.setFrameShape(QFrame.Shape.HLine);divider.setObjectName('toolDivider');layout.addWidget(divider)
        footer = QHBoxLayout()
        self.extract_button = self.button('Extract selected',lambda:self.finish(True),footer)
        self.extract_button.setText('Extract');self.extract_button.setAccessibleName('Extract selected pages')
        self.folder_button = self.button('Output folder…',self.choose_output,footer)
        self.folder_button.setText('');self.folder_button.setAccessibleName('Choose output folder');self.folder_button.setFixedWidth(34)
        self.update_destination()
        footer.addStretch()
        self.save_button = self.button('Save PDF',lambda:self.finish(False),footer)
        self.save_button.setObjectName('primary')
        self.button('Cancel',self.reject,footer)
        layout.addLayout(footer)
        for key, action in [('Ctrl+Z',self.undo),('Ctrl+Shift+Z',self.redo),
                            ('Delete',self.remove_selected),('Alt+Left',lambda:self.move_selected(-1)),
                            ('Alt+Right',lambda:self.move_selected(1))]:
            shortcut=QShortcut(QKeySequence(key),self)
            shortcut.activated.connect(action)
        if plan:
            clean=validate_plan(plan)
            self.restore({**clean,'selected':[]})
        else:
            self.add_files(paths,record=False)
        self.update_actions()

    def button(self,text,action,layout):
        glyphs={'Undo':('undo-2','Undo · Ctrl+Z'),'Redo':('redo-2','Redo · Ctrl+Shift+Z'),
                'Move earlier':('arrow-left','Move earlier · Alt+Left'),'Move later':('arrow-right','Move later · Alt+Right'),
                'Rotate left':('rotate-ccw','Rotate left'),'Rotate right':('rotate-cw','Rotate right'),
                'Remove':('trash-2','Remove selected pages · Delete')}
        if text in glyphs:
            glyph,title=glyphs[text]
            button=IconButton(glyph,title,action)
            if text=='Remove':button.setProperty('danger',True)
        else:
            button=QPushButton(text)
            button.clicked.connect(action)
            if text in {'Add PDFs','Extract selected','Output folder…'}:
                button.setIcon(icon({'Add PDFs':'plus','Extract selected':'scissors','Output folder…':'folder-open'}[text],16))
        layout.addWidget(button)
        return button

    def entries(self):
        return [deepcopy(self.grid.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(self.grid.count())]

    def selected(self):
        return sorted(self.grid.row(item) for item in self.grid.selectedItems())

    def snapshot(self):
        return {'version':1,'sources':deepcopy(self.sources),'pages':self.entries(),'selected':self.selected()}

    def restore(self,state):
        self.feedback_timer.stop();self.grid.landed.clear()
        self.grid.blockSignals(True)
        self.grid.clear()
        self.sources=deepcopy(state['sources'])
        for source in self.sources:self.load_dimensions(source)
        for index,page in enumerate(state['pages']):
            source=self.sources[page['source']]
            name=Path(source['path']).name
            text=f"{index+1} · p. {page['page']+1}"
            if page['rotation']:
                text+=f" · {page['rotation']}°"
            text+='\n'+name
            item=QListWidgetItem(text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            ratio=self.page_ratio(page)
            item.setSizeHint(self.grid.card_size(ratio));item.setData(ASPECT_ROLE,ratio)
            item.setData(Qt.ItemDataRole.UserRole,deepcopy(page))
            item.setToolTip(f"Output page {index+1}\n{source['path']}\nOriginal page {page['page']+1}, rotation +{page['rotation']}°")
            key=self.cache_key(page)
            item.setIcon(self.thumbnail_cache.get(key,self.placeholder));item.setData(READY_ROLE,key in self.thumbnail_cache)
            self.grid.addItem(item)
            item.setSelected(index in state.get('selected',[]))
        self.grid.blockSignals(False)
        self.update_actions()
        self.schedule_thumbnails()

    def load_dimensions(self,source):
        key=(source['path'],source['mtime_ns'])
        if key in self.page_dimensions:return
        try:
            source_unchanged(source)
            with pymupdf.open(source['path']) as document:
                self.page_dimensions[key]=[(p.rect.width,p.rect.height) for p in document]
        except (OSError,ValueError,RuntimeError):pass

    def page_ratio(self,page):
        source=self.sources[page['source']]
        dimensions=self.page_dimensions.get((source['path'],source['mtime_ns']),[])
        width,height=dimensions[page['page']] if page['page']<len(dimensions) else (3,4)
        if page['rotation']%180:width,height=height,width
        return height/max(1,width)

    def change(self,pages,selected=(),sources=None):
        before=self.snapshot()
        if pages==before['pages'] and (sources is None or sources==self.sources):
            return False
        self.undo_stack.append(before)
        self.undo_stack=self.undo_stack[-40:]
        self.redo_stack.clear()
        self.restore({'sources':self.sources if sources is None else sources,'pages':pages,'selected':list(selected)})
        return True

    def resize_cards(self,width):
        state=self.snapshot();self.grid.set_card_size(width);self.restore(state)

    def view_page(self,index=None):
        if not self.grid.count():return
        if index is None or isinstance(index,bool):index=max(0,self.grid.currentRow())
        preview=PagePreview(self,self.sources,self.entries(),index);preview.exec()
        self.grid.setCurrentRow(preview.index,QItemSelectionModel.SelectionFlag.NoUpdate)
        self.grid.scrollToItem(self.grid.item(preview.index))

    def clear_landing(self):
        self.grid.landed.clear();self.grid.viewport().update()
        if self.message.text().startswith(('Moved','Pages are already')):self.message.clear()

    def landing(self,rows,changed):
        self.clear_landing()
        if not changed:self.message.setText('Pages are already in that position');return
        self.grid.landed=set(rows);self.grid.viewport().update();self.feedback_timer.start(1800)
        if len(rows)==1:message=f'Moved to output page {rows[0]+1}'
        elif rows==list(range(rows[0],rows[-1]+1)):
            message=f'Moved {len(rows)} pages to output positions {rows[0]+1}–{rows[-1]+1}'
        else:
            numbers=', '.join(str(row+1) for row in rows[:6])+('…' if len(rows)>6 else '')
            message=f'Moved {len(rows)} pages · output positions {numbers}'
        self.message.setText(message)

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(self.snapshot())
            self.restore(self.undo_stack.pop())

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(self.snapshot())
            self.restore(self.redo_stack.pop())

    def pick_files(self):
        paths,_=QFileDialog.getOpenFileNames(self,'Add PDFs to organize','','PDF files (*.pdf)')
        self.add_files(paths)

    def update_destination(self):
        location=str(self.output_directory) if self.output_directory else 'Beside the first source PDF'
        short=self.fontMetrics().elidedText(location,Qt.TextElideMode.ElideMiddle,600)
        self.destination.setText(short+' · Originals stay unchanged')
        self.destination.setToolTip(location)
        if hasattr(self,'folder_button'):self.folder_button.setToolTip('Output folder: '+location)

    def choose_output(self):
        directory=QFileDialog.getExistingDirectory(self,'Choose output folder',str(self.output_directory or Path.home()))
        if directory:
            self.output_directory=Path(directory).absolute()
            self.update_destination()

    def add_files(self,paths,record=True):
        if not paths:
            return
        pages=self.entries()
        sources=deepcopy(self.sources)
        try:
            for path in paths:
                source=inspect_source(path)
                if len(sources)>=MAX_SOURCES or len(pages)+source['pages']>MAX_PAGES:
                    raise ValueError('The workspace supports up to 50 PDFs and 2,000 output pages.')
                source_index=len(sources)
                sources.append(source)
                pages.extend({'source':source_index,'page':i,'rotation':0} for i in range(source['pages']))
            used={p['source'] for p in pages}
            if sum(sources[i]['size'] for i in used)>MAX_BYTES:
                raise ValueError('The combined input size must not exceed 1 GB.')
            if record:
                self.change(pages,sources=sources)
            else:
                self.restore({'sources':sources,'pages':pages,'selected':[]})
            self.message.clear()
        except Exception as error:
            self.message.setText(str(error))

    def remove_selected(self):
        selected=set(self.selected())
        if selected:
            self.change([p for i,p in enumerate(self.entries()) if i not in selected])

    def rotate(self,angle):
        selected=self.selected()
        pages=self.entries()
        for index in selected:
            pages[index]['rotation']=(pages[index]['rotation']+angle)%360
        self.change(pages,selected)

    def rotate_page(self,index,angle=90):
        """The card action changes just that page without disturbing selection."""
        if not 0<=index<self.grid.count():return
        pages=self.entries();pages[index]['rotation']=(pages[index]['rotation']+angle)%360
        self.change(pages,self.selected())

    def move_selected(self,delta):
        selected=set(self.selected())
        pages=self.entries()
        for index in sorted(selected,reverse=delta>0):
            other=index+delta
            if 0<=other<len(pages) and other not in selected:
                pages[index],pages[other]=pages[other],pages[index]
                selected.remove(index);selected.add(other)
        changed=self.change(pages,sorted(selected));self.landing(sorted(selected),changed)
        if selected:
            self.grid.scrollToItem(self.grid.item(min(selected)))

    def move_to(self,target,rows=None):
        selected=self.selected() if rows is None else sorted(rows)
        if not selected:
            return
        pages=self.entries()
        moving=[pages[i] for i in selected]
        remaining=[p for i,p in enumerate(pages) if i not in selected]
        target-=sum(i<target for i in selected)
        target=max(0,min(len(remaining),target));rows=list(range(target,target+len(moving)))
        changed=self.change(remaining[:target]+moving+remaining[target:],rows)
        self.landing(rows,changed)
        if changed:self.grid.scrollToItem(self.grid.item(target))

    def update_actions(self):
        selected=self.selected()
        count=self.grid.count()
        self.count_label.setText(f'{count} pages · {len(selected)} selected')
        for button in (self.rotate_left,self.rotate_right,self.remove_button,self.extract_button):
            button.setEnabled(bool(selected))
        self.earlier.setEnabled(bool(selected) and selected[0]>0)
        self.later.setEnabled(bool(selected) and selected[-1]<count-1)
        self.save_button.setEnabled(count>0)
        self.view_button.setEnabled(count>0)
        self.undo_button.setEnabled(bool(self.undo_stack))
        self.redo_button.setEnabled(bool(self.redo_stack))

    def cache_key(self,page):
        source=self.sources[page['source']]
        return (source['path'],source['mtime_ns'],page['page'],page['rotation'],self.page_size.value())

    def schedule_thumbnails(self,*args):
        if not self.timer.isActive():
            self.timer.start(20)

    def render_thumbnail(self):
        if not self.isVisible():
            return
        viewport=self.grid.viewport().rect()
        for index in range(self.grid.count()):
            item=self.grid.item(index)
            if item.data(READY_ROLE) and not viewport.intersects(self.grid.visualItemRect(item)):
                item.setIcon(self.placeholder);item.setData(READY_ROLE,False)
        for index in range(self.grid.count()):
            item=self.grid.item(index)
            if not viewport.intersects(self.grid.visualItemRect(item)):
                continue
            page=item.data(Qt.ItemDataRole.UserRole)
            key=self.cache_key(page)
            if key in self.thumbnail_cache:
                self.thumbnail_cache.move_to_end(key)
                item.setIcon(self.thumbnail_cache[key])
                item.setData(READY_ROLE,True)
                continue
            if item.data(READY_ROLE):continue
            source=self.sources[page['source']]
            try:
                source_unchanged(source)
                with pymupdf.open(source['path']) as document:
                    pdf_page=document[page['page']]
                    pdf_page.set_rotation((pdf_page.rotation+page['rotation'])%360)
                    width=self.page_size.value()*min(2,self.devicePixelRatioF())
                    scale=min(width/pdf_page.rect.width,width*2/pdf_page.rect.height)
                    pixmap=pdf_page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),colorspace=pymupdf.csRGB,alpha=False)
                    image=QImage(pixmap.samples,pixmap.width,pixmap.height,pixmap.stride,QImage.Format.Format_RGB888).copy()
                    paper=QPixmap.fromImage(image)
                    preview=QIcon(paper)
                    preview.addPixmap(paper,QIcon.Mode.Selected,QIcon.State.Off)
                    preview.addPixmap(paper,QIcon.Mode.Selected,QIcon.State.On)
            except Exception as error:
                preview=icon('info',32)
                item.setToolTip(item.toolTip()+'\nPreview unavailable: '+str(error))
                self.message.setText(str(error))
            self.thumbnail_cache[key]=preview
            budget=max(8,min(80,int(12_000_000/(self.page_size.value()*min(2,self.devicePixelRatioF()))**2/2)))
            while len(self.thumbnail_cache)>budget:
                self.thumbnail_cache.popitem(last=False)
            item.setIcon(preview)
            item.setData(READY_ROLE,True)
            self.timer.start(20)
            return

    def showEvent(self,event):
        super().showEvent(event)
        self.schedule_thumbnails()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'tools_layout'):
            narrow=self.width()<700
            self.tools_layout.setDirection(QBoxLayout.Direction.TopToBottom if narrow else QBoxLayout.Direction.LeftToRight)
            self.selection_hint.setVisible(self.width()>=950)
            self.page_size_label.setVisible(self.width()>=520)

    def finish(self,only_selected):
        try:
            pages=self.entries()
            if only_selected:
                pages=[pages[i] for i in self.selected()]
            plan=validate_plan({'version':1,'sources':self.sources,'pages':pages})
            for source in plan['sources']:
                source_unchanged(source)
            self.result_plan=plan
            self.accept()
        except ValueError as error:
            self.message.setText(str(error))

    def done(self,result):
        self.timer.stop();self.feedback_timer.stop()
        super().done(result)
