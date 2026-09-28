"""Resolution-independent, local Qt icons and a shared control treatment."""
from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QIconEngine, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QDialogButtonBox


CONTROL_STYLE = """
QPushButton {
    color: #24476a; border: 1px solid #91b9dd; border-radius: 8px;
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #ffffff, stop:1 #dbeeff);
    padding: 5px 9px; min-height: 20px;
}
QPushButton:hover { background: #edf7ff; border-color: #4b8ec6; }
QPushButton:pressed { background: #beddf5; border-color: #336f9e; }
QPushButton:focus { border: 2px solid #3c7eaf; padding: 4px 8px; }
QPushButton:disabled { color: #718496; background: #e8eef3; border-color: #c5d2dd; }
QMenu { color: #24476a; background: #f7fbff; border: 1px solid #91b9dd; padding: 5px; }
QMenu::item { padding: 7px 24px 7px 28px; border-radius: 6px; }
QMenu::item:selected { color: #173a5b; background: #d6ebfc; }
QMenu::item:disabled { color: #718496; }
QMenu::separator { height: 1px; background: #cfdfec; margin: 4px 8px; }
"""


class BlueIconEngine(QIconEngine):
    def __init__(self, name):
        super().__init__()
        self.name = name

    def clone(self):
        return BlueIconEngine(self.name)

    def pixmap(self, size, mode, state):
        pixmap = QPixmap(size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        self.paint(painter, pixmap.rect(), mode, state)
        painter.end()
        return pixmap

    def paint(self, painter, rect, mode, state):
        painter.save()
        side = min(rect.width(), rect.height())
        painter.translate(rect.x() + (rect.width() - side) / 2,
                          rect.y() + (rect.height() - side) / 2)
        painter.scale(side / 24, side / 24)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        disabled = mode == QIcon.Mode.Disabled
        ink = QColor('#8295a6' if disabled else '#285d89')
        gradient = QLinearGradient(3, 22, 18, 2)
        gradient.setColorAt(0, QColor('#dce5ed' if disabled else '#a8d4f5'))
        gradient.setColorAt(1, QColor('#ffffff'))
        # Pale outer rim reads on dark panels; blue edge reads on light ones.
        painter.setPen(QPen(QColor('#eaf6ff'), 2))
        painter.setBrush(gradient)
        painter.drawRoundedRect(QRectF(2, 2, 20, 20), 6, 6)
        painter.setPen(QPen(QColor('#a8bac9' if disabled else '#6eacd9'), .9))
        painter.drawRoundedRect(QRectF(2, 2, 20, 20), 6, 6)
        painter.setPen(QPen(QColor('#ffffff'), 1.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(7, 4), QPointF(16, 4))
        painter.setPen(QPen(ink, 1.7, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)

        def line(x1, y1, x2, y2):
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        def path(points):
            shape = QPainterPath(QPointF(*points[0]))
            for point in points[1:]:
                shape.lineTo(*point)
            painter.drawPath(shape)

        name = self.name
        if name in ('add', 'notes', 'save'):
            painter.drawRoundedRect(QRectF(7, 6, 10, 12), 2, 2)
            if name == 'add':
                line(9.5, 12, 14.5, 12)
                line(12, 9.5, 12, 14.5)
            elif name == 'save':
                path([(9, 12), (11, 14), (15, 10)])
            else:
                for y in (9, 12, 15):
                    line(10, y, 14, y)
        elif name == 'sleep':
            moon = QPainterPath(QPointF(14, 6))
            moon.cubicTo(3, 5, 4, 20, 15, 18)
            moon.quadTo(18, 17, 18, 14)
            moon.cubicTo(11, 17, 9, 9, 14, 6)
            painter.drawPath(moon)
        elif name == 'settings':
            for x, y in ((8, 9), (12, 15), (16, 10)):
                line(x, 6, x, 18)
                painter.setBrush(QColor('#f5fbff'))
                painter.drawEllipse(QPointF(x, y), 1.7, 1.7)
        elif name in ('show', 'hide'):
            eye = QPainterPath(QPointF(5, 12))
            eye.quadTo(12, 4, 19, 12)
            eye.quadTo(12, 20, 5, 12)
            painter.drawPath(eye)
            painter.drawEllipse(QPointF(12, 12), 2, 2)
            if name == 'hide':
                line(6, 18, 18, 6)
        elif name == 'quit':
            painter.drawArc(QRectF(6, 6, 12, 12), 135 * 16, 270 * 16)
            line(12, 5, 12, 11)
        elif name in ('close', 'cancel'):
            line(8, 8, 16, 16)
            line(16, 8, 8, 16)
        elif name == 'complete':
            path([(6, 12), (10, 16), (18, 8)])
        elif name == 'delete':
            line(6, 8, 18, 8)
            line(10, 5.5, 14, 5.5)
            path([(8, 10), (9, 18), (15, 18), (16, 10)])
            line(12, 10, 12, 15)
        elif name == 'reminder':
            bell = QPainterPath(QPointF(6, 16))
            bell.lineTo(8, 13)
            bell.lineTo(8, 10)
            bell.cubicTo(8, 5, 16, 5, 16, 10)
            bell.lineTo(16, 13)
            bell.lineTo(18, 16)
            bell.closeSubpath()
            painter.drawPath(bell)
            line(11, 19, 13, 19)
        elif name in ('sit', 'stand'):
            if name == 'sit':
                path([(7, 6), (7, 13), (17, 13), (17, 18)])
                line(7, 13, 7, 18)
            else:
                line(12, 18, 12, 6)
                path([(7, 11), (12, 6), (17, 11)])
        else:  # A simple friendly pet face remains legible at tray sizes.
            face = QPainterPath(QPointF(6, 16))
            face.lineTo(6, 7)
            face.lineTo(10, 10)
            face.quadTo(12, 9, 14, 10)
            face.lineTo(18, 7)
            face.lineTo(18, 16)
            face.quadTo(12, 21, 6, 16)
            painter.drawPath(face)
            line(9, 13, 9, 14)
            line(15, 13, 15, 14)
            smile = QPainterPath(QPointF(10, 16))
            smile.quadTo(12, 18, 14, 16)
            painter.drawPath(smile)
        painter.restore()


def icon(name):
    return QIcon(BlueIconEngine(name))


def style_button(button, name):
    button.setIcon(icon(name))
    button.setIconSize(QSize(20, 20))
    button.setStyleSheet(CONTROL_STYLE)


def style_button_box(box):
    for standard, name in ((QDialogButtonBox.StandardButton.Save, 'save'),
                           (QDialogButtonBox.StandardButton.Cancel, 'cancel'),
                           (QDialogButtonBox.StandardButton.Close, 'close')):
        button = box.button(standard)
        if button is not None:
            style_button(button, name)


def menu_action(menu, name, label, callback):
    action = menu.addAction(label, callback)
    action.setIcon(icon(name))
    action.setIconVisibleInMenu(True)
    return action
