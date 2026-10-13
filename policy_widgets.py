"""Qt controls for account priority, quota reserves and folded quota summaries."""
import math
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QPalette, QIntValidator
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QLineEdit, QToolTip, QInputDialog, QGridLayout
from locales import tr


class ActionGrid(QWidget):
    """Wrap action buttons without imposing a wide minimum on scroll content."""
    def __init__(self):
        super().__init__()
        self.buttons, self.columns = [], 1
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(6)

    def addWidget(self, button):
        self.buttons.append(button)
        self.grid.addWidget(button, len(self.buttons) - 1, 0)
        self.columns = 1

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.buttons:
            return
        width = max(button.minimumSizeHint().width() for button in self.buttons)
        columns = max(1, min(len(self.buttons), (self.width() + 6) // (width + 6)))
        if columns == self.columns:
            return
        self.columns = columns
        while self.grid.count():
            self.grid.takeAt(0)
        for index, button in enumerate(self.buttons):
            self.grid.addWidget(button, index // columns, index % columns)


class PriorityInput(QLineEdit):
    """A compact validated editor without native spin-control padding."""
    valueChanged = Signal(int)

    def __init__(self):
        super().__init__('0')
        self._value = 0
        self.setValidator(QIntValidator(0, 999, self))
        self.setMaxLength(3)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet('padding: 1px 4px; border-radius: 4px;')
        self.editingFinished.connect(self.commit)

    def value(self):
        return self._value

    def setValue(self, value):
        value = max(0, min(999, int(value)))
        changed = self._value != value
        self._value = value
        if self.text() != str(value):
            self.setText(str(value))
        if changed:
            self.valueChanged.emit(value)

    def commit(self):
        self.setValue(int(self.text()) if self.hasAcceptableInput() else self._value)

    def stepUp(self):
        self.setValue(self._value + 1)

    def stepDown(self):
        self.setValue(self._value - 1)


class PriorityControl(QWidget):
    changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.input = PriorityInput()
        self.input.setFixedWidth(44)
        self.input.setFixedHeight(25)
        self.input.valueChanged.connect(self.changed)
        self.down = QPushButton('−')
        self.up = QPushButton('+')
        for button in (self.down, self.up):
            button.setFixedSize(20, 24)
            button.setProperty('flat', True)
            button.setAutoRepeat(True)
        self.down.clicked.connect(self.input.stepDown)
        self.up.clicked.connect(self.input.stepUp)
        layout.addWidget(self.down)
        layout.addWidget(self.input)
        layout.addWidget(self.up)
        self.setToolTip(tr('account_priority_hint'))

    def set_value(self, value):
        self.input.blockSignals(True)
        self.input.setValue(value)
        self.input.blockSignals(False)
        self.down.setEnabled(value > 0)
        self.up.setEnabled(value < 999)
        self.setToolTip(tr('account_priority_hint'))


class ReserveBar(QWidget):
    """A progress track with a reserve marker; commit only on release."""
    reserve_changed = Signal(int)

    def __init__(self, parent=None, large=False):
        super().__init__(parent)
        self._value, self._floor, self._dragging = None, 0, False
        self._color = '#66d7b0'
        self._text, self._track = '#d5e0f2', '#354157'
        self.setFixedHeight(22 if large else 16)
        self.setMinimumWidth(35)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.set_floor(0)

    def set_value(self, fraction):
        value = fraction if isinstance(fraction, (int, float)) and not isinstance(fraction, bool) and math.isfinite(fraction) else None
        value = max(0, min(1, value)) if value is not None else None
        if self._value != value:
            self._value = value
            self.update()

    def set_color(self, color):
        if color != self._color:
            self._color = color
            self.update()

    def set_theme(self, colors):
        self._text, self._track = colors['text'], colors['progress_track']
        self.update()

    def set_floor(self, value):
        if not self._dragging:
            self._floor = max(0, min(100, int(value)))
        self.setToolTip(tr('quota_reserve_hint', percent=self._floor))
        self.update()

    def floor(self):
        return self._floor

    def track(self):
        return QRectF(5, self.height() / 2 - 3, max(1, self.width() - 10), 6)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        track = self.track()
        painter.setPen(Qt.NoPen)
        track_color = QColor(self._track)
        painter.setBrush(track_color)
        painter.drawRoundedRect(track, 3, 3)
        if self._value is not None and self._value > 0:
            filled = QRectF(track)
            filled.setWidth(track.width() * self._value)
            painter.setBrush(QColor(self._color))
            painter.drawRoundedRect(filled, 3, 3)
        x = track.left() + track.width() * self._floor / 100
        color = QColor(self._text)
        painter.setPen(QPen(color, 1.5))
        painter.drawLine(QPointF(x, track.top() - 3), QPointF(x, track.bottom() + 3))
        painter.setBrush(color)
        radius = 4 if self._dragging else 2.5
        painter.drawEllipse(QPointF(x, track.center().y()), radius, radius)

    def _move(self, position):
        track = self.track()
        self._floor = max(0, min(100, round((position.x() - track.left()) * 100 / track.width())))
        QToolTip.showText(self.mapToGlobal(QPointF(position.x(), -12).toPoint()), f'{self._floor}%', self)
        self.update()

    def mousePressEvent(self, event):
        x = self.track().left() + self.track().width() * self._floor / 100
        if event.button() == Qt.LeftButton and abs(event.position().x() - x) <= 10:
            self._dragging = True
            self.setFocus()
            self._move(event.position())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._move(event.position())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging and event.button() == Qt.LeftButton:
            self._move(event.position())
            self._dragging = False
            QToolTip.hideText()
            self.set_floor(self._floor)
            self.reserve_changed.emit(self._floor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        self._dragging = False
        QToolTip.hideText()
        value, accepted = QInputDialog.getInt(self, tr('quota_reserve'), tr('quota_reserve_amount'), self._floor, 0, 100)
        if accepted:
            self.set_floor(value)
            self.reserve_changed.emit(value)

    def keyPressEvent(self, event):
        keys = {Qt.Key_Left: -1, Qt.Key_Right: 1, Qt.Key_Down: -10, Qt.Key_Up: 10}
        if event.key() in keys or event.key() in (Qt.Key_Home, Qt.Key_End):
            value = 0 if event.key() == Qt.Key_Home else 100 if event.key() == Qt.Key_End else self._floor + keys[event.key()]
            self.set_floor(value)
            self.reserve_changed.emit(self._floor)
            event.accept()
        else:
            super().keyPressEvent(event)


class QuotaCircle(QWidget):
    def __init__(self, label, parent=None):
        super().__init__(parent)
        self.label, self.fraction = label, None
        self._text, self._track = '#d5e0f2', '#354157'
        self.setFixedSize(34, 34)

    def set_value(self, fraction):
        value = fraction if isinstance(fraction, (int, float)) and not isinstance(fraction, bool) and math.isfinite(fraction) else None
        value = max(0, min(1, value)) if value is not None else None
        if self.fraction != value:
            self.fraction = value
            self.update()
        self.setToolTip(self.label + ' · ' + (tr('quota_no_data') if value is None else f'{value * 100:.1f}%'))

    def set_theme(self, colors):
        self._text, self._track = colors['text'], colors['progress_track']
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        bounds = QRectF(3, 3, 28, 28)
        value = self.fraction
        color = '#8390a3' if value is None else '#36bb87' if value >= .5 else '#edaa43' if value > .1 else '#f06472'
        track = QColor(self._track)
        painter.setPen(QPen(track, 3)); painter.drawEllipse(bounds)
        painter.setPen(QPen(QColor(color), 3, Qt.SolidLine, Qt.RoundCap))
        if value is not None and value > 0:
            painter.drawArc(bounds, 90 * 16, -round(value * 360 * 16))
        elif value is None or value == 0:
            painter.drawEllipse(bounds)
        painter.setPen(QColor(self._text))
        painter.setFont(QFont('Segoe UI', 7))
        painter.drawText(self.rect(), Qt.AlignCenter, self.label)


class FoldHeader(QWidget):
    toggled = Signal(bool)

    def __init__(self, title, labels, collapsed=False, parent=None):
        super().__init__(parent)
        self.title, self.collapsed = title, collapsed
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.button = QPushButton()
        self.button.setProperty('flat', True)
        self.button.clicked.connect(self.toggle)
        layout.addWidget(self.button, 1)
        self.circles = [QuotaCircle(label) for label in labels]
        for circle in self.circles:
            layout.addWidget(circle)
        self.set_title(title)

    def set_title(self, title):
        self.title = title
        self.button.setText(('▸ ' if self.collapsed else '▾ ') + title)

    def set_values(self, values):
        for circle, value in zip(self.circles, values):
            circle.set_value(value)

    def set_theme(self, colors):
        for circle in self.circles:
            circle.set_theme(colors)

    def toggle(self):
        self.collapsed = not self.collapsed
        self.set_title(self.title)
        self.toggled.emit(self.collapsed)
