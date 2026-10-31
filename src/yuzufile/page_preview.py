"""Readable inspection of pages in their planned output order."""
from pathlib import Path
import pymupdf
from PySide6.QtCore import Qt,QTimer,QSizeF
from PySide6.QtWidgets import QHBoxLayout,QLabel,QPushButton
from yuzufile.spread_preview import SplitCanvas
from yuzufile.split_viewport import SplitViewport
from yuzufile.preview_tools import ZoomControls,raster_page
from yuzufile.organize import source_unchanged
from yuzufile.tool_window import ToolDialog
from yuzufile.ui_components import IconButton


class PagePreview(ToolDialog):
    def __init__(self,parent,sources,pages,index=0):
        super().__init__(parent,title='View page');self.sources=sources;self.pages=pages;self.index=index
        self.document=None;self.pdf_page=None
        self.setWindowTitle('View page');self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint,True)
        available=self.screen().availableGeometry()
        self.resize(min(1280,int(available.width()*.94)),min(1000,int(available.height()*.94)))
        layout=self.body_layout;layout.setContentsMargins(12,8,12,10);bar=QHBoxLayout()
        self.previous=IconButton('arrow-left','Previous page');self.next=IconButton('arrow-right','Next page');self.position=QLabel()
        bar.addWidget(self.previous);bar.addWidget(self.position,1);bar.addWidget(self.next);layout.addLayout(bar)
        self.caption=QLabel();self.caption.setObjectName('muted');self.caption.hide()
        self.canvas=SplitCanvas();self.canvas.selected=False
        self.view=SplitViewport(self.canvas);self.view.setAccessibleName('Full page reading view')
        self.controls=ZoomControls(self.view);bar.addWidget(self.controls)
        layout.addWidget(self.view,1)
        self.hint=QLabel('Scroll to read · Ctrl+scroll to zoom · Space+drag to pan');self.hint.setObjectName('muted')
        close=QPushButton('Done');close.clicked.connect(self.accept)
        footer=QHBoxLayout();footer.addWidget(self.hint,1);footer.addWidget(close);layout.addLayout(footer)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.render)
        self.view.view_changed.connect(lambda:self.timer.start(140))
        self.previous.clicked.connect(lambda:self.show_page(self.index-1));self.next.clicked.connect(lambda:self.show_page(self.index+1))
        self.show_page(index)

    def show_page(self,index):
        self.timer.stop();self.pdf_page=None
        self.hint.setText('Scroll to read · Ctrl+scroll to zoom · Space+drag to pan')
        if self.document is not None:self.document.close();self.document=None
        self.index=max(0,min(len(self.pages)-1,index));entry=self.pages[self.index];source=self.sources[entry['source']]
        self.position.setText(f'Output page {self.index+1} of {len(self.pages)}')
        self.caption.setText(f"{Path(source['path']).name} · Original page {entry['page']+1} · Rotation +{entry['rotation']}°")
        self.position.setToolTip(self.caption.text());self.header.title.setToolTip(self.caption.text())
        self.previous.setEnabled(self.index>0);self.next.setEnabled(self.index<len(self.pages)-1)
        try:
            source_unchanged(source);self.document=pymupdf.open(source['path']);self.pdf_page=self.document[entry['page']]
            self.pdf_page.set_rotation((self.pdf_page.rotation+entry['rotation'])%360)
            self.view.set_page_size(QSizeF(self.pdf_page.rect.width,self.pdf_page.rect.height));self.render()
        except (OSError,ValueError,RuntimeError) as error:
            from PySide6.QtGui import QPixmap
            self.canvas.pixmap=QPixmap();self.canvas.update();self.hint.setText(str(error))

    def render(self):
        self.timer.stop()
        if self.pdf_page is None:return
        try:self.canvas.pixmap=raster_page(self.pdf_page,self.view.zoom,self.devicePixelRatioF());self.canvas.update()
        except (ValueError,RuntimeError) as error:self.hint.setText(str(error))

    def done(self,result):
        self.timer.stop();self.pdf_page=None
        if self.document is not None:self.document.close();self.document=None
        super().done(result)
