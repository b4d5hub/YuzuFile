"""Focused, movable tool windows with a compact shared title bar."""
from PySide6.QtCore import Qt,QPoint,QRectF
from PySide6.QtGui import QColor,QPainter,QPainterPath,QPen,QRegion
from PySide6.QtWidgets import QDialog,QWidget,QHBoxLayout,QVBoxLayout,QLabel,QSizeGrip
from yuzufile.ui_components import IconButton
from yuzufile.ui_style import STYLE,SHELL_STYLE,light_palette


class ToolHeader(QWidget):
    def __init__(self,window,title):
        super().__init__(window);self.target=window;self.origin=None
        self.setObjectName('toolHeader');self.setFixedHeight(48)
        row=QHBoxLayout(self);row.setContentsMargins(12,0,12,0);row.setSpacing(5)
        left=QWidget();left.setFixedWidth(66);buttons=QHBoxLayout(left);buttons.setContentsMargins(0,0,0,0)
        self.close_button=IconButton('x','Close tool',window.reject);self.close_button.setObjectName('toolClose')
        buttons.addWidget(self.close_button);buttons.addStretch();row.addWidget(left)
        self.title=QLabel(title);self.title.setObjectName('toolWindowTitle')
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter);row.addWidget(self.title,1)
        right=QWidget();right.setFixedWidth(66);controls=QHBoxLayout(right);controls.setContentsMargins(0,0,0,0);controls.setSpacing(1)
        self.minimize=IconButton('minus','Minimize tool',window.showMinimized)
        self.maximize=IconButton('maximize','Maximize or restore tool',self.toggle_maximized)
        controls.addWidget(self.minimize);controls.addWidget(self.maximize);row.addWidget(right)
        self.setToolTip('Drag to move · Double-click to maximize')

    def toggle_maximized(self):
        self.target.showNormal() if self.target.isMaximized() else self.target.showMaximized()

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            self.origin=event.globalPosition().toPoint()-self.target.pos()
            handle=self.target.windowHandle()
            if handle and handle.startSystemMove():self.origin=None
            event.accept()

    def mouseMoveEvent(self,event):
        if self.origin is not None and event.buttons()&Qt.MouseButton.LeftButton:
            self.target.move(event.globalPosition().toPoint()-self.origin);event.accept()

    def mouseReleaseEvent(self,event):self.origin=None;event.accept()
    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.toggle_maximized();event.accept()

    def paintEvent(self,event):
        p=QPainter(self);p.setPen(QPen(QColor('#dddddd'),1));p.drawLine(0,self.height()-1,self.width(),self.height()-1)


class ToolDialog(QDialog):
    """Editors provide content in body_layout; header/chrome stays consistent."""
    def __init__(self,parent=None,title='PDF tool'):
        # An independent top-level window keeps a Windows taskbar entry while
        # the launcher is hidden. exec() still supplies modal dialog behavior.
        super().__init__(None,Qt.WindowType.Window|Qt.WindowType.FramelessWindowHint)
        self.owner=parent
        if parent is not None:self.setWindowIcon(parent.windowIcon())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose,False)
        self.setPalette(light_palette());self.setWindowTitle(title)
        self.setStyleSheet(STYLE+SHELL_STYLE+'''
            QDialog { background:transparent; }
            QWidget#toolBody,QWidget#toolHeader { background:transparent; }
            QFrame#toolDivider { background:#dddddd; border:0; min-height:1px; max-height:1px; }
            QLabel#toolWindowTitle { font-size:16px; font-weight:600; color:#484848; }
            QPushButton#toolClose { background:#e9e9e9; border:0; border-radius:15px; padding:0; }
            QPushButton#toolClose:hover { background:#dedede; }
            QPushButton#primary { background:#e2e2e2; color:#3f3f3f; border:1px solid #dedede; }
            QPushButton#primary:hover { background:#d8d8d8; border-color:#cccccc; }
        ''')
        root=QVBoxLayout(self);root.setContentsMargins(7,7,7,7);root.setSpacing(0)
        self.header=ToolHeader(self,title);root.addWidget(self.header)
        self.body=QWidget();self.body.setObjectName('toolBody')
        self.body_layout=QVBoxLayout(self.body);self.body_layout.setContentsMargins(16,12,16,14);self.body_layout.setSpacing(8)
        root.addWidget(self.body,1)
        self.size_grip=QSizeGrip(self);self.size_grip.setFixedSize(14,14)
        self.setMinimumSize(420,320)
        self.windowTitleChanged.connect(self.header.title.setText)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect=QRectF(self.rect()).adjusted(6,6,-6,-6)
        p.setPen(Qt.PenStyle.NoPen)
        for spread in range(6,0,-1):
            p.setBrush(QColor(0,0,0,4));p.drawRoundedRect(rect.adjusted(-spread,1-spread,spread,2+spread),24+spread,24+spread)
        p.setBrush(QColor('#f8f8f8'));p.setPen(QPen(QColor('#d9d9d9'),1));p.drawRoundedRect(rect,24,24)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.size_grip.move(self.width()-23,self.height()-23);self.size_grip.raise_()
        if self.isMaximized():self.clearMask()
        else:
            path=QPainterPath();path.addRoundedRect(QRectF(self.rect()),28,28)
            self.setMask(QRegion(path.toFillPolygon().toPolygon()))
