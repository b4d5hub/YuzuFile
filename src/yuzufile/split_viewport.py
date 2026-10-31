"""Scrollable, cursor-anchored page zoom without changing PDF geometry."""
import math
from PySide6.QtCore import Qt,QPoint,QPointF,QRectF,QSizeF,Signal
from PySide6.QtWidgets import QScrollArea


class SplitViewport(QScrollArea):
    view_changed=Signal(float)
    MARGIN=24

    def __init__(self,canvas):
        super().__init__();self.canvas=canvas;self.page_size=QSizeF()
        self.mode='width';self.zoom=1.;self.updating=False
        self.setWidget(canvas);self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(280,200)
        self.setAccessibleName('Scrollable split page preview')
        canvas.viewport_owner=self
        self.horizontalScrollBar().valueChanged.connect(canvas.update)
        self.verticalScrollBar().valueChanged.connect(canvas.update)

    def set_page_size(self,size,reset=True):
        size=QSizeF(size)
        if size==self.page_size and not reset:return
        self.page_size=size
        if self.page_size.isEmpty():
            self.canvas.display_size=None;self.canvas.resize(self.viewport().size());self.canvas.update()
        else:self.relayout()
        if reset:
            self.horizontalScrollBar().setValue(0);self.verticalScrollBar().setValue(0)

    def visible_canvas_rect(self):
        origin=self.canvas.mapFrom(self.viewport(),QPoint(0,0))
        return QRectF(QPointF(origin),QSizeF(self.viewport().size()))

    def relayout(self):
        if self.updating or self.page_size.isEmpty():return
        self.updating=True
        try:
            width=max(1,self.viewport().width()-2*self.MARGIN)
            height=max(1,self.viewport().height()-2*self.MARGIN)
            if self.mode=='width':self.zoom=width/(self.page_size.width()*96/72)
            elif self.mode=='page':self.zoom=min(width/(self.page_size.width()*96/72),height/(self.page_size.height()*96/72))
            display=QSizeF(self.page_size.width()*96/72*self.zoom,self.page_size.height()*96/72*self.zoom)
            self.canvas.display_size=display
            self.canvas.resize(max(self.viewport().width(),math.ceil(display.width()+2*self.MARGIN-1e-6)),
                               max(self.viewport().height(),math.ceil(display.height()+2*self.MARGIN-1e-6)))
            self.canvas.page_rect=self.canvas.fit_rect();self.canvas.update()
        finally:self.updating=False
        self.view_changed.emit(self.zoom)

    def fit_width(self):self.mode='width';self.relayout()
    def fit_page(self):self.mode='page';self.relayout()

    def set_zoom(self,value,anchor=None):
        if self.page_size.isEmpty():return
        anchor=QPointF(anchor) if anchor is not None else QPointF(self.viewport().rect().center())
        old=self.canvas.fit_rect()
        point=QPointF(self.canvas.mapFrom(self.viewport(),anchor.toPoint()))
        fractions=QPointF((point.x()-old.left())/old.width(),(point.y()-old.top())/old.height())
        self.mode='manual';self.zoom=max(.01,min(6.,float(value)))
        self.relayout()
        new=self.canvas.fit_rect()
        target=QPointF(new.left()+fractions.x()*new.width(),new.top()+fractions.y()*new.height())
        current=QPointF(self.canvas.mapFrom(self.viewport(),anchor.toPoint()))
        self.pan_by(current-target)

    def pan_by(self,delta):
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value()-round(delta.x()))
        self.verticalScrollBar().setValue(self.verticalScrollBar().value()-round(delta.y()))

    def resizeEvent(self,event):
        super().resizeEvent(event);self.relayout()

    def wheelEvent(self,event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.set_zoom(self.zoom*(1.2 if event.angleDelta().y()>0 else 1/1.2),event.position())
            event.accept()
        else:super().wheelEvent(event)
