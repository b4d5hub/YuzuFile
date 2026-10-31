"""Direct page manipulation: crop handles, alignment guide and live feedback."""
import math

from PySide6.QtCore import Qt,QPointF,QRectF,Signal
from PySide6.QtGui import QColor,QPainter,QPen,QPixmap
from PySide6.QtWidgets import QWidget

from yuzufile.ui_style import COLORS


class PageCanvas(QWidget):
    started=Signal()
    crop_changed=Signal(object)
    angle_changed=Signal(float)
    finished=Signal()

    def __init__(self):
        super().__init__()
        self.setMinimumSize(260,220)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAccessibleName('Visual page crop and alignment')
        self.setToolTip('Drag an edge or corner to crop. Drag inside to move. Arrow keys nudge; Shift moves farther.')
        self.pixmap=QPixmap()
        self.crop=[0.,0.,1.,1.]
        self.minimum=(.05,.05)
        self.tool='crop'
        self.crop_enabled=True
        self.page_rect=QRectF()
        self.active=None
        self.origin=None
        self.initial=None
        self.line=None
        self.zoom=1.
        self.pan=QPointF()
        self.pan_start=None
        self.space_down=False
        self.display_size=None;self.viewport_owner=None

    def fit_rect(self):
        if self.display_size is not None:
            size=self.display_size
            return QRectF((self.width()-size.width())/2,(self.height()-size.height())/2,size.width(),size.height())
        if self.pixmap.isNull():return QRectF()
        available=self.rect().adjusted(14,14,-14,-14)
        size=self.pixmap.size().scaled(available.size(),Qt.AspectRatioMode.KeepAspectRatio)
        width,height=size.width()*self.zoom,size.height()*self.zoom
        return QRectF((self.width()-width)/2+self.pan.x(),(self.height()-height)/2+self.pan.y(),width,height)

    def fit_view(self):
        if self.viewport_owner:
            self.viewport_owner.fit_width();return
        self.zoom=1.;self.pan=QPointF();self.update()

    def wheelEvent(self,event):
        if self.viewport_owner:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                anchor=self.mapTo(self.viewport_owner.viewport(),event.position().toPoint())
                self.viewport_owner.set_zoom(self.viewport_owner.zoom*(1.2 if event.angleDelta().y()>0 else 1/1.2),anchor)
                event.accept()
            else:event.ignore()
            return
        if self.pixmap.isNull():return
        point=event.position();fraction=self.normalized(point)
        self.zoom=max(1,min(5,self.zoom*(1.15 if event.angleDelta().y()>0 else 1/1.15)))
        if self.zoom==1:self.pan=QPointF()
        else:
            new=self.fit_rect()
            self.pan+=QPointF(point.x()-(new.left()+fraction.x()*new.width()),point.y()-(new.top()+fraction.y()*new.height()))
        self.update();event.accept()

    def crop_rect(self):
        r=self.fit_rect()
        x0,y0,x1,y1=self.crop
        return QRectF(r.x()+x0*r.width(),r.y()+y0*r.height(),(x1-x0)*r.width(),(y1-y0)*r.height())

    def paintEvent(self,event):
        p=QPainter(self)
        p.fillRect(self.rect(),QColor(COLORS['canvas']))
        if self.pixmap.isNull():return
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r=self.fit_rect()
        self.page_rect=r
        p.drawPixmap(r.toRect(),self.pixmap)
        if self.crop_enabled:
            crop=self.crop_rect()
            shade=QColor(COLORS['text']);shade.setAlpha(120)
            p.fillRect(QRectF(r.left(),r.top(),r.width(),max(0,crop.top()-r.top())),shade)
            p.fillRect(QRectF(r.left(),crop.bottom(),r.width(),max(0,r.bottom()-crop.bottom())),shade)
            p.fillRect(QRectF(r.left(),crop.top(),max(0,crop.left()-r.left()),crop.height()),shade)
            p.fillRect(QRectF(crop.right(),crop.top(),max(0,r.right()-crop.right()),crop.height()),shade)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(QPen(QColor(COLORS['accent']),2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(crop)
            grid=QColor(COLORS['accent']);grid.setAlpha(65)
            p.setPen(QPen(grid,1))
            for f in (1/3,2/3):
                p.drawLine(QPointF(crop.left()+crop.width()*f,crop.top()),QPointF(crop.left()+crop.width()*f,crop.bottom()))
                p.drawLine(QPointF(crop.left(),crop.top()+crop.height()*f),QPointF(crop.right(),crop.top()+crop.height()*f))
            p.setPen(QPen(QColor(COLORS['accent']),1.5))
            p.setBrush(QColor('white'))
            for x,y in self.handles().values():p.drawRoundedRect(QRectF(x-7,y-7,14,14),4,4)
        if self.tool=='straighten':
            guide=QColor(COLORS['accent']);guide.setAlpha(45)
            p.setPen(QPen(guide,1))
            for y in range(int(r.top())+20,int(r.bottom()),30):
                p.drawLine(QPointF(r.left(),y),QPointF(r.right(),y))
        if self.line:
            a,b=self.line
            p.setPen(QPen(QColor(COLORS['accent']),2,Qt.PenStyle.DashLine))
            p.drawLine(a,b)
            p.setBrush(QColor('white'))
            p.drawEllipse(a,4,4);p.drawEllipse(b,4,4)

    def handles(self):
        r=self.crop_rect()
        visible=self.viewport_owner.visible_canvas_rect().intersected(r) if self.viewport_owner else r
        center=visible.center() if not visible.isEmpty() else r.center()
        return {'nw':(r.left(),r.top()),'n':(center.x(),r.top()),'ne':(r.right(),r.top()),
                'e':(r.right(),center.y()),'se':(r.right(),r.bottom()),'s':(center.x(),r.bottom()),
                'sw':(r.left(),r.bottom()),'w':(r.left(),center.y())}

    def hit(self,point):
        if not self.crop_enabled:return None
        for name,(x,y) in self.handles().items():
            if abs(point.x()-x)<=12 and abs(point.y()-y)<=12:return name
        r=self.crop_rect()
        if r.adjusted(-7,-7,7,7).contains(point):
            if abs(point.x()-r.left())<7:return 'w'
            if abs(point.x()-r.right())<7:return 'e'
            if abs(point.y()-r.top())<7:return 'n'
            if abs(point.y()-r.bottom())<7:return 's'
            if r.contains(point):return 'move'
        return 'draw' if self.fit_rect().contains(point) else None

    def normalized(self,point):
        r=self.fit_rect()
        return QPointF(max(0,min(1,(point.x()-r.left())/max(1,r.width()))),
                       max(0,min(1,(point.y()-r.top())/max(1,r.height()))))

    def set_crop(self,crop,emit=False):
        self.crop=list(crop)
        self.setAccessibleDescription('Crop: '+', '.join(f'{v*100:.1f}%' for v in crop))
        self.update()
        if emit:self.crop_changed.emit(self.crop[:])

    def mousePressEvent(self,event):
        self.setFocus()
        if event.button()==Qt.MouseButton.MiddleButton or (event.button()==Qt.MouseButton.LeftButton and (self.space_down or self.tool=='pan')):
            self.pan_start=(event.globalPosition(),None) if self.viewport_owner else (event.position(),QPointF(self.pan))
            self.setCursor(Qt.CursorShape.ClosedHandCursor);return
        if event.button()!=Qt.MouseButton.LeftButton or not self.fit_rect().contains(event.position()):return
        self.setFocus()
        self.active='line' if self.tool=='straighten' else self.hit(event.position())
        if not self.active:return
        self.started.emit()
        self.origin=event.position()
        self.initial=self.crop[:]
        if self.active=='line':self.line=(self.origin,self.origin)
        self.update()

    def mouseMoveEvent(self,event):
        if self.pan_start:
            origin,pan=self.pan_start
            if self.viewport_owner:
                self.viewport_owner.pan_by(event.globalPosition()-origin);self.pan_start=(event.globalPosition(),None)
            else:self.pan=pan+event.position()-origin
            self.update();return
        if not self.active:
            name=self.hit(event.position()) if self.tool=='crop' else ('pan' if self.tool=='pan' else 'line')
            cursor={'nw':Qt.CursorShape.SizeFDiagCursor,'se':Qt.CursorShape.SizeFDiagCursor,
                    'ne':Qt.CursorShape.SizeBDiagCursor,'sw':Qt.CursorShape.SizeBDiagCursor,
                    'n':Qt.CursorShape.SizeVerCursor,'s':Qt.CursorShape.SizeVerCursor,
                    'e':Qt.CursorShape.SizeHorCursor,'w':Qt.CursorShape.SizeHorCursor,
                    'move':Qt.CursorShape.SizeAllCursor,'line':Qt.CursorShape.CrossCursor,'draw':Qt.CursorShape.CrossCursor,
                    'pan':Qt.CursorShape.OpenHandCursor}.get(name,Qt.CursorShape.ArrowCursor)
            self.setCursor(cursor)
            return
        if self.active=='line':
            self.line=(self.origin,event.position())
            self.update()
            return
        point,start=self.normalized(event.position()),self.normalized(self.origin)
        dx,dy=point.x()-start.x(),point.y()-start.y()
        x0,y0,x1,y1=self.initial
        mw,mh=self.minimum
        if self.active=='move':
            dx=max(-x0,min(1-x1,dx));dy=max(-y0,min(1-y1,dy))
            x0+=dx;x1+=dx;y0+=dy;y1+=dy
        elif self.active=='draw':
            x0,x1=sorted((start.x(),point.x()));y0,y1=sorted((start.y(),point.y()))
            x1=min(1,max(x1,x0+mw));y1=min(1,max(y1,y0+mh))
            x0=min(x0,x1-mw);y0=min(y0,y1-mh)
        else:
            if 'w' in self.active:x0=max(0,min(x1-mw,x0+dx))
            if 'e' in self.active:x1=min(1,max(x0+mw,x1+dx))
            if 'n' in self.active:y0=max(0,min(y1-mh,y0+dy))
            if 's' in self.active:y1=min(1,max(y0+mh,y1+dy))
        self.set_crop([x0,y0,x1,y1],True)

    def mouseReleaseEvent(self,event):
        if self.pan_start:self.pan_start=None;self.setCursor(Qt.CursorShape.OpenHandCursor);return
        if not self.active:return
        if self.active=='line' and self.line:
            a,b=self.line
            dx,dy=b.x()-a.x(),b.y()-a.y()
            if abs(dx)>20:
                if dx<0:dx,dy=-dx,-dy
                self.angle_changed.emit(max(-45,min(45,math.degrees(math.atan2(dy,dx)))))
        self.active=None;self.line=None
        self.finished.emit()
        self.update()

    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Space:self.space_down=True;event.accept();return
        keys={Qt.Key.Key_Left:(-1,0),Qt.Key.Key_Right:(1,0),Qt.Key.Key_Up:(0,-1),Qt.Key.Key_Down:(0,1)}
        if event.key() not in keys or self.tool!='crop' or not self.crop_enabled:
            return super().keyPressEvent(event)
        dx,dy=keys[event.key()]
        step=.02 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else .002
        dx*=step;dy*=step
        x0,y0,x1,y1=self.crop
        self.started.emit()
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            x1=max(x0+self.minimum[0],min(1,x1+dx));y1=max(y0+self.minimum[1],min(1,y1+dy))
        else:
            dx=max(-x0,min(1-x1,dx));dy=max(-y0,min(1-y1,dy))
            x0+=dx;x1+=dx;y0+=dy;y1+=dy
        self.set_crop([x0,y0,x1,y1],True)
        self.finished.emit()
        event.accept()

    def keyReleaseEvent(self,event):
        if event.key()==Qt.Key.Key_Space:self.space_down=False;event.accept()
        else:super().keyReleaseEvent(event)

    def focusOutEvent(self,event):
        self.space_down=False;super().focusOutEvent(event)
