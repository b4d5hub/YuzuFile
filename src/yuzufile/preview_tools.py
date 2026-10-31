"""Shared readable-page controls and bounded current-page rasterization."""
import math
import pymupdf
from PySide6.QtGui import QImage,QPixmap
from PySide6.QtWidgets import QWidget,QHBoxLayout,QPushButton,QSpinBox


def raster_page(page,zoom,dpr=1.,clip=None):
    rect=page.rect if clip is None else pymupdf.Rect(clip)&page.rect
    scale=min(max(1,zoom*96/72*dpr),math.sqrt(8_000_000/max(1,rect.get_area())),
              6000/max(1,rect.width,rect.height))
    pix=page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),clip=clip,
                       colorspace=pymupdf.csRGB,alpha=False)
    image=QImage(pix.samples,pix.width,pix.height,pix.stride,QImage.Format.Format_RGB888).copy()
    return QPixmap.fromImage(image)


class ZoomControls(QWidget):
    def __init__(self,viewport,compact=False):
        super().__init__();self.view=None
        layout=QHBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(5)
        self.fit_width=QPushButton('Width' if compact else 'Fit width');self.fit_page=QPushButton('Page' if compact else 'Fit page')
        self.fit_width.setToolTip('Fit width');self.fit_width.setAccessibleName('Fit width')
        self.fit_page.setToolTip('Fit page');self.fit_page.setAccessibleName('Fit page')
        self.minus=QPushButton('−');self.plus=QPushButton('+')
        for button,title in ((self.minus,'Zoom out'),(self.plus,'Zoom in')):
            button.setFixedWidth(30);button.setAccessibleName(title)
        self.percent=QSpinBox();self.percent.setRange(1,600);self.percent.setSuffix('%')
        self.percent.setSingleStep(10);self.percent.setFixedWidth(72);self.percent.setAccessibleName('Page zoom percentage')
        for widget in (self.fit_width,self.fit_page,self.minus,self.percent,self.plus):
            widget.setStyleSheet('padding:5px 6px;');layout.addWidget(widget)
        self.fit_width.clicked.connect(lambda:self.view.fit_width())
        self.fit_page.clicked.connect(lambda:self.view.fit_page())
        self.minus.clicked.connect(lambda:self.view.set_zoom(self.view.zoom/1.2))
        self.plus.clicked.connect(lambda:self.view.set_zoom(self.view.zoom*1.2))
        self.percent.valueChanged.connect(lambda value:self.view.set_zoom(value/100))
        self.bind(viewport)

    def bind(self,viewport):
        if self.view is not None:self.view.view_changed.disconnect(self.sync)
        self.view=viewport;viewport.view_changed.connect(self.sync);self.sync(viewport.zoom)

    def sync(self,zoom):
        self.percent.blockSignals(True);self.percent.setValue(round(zoom*100));self.percent.blockSignals(False)
