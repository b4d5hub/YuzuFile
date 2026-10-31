"""A sculpted file-centred tool menu with real, accessible Qt buttons."""
import math
from PySide6.QtCore import Qt,QPointF,QRectF,QSize
from PySide6.QtGui import QColor,QFont,QLinearGradient,QPainter,QPainterPath,QPainterPathStroker,QPen,QRegion
from PySide6.QtWidgets import QCheckBox,QPushButton,QSizePolicy,QWidget
from yuzufile.icons import icon
from yuzufile.ui_style import COLORS


def polar(center,radius,angle):
    radians=math.radians(angle)
    return QPointF(center.x()+radius*math.cos(radians),center.y()+radius*math.sin(radians))


def wedge(center,inner,outer,start,end):
    """Rounded annular sector, including rounded corners at the inner edge."""
    path=QPainterPath();path.moveTo(polar(center,outer-7,start))
    path.quadTo(polar(center,outer,start),polar(center,outer,start+3))
    for i in range(1,25):path.lineTo(polar(center,outer,start+3+(end-start-6)*i/24))
    path.quadTo(polar(center,outer,end),polar(center,outer-7,end))
    path.lineTo(polar(center,inner+7,end))
    path.quadTo(polar(center,inner,end),polar(center,inner,end-5))
    for i in range(1,25):path.lineTo(polar(center,inner,end-5-(end-start-10)*i/24))
    path.quadTo(polar(center,inner,start),polar(center,inner+7,start))
    path.closeSubpath();return path


def initialize(button,title,caption,glyph,short):
    button.title,button.caption,button.glyph,button.short=title,caption,glyph,short
    button.path=QPainterPath();button.label_point=QPointF();button.hit_point=QPointF()
    button.setAccessibleName(title);button.setAccessibleDescription(caption)
    button.setToolTip(caption)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    button.setAttribute(Qt.WidgetAttribute.WA_Hover)


def shape(button,path,position):
    bounds=path.boundingRect().toAlignedRect().adjusted(-2,-2,2,2)
    button.setGeometry(bounds)
    button.path=path.translated(-bounds.x(),-bounds.y())
    button.label_point=position-QPointF(bounds.x(),bounds.y())
    button.hit_point=button.label_point
    edge=QPainterPathStroker();edge.setWidth(3)
    mask=button.path.united(edge.createStroke(button.path))
    button.setMask(QRegion(mask.toFillPolygon().toPolygon()))
    button.update()


def paint(button):
    p=QPainter(button);p.setRenderHint(QPainter.RenderHint.Antialiasing)
    selected=getattr(button,'drag_hovered',False) if getattr(button,'drag_active',False) else button.isChecked()
    pressed=button.isDown()
    fill=QLinearGradient(0,0,0,button.height())
    if selected:
        fill.setColorAt(0,QColor('#ff792b' if not pressed else '#e45b18'))
        fill.setColorAt(1,QColor('#f36b24' if not pressed else '#d95415'))
    else:
        fill.setColorAt(0,QColor('#ffffff' if button.underMouse() else '#f8f8f7'))
        fill.setColorAt(1,QColor('#eeeeec' if button.underMouse() else '#e6e6e3'))
        if pressed:fill.setColorAt(0,QColor('#deded9'))
    p.setBrush(fill);p.setPen(QPen(QColor('#e96320' if selected else '#d1d4d5'),1))
    p.drawPath(button.path)
    p.save();p.setClipPath(button.path)
    p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(QColor(255,255,255,120),1))
    p.drawPath(button.path.translated(0,1));p.restore()
    color='#ffffff' if selected else '#42484b'
    center=button.label_point
    icon(button.glyph,21,color).paint(p,QRectF(center.x()-10.5,center.y()-23,21,21).toRect())
    font=QFont('Segoe UI');font.setPixelSize(12);font.setWeight(QFont.Weight.Medium)
    p.setFont(font);p.setPen(QColor(color))
    text=button.short if button.short in {'OCR','No OCR'} else button.short.capitalize()
    p.drawText(QRectF(center.x()-55,center.y()+3,110,20),Qt.AlignmentFlag.AlignCenter,text)
    if button.hasFocus() and getattr(button,'keyboard_focus',False):
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(COLORS['accent']),2,Qt.PenStyle.DotLine));p.drawPath(button.path)


def arrow(button,event):
    direction={Qt.Key.Key_Right:1,Qt.Key.Key_Down:1,Qt.Key.Key_Left:-1,Qt.Key.Key_Up:-1}.get(event.key())
    if direction:
        button.parentWidget().focus_next(button,direction);event.accept();return True
    return False


class WheelTool(QCheckBox):
    def __init__(self,parent,title,caption,glyph,short):
        super().__init__(title,parent);initialize(self,title,caption,glyph,short)
    def paintEvent(self,event):paint(self)
    def hitButton(self,point):return self.path.contains(QPointF(point))
    def keyPressEvent(self,event):
        if not arrow(self,event):super().keyPressEvent(event)
    def enterEvent(self,event):self.update();super().enterEvent(event)
    def leaveEvent(self,event):self.update();super().leaveEvent(event)
    def focusInEvent(self,event):
        self.keyboard_focus=event.reason() in (Qt.FocusReason.TabFocusReason,Qt.FocusReason.BacktabFocusReason,Qt.FocusReason.ShortcutFocusReason)
        super().focusInEvent(event);self.update()


class WheelAction(QPushButton):
    def __init__(self,parent,title,caption,glyph,short,callback):
        super().__init__(title,parent);initialize(self,title,caption,glyph,short)
        self.clicked.connect(callback)
    def paintEvent(self,event):paint(self)
    def hitButton(self,point):return self.path.contains(QPointF(point))
    def keyPressEvent(self,event):
        if not arrow(self,event):super().keyPressEvent(event)
    def enterEvent(self,event):self.update();super().enterEvent(event)
    def leaveEvent(self,event):self.update();super().leaveEvent(event)
    def focusInEvent(self,event):
        self.keyboard_focus=event.reason() in (Qt.FocusReason.TabFocusReason,Qt.FocusReason.BacktabFocusReason,Qt.FocusReason.ShortcutFocusReason)
        super().focusInEvent(event);self.update()


class ToolWheel(QWidget):
    def __init__(self,center_button):
        super().__init__();self.buttons=[];self.center_button=center_button
        center_button.setParent(self)
        self.setAccessibleName('PDF tool wheel')
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        self.setFixedHeight(356)

    def add_tool(self,title,caption,glyph,short):
        button=WheelTool(self,title,caption,glyph,short);self.buttons.append(button);return button

    def add_action(self,title,caption,glyph,short,callback):
        button=WheelAction(self,title,caption,glyph,short,callback);self.buttons.append(button);return button

    def sizeHint(self):return QSize(368,356)
    def minimumSizeHint(self):return QSize(300,326)

    def geometry_values(self):
        return QPointF(self.width()/2,self.height()/2),min(self.width(),self.height())/2-17

    def resizeEvent(self,event):
        center,radius=self.geometry_values();count=max(1,len(self.buttons));step=360/count
        for i,button in enumerate(self.buttons):
            angle=-90+i*step
            path=wedge(center,62,radius-4,angle-step/2+1.3,angle+step/2-1.3)
            shape(button,path,polar(center,(radius+62)/2,angle))
        self.center_button.setGeometry(round(center.x()-57),round(center.y()-57),114,114)
        super().resizeEvent(event)

    def focus_next(self,button,direction):
        self.buttons[(self.buttons.index(button)+direction)%len(self.buttons)].setFocus(Qt.FocusReason.TabFocusReason)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        center,radius=self.geometry_values();rect=QRectF(center.x()-radius,center.y()-radius,radius*2,radius*2)
        p.setPen(Qt.PenStyle.NoPen)
        for spread in range(10,0,-1):
            p.setBrush(QColor(0,0,0,2));p.drawEllipse(rect.adjusted(-spread,4-spread,spread,4+spread))
        gradient=QLinearGradient(rect.topLeft(),rect.bottomLeft())
        gradient.setColorAt(0,QColor('#fafaf8'));gradient.setColorAt(.5,QColor('#e9e9e5'));gradient.setColorAt(1,QColor('#d7d7d2'))
        p.setBrush(gradient);p.setPen(QPen(QColor('#c9c9c2'),1));p.drawEllipse(rect)
        p.setBrush(QColor('#e0e1da'));p.setPen(QPen(QColor('#f9faf5'),1));p.drawEllipse(QRectF(center.x()-63,center.y()-63,126,126))
