"""Visual controls with native button semantics and accessible labels."""
from PySide6.QtCore import Qt, QSize, QRectF, QRect
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QFontMetrics
from PySide6.QtWidgets import QCheckBox, QPushButton, QScrollArea, QSizePolicy, QWidget, QVBoxLayout,QFrame,QHBoxLayout,QButtonGroup

from yuzufile.icons import icon
from yuzufile.ui_style import COLORS


class OptionSegments(QFrame):
    """A compact inset preset selector, bound to an existing combo model."""
    def __init__(self,combo):
        super().__init__();self.setObjectName('segmented');self.combo=combo
        layout=QHBoxLayout(self);layout.setContentsMargins(2,2,2,2);layout.setSpacing(1)
        self.group=QButtonGroup(self);self.group.setExclusive(True);self.buttons=[]
        for index in range(combo.count()):
            button=QPushButton(combo.itemText(index));button.setObjectName('segment')
            button.setCheckable(True);button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setAccessibleName(combo.accessibleName()+': '+combo.itemText(index))
            button.clicked.connect(lambda checked=False,i=index:combo.setCurrentIndex(i))
            self.group.addButton(button,index);layout.addWidget(button);self.buttons.append(button)
        combo.currentIndexChanged.connect(self.sync);self.sync(combo.currentIndex())
    def sync(self,index):
        for i,button in enumerate(self.buttons):button.setChecked(i==index)


class IconButton(QPushButton):
    def __init__(self,glyph,title,callback=None,parent=None):
        super().__init__(parent)
        self.setObjectName('iconButton')
        self.setIcon(icon(glyph,18))
        self.setIconSize(QSize(18,18))
        self.setFixedSize(36,36)
        self.setAccessibleName(title)
        self.setToolTip(title)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if callback:
            self.clicked.connect(callback)

    def focusInEvent(self,event):
        self.setProperty('keyboardFocus',event.reason() in (
            Qt.FocusReason.TabFocusReason,Qt.FocusReason.BacktabFocusReason,Qt.FocusReason.ShortcutFocusReason))
        self.style().unpolish(self);self.style().polish(self)
        super().focusInEvent(event)

    def focusOutEvent(self,event):
        self.setProperty('keyboardFocus',False)
        self.style().unpolish(self);self.style().polish(self)
        super().focusOutEvent(event)


def paint_card(widget,painter,active,action=False):
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    hovered=widget.underMouse()
    background=COLORS['accent_soft'] if active else COLORS['surface']
    border=COLORS['accent'] if active else COLORS['border']
    if hovered and not active:
        border=COLORS['border_hover']
    # A shallow lower edge gives the reference's raised-paper feel without
    # gradients or a graphics effect on every control.
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(COLORS['shadow']))
    painter.drawRoundedRect(QRectF(widget.rect()).adjusted(1,3,-1,-1),18,18)
    painter.setPen(QPen(QColor(border),1.3 if active else 1))
    painter.setBrush(QColor(background))
    painter.drawRoundedRect(QRectF(widget.rect()).adjusted(1,1,-1,-3),18,18)
    y=(widget.height()-40)//2-1
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(COLORS['surface'] if active else COLORS['icon_well']))
    painter.drawRoundedRect(QRectF(16,y,40,40),13,13)
    (widget.active_icon if active else widget.rest_icon).paint(painter,QRect(26,y+10,20,20))
    font=QFont('Segoe UI');font.setPixelSize(14);font.setWeight(QFont.Weight.DemiBold)
    painter.setFont(font);painter.setPen(QColor(COLORS['text']))
    width=max(1,widget.width()-110)
    title=QFontMetrics(font).elidedText(widget.title,Qt.TextElideMode.ElideRight,width)
    painter.drawText(QRect(68,widget.height()//2-20,width,22),Qt.AlignmentFlag.AlignVCenter,title)
    font.setPixelSize(12);font.setWeight(QFont.Weight.Normal);painter.setFont(font)
    painter.setPen(QColor(COLORS['muted']))
    caption=QFontMetrics(font).elidedText(widget.caption,Qt.TextElideMode.ElideRight,width)
    painter.drawText(QRect(68,widget.height()//2+3,width,20),Qt.AlignmentFlag.AlignVCenter,caption)
    if action:
        widget.arrow.paint(painter,QRect(widget.width()-34,(widget.height()-18)//2,18,18))
    elif active:
        painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor(COLORS['accent']))
        painter.drawEllipse(QRectF(widget.width()-30,14,16,16))
        widget.check.paint(painter,QRect(widget.width()-28,16,12,12))
    else:
        painter.setBrush(Qt.BrushStyle.NoBrush);painter.setPen(QPen(QColor(COLORS['border_hover']),1))
        painter.drawEllipse(QRectF(widget.width()-30,14,16,16))
    if widget.hasFocus():
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(COLORS['accent']),1,Qt.PenStyle.DotLine))
        painter.drawRoundedRect(QRectF(widget.rect()).adjusted(4,4,-4,-6),15,15)


class ToolCard(QCheckBox):
    def __init__(self,title,caption,glyph):
        super().__init__(title)
        self.title,self.caption=title,caption
        self.rest_icon=icon(glyph,20,COLORS['icon'])
        self.active_icon=icon(glyph,20,COLORS['accent'])
        self.check=icon('check',12,COLORS['on_accent'])
        self.setAccessibleName(title)
        self.setAccessibleDescription(caption)
        self.setToolTip(caption+' · Select to combine with other tools')
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(86)

    def sizeHint(self): return QSize(280,86)
    def minimumSizeHint(self): return QSize(140,86)
    def hitButton(self,pos): return self.rect().contains(pos)
    def paintEvent(self,event):
        painter=QPainter(self);paint_card(self,painter,self.isChecked())


class ActionCard(QPushButton):
    def __init__(self,title,caption,glyph,callback):
        super().__init__()
        self.title,self.caption=title,caption
        self.rest_icon=icon(glyph,20)
        self.active_icon=self.rest_icon
        self.arrow=icon('arrow-right',18)
        self.setAccessibleName(title)
        self.setToolTip(caption)
        self.setMinimumHeight(72)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(callback)

    def sizeHint(self): return QSize(280,72)
    def minimumSizeHint(self): return QSize(140,72)
    def paintEvent(self,event):
        painter=QPainter(self);paint_card(self,painter,False,True)


class WorkspaceScroll(QWidget):
    """A scrolling canvas and a sibling action dock, with no overlap."""
    def __init__(self):
        super().__init__()
        self.dock=None
        self.area=QScrollArea()
        self.area.setWidgetResizable(True)
        self.root_layout=QVBoxLayout(self)
        self.root_layout.setContentsMargins(0,0,0,0)
        self.root_layout.setSpacing(0)
        self.root_layout.addWidget(self.area,1)

    def setWidget(self,widget): self.area.setWidget(widget)
    def widget(self): return self.area.widget()
    def viewport(self): return self.area.viewport()
    def verticalScrollBar(self): return self.area.verticalScrollBar()
    def horizontalScrollBar(self): return self.area.horizontalScrollBar()
    def ensureWidgetVisible(self,*args): self.area.ensureWidgetVisible(*args)

    def set_dock(self,dock):
        self.dock=dock
        dock.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Fixed)
        self.root_layout.addWidget(dock)
