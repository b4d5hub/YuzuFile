"""A document-order workspace for merging whole PDFs through the page planner."""
from pathlib import Path
from copy import deepcopy

from PySide6.QtCore import Qt,QRectF,QSize
from PySide6.QtGui import QColor,QPainter,QPen,QShortcut,QKeySequence,QFont
from PySide6.QtWidgets import (QAbstractItemView,QFileDialog,QFrame,QHBoxLayout,QLabel,
    QListWidget,QListWidgetItem,QPushButton,QStyledItemDelegate,QStyle)

from yuzufile.icons import icon
from yuzufile.organize import MAX_BYTES,MAX_PAGES,MAX_SOURCES,inspect_source,source_unchanged,validate_plan
from yuzufile.tool_window import ToolDialog
from yuzufile.ui_components import IconButton
from yuzufile.ui_style import COLORS


class MergeDelegate(QStyledItemDelegate):
    def controls(self,rect):
        rect=QRectF(rect)
        return (QRectF(rect.right()-72,rect.top()+8,28,20),
                QRectF(rect.right()-72,rect.top()+30,28,20),
                QRectF(rect.right()-36,rect.top()+16,26,26))

    def paint(self,painter,option,index):
        painter.save();painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        selected=bool(option.state&QStyle.StateFlag.State_Selected)
        rect=QRectF(option.rect).adjusted(1,3,-1,-3)
        painter.setPen(QPen(QColor(COLORS['accent'] if selected else '#eeeeee'),1))
        painter.setBrush(QColor('#eeeeee' if selected else '#f0f0f0'));painter.drawRoundedRect(rect,12,12)
        painter.setPen(QColor(COLORS['muted']));painter.drawText(QRectF(rect.left()+10,rect.top(),28,rect.height()),Qt.AlignmentFlag.AlignCenter,str(index.row()+1))
        icon('file-text',18).paint(painter,QRectF(rect.left()+46,rect.center().y()-9,18,18).toRect())
        source=index.data(Qt.ItemDataRole.UserRole)
        available=max(20,rect.width()-164)
        text_rect=QRectF(rect.left()+78,rect.top()+8,available,22)
        painter.setPen(QColor(COLORS['text']));painter.setFont(option.font)
        painter.drawText(text_rect,Qt.AlignmentFlag.AlignVCenter,option.fontMetrics.elidedText(Path(source['path']).name,Qt.TextElideMode.ElideMiddle,round(available)))
        size=f"{source['size']/1_000_000:.1f} MB" if source['size']>=1_000_000 else f"{source['size']/1000:.1f} KB"
        detail=f"{source['pages']} {'page' if source['pages']==1 else 'pages'} · {size}"
        font=QFont(option.font);font.setPointSizeF(max(8,font.pointSizeF()-1));painter.setFont(font);painter.setPen(QColor(COLORS['muted']))
        painter.drawText(text_rect.translated(0,20),Qt.AlignmentFlag.AlignVCenter,detail)
        up,down,remove=self.controls(option.rect)
        for area,glyph,enabled in ((up,'chevron-up',index.row()>0),(down,'chevron-down',index.row()<index.model().rowCount()-1),(remove,'x',True)):
            painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor('#e3e3e3'));painter.drawRoundedRect(area,6,6)
            painter.save()
            if glyph=='chevron-up':
                painter.translate(area.center());painter.rotate(180)
                icon('chevron-down',14,COLORS['icon'] if enabled else '#b9b9b9').paint(painter,QRectF(-7,-7,14,14).toRect())
            else:icon(glyph,14,COLORS['icon'] if enabled else '#b9b9b9').paint(painter,area.adjusted(7,3,-7,-3).toRect())
            painter.restore()
        painter.restore()


class MergeList(QListWidget):
    def __init__(self,owner):
        super().__init__();self.owner=owner;self._action=False
        self.setAccessibleName('PDF documents in merge order')
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction);self.setDropIndicatorShown(True)
        self.setItemDelegate(MergeDelegate(self));self.setSpacing(2)
        self.setStyleSheet('QListWidget {background:transparent;border:0;} QListWidget::drop-indicator {background:#ed6b2e;height:3px;}')
        self.model().rowsMoved.connect(owner.update_count)

    def mousePressEvent(self,event):
        index=self.indexAt(event.position().toPoint())
        if event.button()==Qt.MouseButton.LeftButton and index.isValid():
            for action,area in zip(('up','down','remove'),self.itemDelegate().controls(self.visualItemRect(self.item(index.row())))):
                if area.contains(event.position()):
                    self._action=True
                    if action=='remove':self.owner.remove_document(index.row())
                    else:self.owner.move_document(index.row(),-1 if action=='up' else 1)
                    event.accept();return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self,event):
        if self._action:self._action=False;event.accept();return
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self,event):
        from yuzufile.desktop_drag import pdf_paths,accept_copy
        if event.mimeData().hasUrls():
            if pdf_paths(event.mimeData()):accept_copy(event)
            else:event.ignore()
        else:super().dragEnterEvent(event)

    def dragMoveEvent(self,event):
        from yuzufile.desktop_drag import pdf_paths,accept_copy
        if event.mimeData().hasUrls():
            if pdf_paths(event.mimeData()):accept_copy(event)
            else:event.ignore()
        else:super().dragMoveEvent(event)

    def dropEvent(self,event):
        from yuzufile.desktop_drag import pdf_paths,accept_copy
        if event.mimeData().hasUrls():
            paths=pdf_paths(event.mimeData())
            if paths and accept_copy(event):self.owner.add_files(paths)
            else:event.ignore()
        else:
            super().dropEvent(event);self.owner.update_count()


class MergeDialog(ToolDialog):
    def __init__(self,parent,paths=(),plan=None):
        super().__init__(parent,title='Merge PDFs')
        available=self.screen().availableGeometry()
        self.resize(min(600,int(available.width()*.9)),min(590,int(available.height()*.9)))
        self.result_plan=None;self.output_directory=getattr(parent,'output_directory',None)
        layout=self.body_layout;layout.setContentsMargins(18,14,18,14);layout.setSpacing(8)
        bar=QHBoxLayout();self.count_label=QLabel('Document order');self.count_label.setObjectName('muted');bar.addWidget(self.count_label,1)
        self.add_button=QPushButton('Add PDFs');self.add_button.setIcon(icon('plus',16));self.add_button.clicked.connect(self.pick_files);bar.addWidget(self.add_button)
        layout.addLayout(bar)
        self.documents=MergeList(self);layout.addWidget(self.documents,1)
        self.empty_label=QLabel('Add PDFs, then drag them into the order you want.');self.empty_label.setObjectName('muted');self.empty_label.setWordWrap(True)
        layout.addWidget(self.empty_label)
        self.message=QLabel();self.message.setWordWrap(True);self.message.hide();layout.addWidget(self.message)
        divider=QFrame();divider.setFrameShape(QFrame.Shape.HLine);divider.setObjectName('toolDivider');layout.addWidget(divider)
        footer=QHBoxLayout();self.folder_button=IconButton('folder-open','Choose output folder',self.choose_output);footer.addWidget(self.folder_button)
        self.destination=QLabel();self.destination.setObjectName('muted');footer.addWidget(self.destination,1)
        self.merge_button=QPushButton('Merge PDFs');self.merge_button.setObjectName('primary');self.merge_button.clicked.connect(self.finish);footer.addWidget(self.merge_button)
        layout.addLayout(footer);self.update_destination()
        for sequence,action in (('Delete',lambda:self.remove_document(self.documents.currentRow())),
            ('Alt+Up',lambda:self.move_document(self.documents.currentRow(),-1)),
            ('Alt+Down',lambda:self.move_document(self.documents.currentRow(),1)),('Ctrl+O',self.pick_files)):
            shortcut=QShortcut(QKeySequence(sequence),self);shortcut.activated.connect(action)
        if plan:
            try:
                clean=validate_plan(plan);order=list(dict.fromkeys(p['source'] for p in clean['pages']))
                for number in order:self.append_source(clean['sources'][number])
            except ValueError as error:self.feedback(str(error))
        else:self.add_files(paths)
        self.update_count()

    @property
    def sources(self):return [deepcopy(self.documents.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(self.documents.count())]
    @property
    def outdir(self):return self.output_directory

    def append_source(self,source):
        item=QListWidgetItem(Path(source['path']).name);item.setData(Qt.ItemDataRole.UserRole,deepcopy(source))
        item.setToolTip(source['path']);item.setSizeHint(QSize(200,62));self.documents.addItem(item)

    def feedback(self,text):self.message.setText(text);self.message.setVisible(bool(text))

    def add_files(self,paths):
        if not paths:return
        try:
            additions=[inspect_source(path) for path in paths]
            combined=self.sources+additions
            if len(combined)>MAX_SOURCES or sum(s['pages'] for s in combined)>MAX_PAGES:
                raise ValueError('Merge supports up to 50 PDFs and 2,000 pages.')
            if sum(s['size'] for s in combined)>MAX_BYTES:raise ValueError('The combined input size must not exceed 1 GB.')
            for source in additions:self.append_source(source)
            self.feedback('');self.update_count()
        except (OSError,ValueError,RuntimeError) as error:self.feedback(str(error))

    def pick_files(self):
        paths,_=QFileDialog.getOpenFileNames(self,'Add PDFs to merge','','PDF files (*.pdf)');self.add_files(paths)

    def remove_document(self,index):
        if 0<=index<self.documents.count():self.documents.takeItem(index);self.update_count()

    def move_document(self,index,delta):
        target=index+delta
        if not 0<=index<self.documents.count() or not 0<=target<self.documents.count():return
        item=self.documents.takeItem(index);self.documents.insertItem(target,item);self.documents.setCurrentRow(target);self.update_count()

    def update_count(self,*args):
        count=self.documents.count();pages=sum(s['pages'] for s in self.sources)
        self.count_label.setText(f'Document order · {count} PDFs · {pages} pages')
        self.empty_label.setVisible(not count);self.merge_button.setEnabled(count>=2);self.documents.viewport().update()

    def update_destination(self):
        text=Path(self.output_directory).name if self.output_directory else 'Beside the first source PDF'
        self.destination.setText(text);self.destination.setToolTip(str(self.output_directory or 'Save beside the first source PDF'))

    def choose_output(self):
        folder=QFileDialog.getExistingDirectory(self,'Choose output folder',str(self.output_directory or Path.home()))
        if folder:self.output_directory=Path(folder).absolute();self.update_destination()

    def finish(self):
        if self.documents.count()<2:return
        try:
            sources=self.sources
            for source in sources:source_unchanged(source)
            pages=[dict(source=index,page=page,rotation=0) for index,source in enumerate(sources) for page in range(source['pages'])]
            self.result_plan=validate_plan(dict(version=1,sources=sources,pages=pages,action='merge'))
            self.result_plan['action']='merge';self.accept()
        except (OSError,ValueError,RuntimeError) as error:self.feedback(str(error))
