"""Page cards with explicit move targets and a visible drag lifecycle."""
from PySide6.QtCore import Qt,QSize,Signal,QPoint,QRect,QRectF
from PySide6.QtGui import QDrag,QPixmap,QPainter,QColor,QPen,QFont
from PySide6.QtWidgets import QListWidget,QAbstractItemView,QStyledItemDelegate,QStyle
from yuzufile.ui_style import COLORS
from yuzufile.icons import icon


ASPECT_ROLE=Qt.ItemDataRole.UserRole+1
READY_ROLE=Qt.ItemDataRole.UserRole+2


class PageDelegate(QStyledItemDelegate):
    """Paint the page and its short caption explicitly; Qt's icon slot is unused."""
    def image_rect(self,rect,index):
        area=QRectF(rect).adjusted(8,8,-8,-self.parent().caption_height()-8)
        ratio=index.data(ASPECT_ROLE) or 4/3
        width=min(area.width(),area.height()/ratio)
        height=width*ratio
        return QRectF(area.center().x()-width/2,area.center().y()-height/2,width,height)

    def rotate_rect(self,rect,index):
        page=self.image_rect(rect,index)
        return QRectF(page.right()-36,page.top()+10,26,26)

    def paint(self,painter,option,index):
        grid=self.parent();painter.save()
        if grid.dragging and index.row() in grid.dragged_rows:painter.setOpacity(.32)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        card=QRectF(option.rect).adjusted(1,1,-1,-1)
        selected=bool(option.state & QStyle.StateFlag.State_Selected)
        border='accent' if selected else 'border_hover' if option.state & QStyle.StateFlag.State_MouseOver else 'border'
        painter.setPen(QPen(QColor(COLORS[border]),1.5 if selected else 1))
        painter.setBrush(QColor(COLORS['surface']))
        painter.drawRoundedRect(card,12,12)
        page_rect=self.image_rect(option.rect,index)
        painter.fillRect(page_rect,QColor('white'))
        preview=index.data(Qt.ItemDataRole.DecorationRole)
        if preview is not None:
            if index.data(READY_ROLE):
                size=page_rect.size()*grid.devicePixelRatioF()
                pix=preview.pixmap(size.toSize())
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                painter.drawPixmap(page_rect,pix,QRectF(pix.rect()))
            else:
                pix=preview.pixmap(40,40)
                painter.drawPixmap(round(page_rect.center().x()-20),round(page_rect.center().y()-20),pix)
        painter.setPen(QPen(QColor(COLORS['border']),1));painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(page_rect)
        # Order and rotation live on the page, leaving its caption compact.
        badge_size=36 if index.row()>=99 else 30
        badge=QRectF(page_rect.left()+10,page_rect.top()+10,badge_size,badge_size)
        painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor(COLORS['brand']))
        painter.drawEllipse(badge);painter.setPen(QColor('white'))
        number_font=QFont(option.font);number_font.setBold(True);painter.setFont(number_font)
        painter.drawText(badge,Qt.AlignmentFlag.AlignCenter,str(index.row()+1))
        rotate=self.rotate_rect(option.rect,index)
        painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor(70,70,70,220));painter.drawEllipse(rotate)
        icon('rotate-cw',16,'#ffffff').paint(painter,rotate.adjusted(5,5,-5,-5).toRect())
        metrics=option.fontMetrics;lines=(index.data(Qt.ItemDataRole.DisplayRole) or '').split('\n')
        caption=QRectF(card.left()+8,card.bottom()-grid.caption_height(),card.width()-16,metrics.height()+2)
        moved=index.row() in grid.landed
        painter.setFont(option.font);painter.setPen(QColor(COLORS['accent' if moved else 'text']))
        text=('Moved · ' if moved else '')+lines[0]
        painter.drawText(caption,Qt.AlignmentFlag.AlignCenter,metrics.elidedText(text,Qt.TextElideMode.ElideRight,round(caption.width())))
        if len(lines)>1:
            caption.translate(0,metrics.height());painter.setPen(QColor(COLORS['muted']))
            painter.drawText(caption,Qt.AlignmentFlag.AlignCenter,metrics.elidedText(lines[1],Qt.TextElideMode.ElideMiddle,round(caption.width())))
        if option.state & QStyle.StateFlag.State_HasFocus:
            painter.setPen(QPen(QColor(COLORS['accent']),1,Qt.PenStyle.DotLine))
            painter.drawRoundedRect(card.adjusted(3,3,-3,-3),10,10)
        painter.restore()
        if index.row() in grid.landed:
            painter.save();painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(QColor(COLORS['accent']),3));painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(option.rect.adjusted(2,2,-2,-2)),12,12)
            painter.restore()


class PageGrid(QListWidget):
    need_thumbnails=Signal()
    def __init__(self,owner):
        super().__init__();self.owner=owner;self.dragging=False;self.dragged_rows=[];self.target=None;self.landed=set()
        self._card_action=False;self.setMouseTracking(True)
        self.setAccessibleName('Pages in output order');self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setResizeMode(QListWidget.ResizeMode.Adjust);self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove);self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDropIndicatorShown(False);self.setAutoScroll(True);self.setAutoScrollMargin(40)
        self.setSpacing(6);self.setWordWrap(False);self.setItemDelegate(PageDelegate(self))
        self.setUniformItemSizes(False)
        self.verticalScrollBar().valueChanged.connect(self.need_thumbnails)
        self.verticalScrollBar().valueChanged.connect(self.viewport().update)
        self.set_card_size(300)

    def set_card_size(self,width):
        self.page_width=width
        self.setIconSize(QSize(width,round(width*2)))
        self.setGridSize(QSize())

    def caption_height(self):return self.fontMetrics().height()*2+8

    def card_size(self,ratio):
        return QSize(self.page_width+16,round(self.page_width*max(.25,min(2,ratio)))+16+self.caption_height())

    def resizeEvent(self,event):super().resizeEvent(event);self.need_thumbnails.emit()

    def mousePressEvent(self,event):
        index=self.indexAt(event.position().toPoint())
        if event.button()==Qt.MouseButton.LeftButton and index.isValid():
            rect=self.visualItemRect(self.item(index.row()))
            if self.itemDelegate().rotate_rect(rect,index).contains(event.position()):
                self._card_action=True;self.owner.rotate_page(index.row());event.accept();return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self,event):
        if self._card_action:self._card_action=False;event.accept();return
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self,event):
        if self._card_action:event.accept();return
        index=self.indexAt(event.position().toPoint());over=False
        if index.isValid():
            over=self.itemDelegate().rotate_rect(self.visualItemRect(self.item(index.row())),index).contains(event.position())
        self.viewport().setCursor(Qt.CursorShape.PointingHandCursor if over else Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)

    def insertion_target(self,point):
        if point.x()<0 or point.y()<0:return self.count()
        index=self.indexAt(point).row()
        if index>=0:
            return index+(point.x()>self.visualItemRect(self.item(index)).center().x())
        if not self.count():return 0
        # Whitespace belongs to the nearest row, then the nearest card edge.
        best=min(range(self.count()),key=lambda row:abs(self.visualItemRect(self.item(row)).center().y()-point.y())*10000+abs(self.visualItemRect(self.item(row)).center().x()-point.x()))
        rect=self.visualItemRect(self.item(best))
        if point.y()>rect.bottom():return self.count()
        return best+(point.x()>rect.center().x())

    def dragEnterEvent(self,event):
        from yuzufile.desktop_drag import pdf_paths,accept_copy
        if event.source() is self:event.acceptProposedAction()
        elif pdf_paths(event.mimeData()):accept_copy(event)

    def startDrag(self,supported_actions):
        if not self.selectedIndexes():return
        self.dragged_rows=self.owner.selected();self.dragging=True;self.landed.clear();self.viewport().update()
        count=len(self.dragged_rows);title=f"Moving {count} {'page' if count==1 else 'pages'}"
        self.owner.message.setText(title+' — drop at the orange marker')
        drag=QDrag(self);drag.setMimeData(self.model().mimeData(self.selectedIndexes()))
        ratio=self.selectedItems()[0].data(ASPECT_ROLE) or 4/3
        image_height=round(170*max(.25,min(2,ratio)));height=image_height+48
        dpr=self.devicePixelRatioF();ghost=QPixmap(round(194*dpr),round(height*dpr));ghost.setDevicePixelRatio(dpr);ghost.fill(Qt.GlobalColor.transparent)
        painter=QPainter(ghost);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor(0,0,0,35));painter.drawRoundedRect(QRectF(6,7,184,height-10),14,14)
        painter.setBrush(QColor('white'));painter.setPen(QPen(QColor(COLORS['accent']),2));painter.drawRoundedRect(QRectF(2,2,184,height-10),14,14)
        pix=self.selectedItems()[0].icon().pixmap(QSize(round(170*dpr),round(image_height*dpr)))
        rect=QRectF(10,10,170,image_height)
        size=pix.size().toSizeF();size.scale(rect.size(),Qt.AspectRatioMode.KeepAspectRatio)
        target=QRectF(rect.center().x()-size.width()/2,rect.center().y()-size.height()/2,size.width(),size.height())
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform);painter.drawPixmap(target,pix,QRectF(pix.rect()))
        painter.setPen(QColor(COLORS['text']));painter.drawText(QRect(8,image_height+14,172,26),Qt.AlignmentFlag.AlignCenter,title);painter.end()
        drag.setPixmap(ghost);drag.setHotSpot(QPoint(80,70))
        try:
            result=drag.exec(Qt.DropAction.MoveAction)
            if result==Qt.DropAction.IgnoreAction:self.owner.message.setText('Move cancelled')
        finally:self.dragging=False;self.dragged_rows=[];self.target=None;self.viewport().update()

    def dragMoveEvent(self,event):
        if event.source() is self:
            super().dragMoveEvent(event)
            self.target=self.insertion_target(event.position().toPoint());self.viewport().update();event.acceptProposedAction()
        elif event.mimeData().hasUrls():
            from yuzufile.desktop_drag import pdf_paths,accept_copy
            if pdf_paths(event.mimeData()):accept_copy(event)
            else:event.ignore()

    def dragLeaveEvent(self,event):self.target=None;self.viewport().update();super().dragLeaveEvent(event)

    def dropEvent(self,event):
        if event.mimeData().hasUrls():
            from yuzufile.desktop_drag import pdf_paths,accept_copy
            paths=pdf_paths(event.mimeData())
            if paths and accept_copy(event):self.owner.add_files(paths)
            else:event.ignore()
        elif event.source() is self:
            target=self.insertion_target(event.position().toPoint())
            self.owner.move_to(target,self.dragged_rows or None)
            self.target=None;self.dragging=False;self.viewport().update()
            event.setDropAction(Qt.DropAction.MoveAction);event.accept()

    def paintEvent(self,event):
        super().paintEvent(event)
        if self.target is None or not self.count():return
        last=self.target==self.count();row=self.count()-1 if last else self.target
        rect=self.visualItemRect(self.item(row));x=rect.right()+3 if last else rect.left()-3
        x=max(4,min(self.viewport().width()-5,x));top=max(6,rect.top());bottom=min(self.viewport().height()-6,rect.bottom())
        painter=QPainter(self.viewport());painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(COLORS['accent']),4));painter.drawLine(x,top,x,bottom)
        painter.setBrush(QColor(COLORS['accent']));painter.drawEllipse(QPoint(x,top),4,4);painter.drawEllipse(QPoint(x,bottom),4,4)
        label='Drop at end' if last else f'Drop before page {self.target+1}'
        width=self.fontMetrics().horizontalAdvance(label)+20
        box=QRect(max(4,min(x,self.viewport().width()-width-4)),max(4,top-30),width,26)
        painter.setPen(Qt.PenStyle.NoPen);painter.drawRoundedRect(box,7,7)
        painter.setPen(QColor('white'));painter.drawText(box,Qt.AlignmentFlag.AlignCenter,label)
