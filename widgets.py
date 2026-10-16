"""Custom PySide6 widgets for Gemini Accounts."""

import math
import colorsys
import time
from datetime import datetime, timezone
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QLabel,
                                QPushButton, QProgressBar, QFrame, QSizePolicy,
                                QGraphicsDropShadowEffect, QComboBox)
from PySide6.QtCore import Qt, Signal, QTimer, QSize, QRectF, QPointF
from PySide6.QtGui import (QPainter, QColor, QPen, QBrush, QLinearGradient,
                            QFont, QFontMetrics, QPainterPath, QPixmap, QImage, QIcon)
from PySide6.QtGui import QPalette
from locales import tr
from policy_widgets import ReserveBar, PriorityControl


def ui_icon(name, color, size=18):
    """Draw toolbar symbols without depending on emoji fonts or OS themes."""
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor(color), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(Qt.NoBrush)
    if name == 'sun':
        painter.drawEllipse(QRectF(5, 5, 8, 8))
        for index in range(8):
            angle = index * math.pi / 4
            painter.drawLine(QPointF(9 + 6 * math.cos(angle), 9 + 6 * math.sin(angle)),
                             QPointF(9 + 8 * math.cos(angle), 9 + 8 * math.sin(angle)))
    elif name == 'moon':
        path = QPainterPath()
        path.moveTo(11, 2)
        path.cubicTo(0, 0, 0, 17, 11, 16)
        path.cubicTo(5, 13, 5, 5, 11, 2)
        painter.drawPath(path)
    elif name == 'settings':
        for y, x in ((4, 6), (9, 12), (14, 8)):
            painter.drawLine(QPointF(2, y), QPointF(16, y))
            painter.drawEllipse(QPointF(x, y), 2, 2)
    else:
        painter.drawRoundedRect(QRectF(2, 3, 14, 12), 2, 2)
        painter.drawLine(QPointF(7, 3), QPointF(7, 15))
    painter.end()
    return QIcon(pixmap)


class ThemedComboBox(QComboBox):
    """Keep the dropdown arrow visible with styled backgrounds in either theme."""

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = self.palette().color(QPalette.Text)
        painter.setPen(QPen(color, 1.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        x, y = self.width() - 12, self.height() / 2
        painter.drawLine(QPointF(x - 3, y - 1), QPointF(x, y + 2))
        painter.drawLine(QPointF(x, y + 2), QPointF(x + 3, y - 1))
        painter.end()


class QuotaBar(QProgressBar):
    """A progress bar that changes color based on the remaining percentage."""

    def __init__(self, parent=None, large=False):
        super().__init__(parent)
        self.setTextVisible(False)
        self.setRange(0, 1000)
        self._color = '#66d7b0'
        if large:
            self.setProperty('size', 'large')

    def set_value(self, fraction):
        """Set progress as a 0..1 fraction.  *None* resets to empty."""
        if fraction is None:
            self.setValue(0)
        else:
            self.setValue(max(0, min(1000, round(fraction * 1000))))

    def set_color(self, color):
        self._color = color
        self.setStyleSheet(
            f'QProgressBar::chunk {{ background-color: {color}; border-radius: '
            f'{"5" if self.property("size") == "large" else "3"}px; }}')


class ForecastWidget(QWidget):
    """Canvas-like widget that draws quota forecast bars with time markers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(16)
        self._forecast = []
        self._remaining = None
        self._quota_color = '#66d7b0'
        self._theme = {}
        self._weekly = False
        self._hover_index = -1
        self.setMouseTracking(True)

    def set_data(self, forecast, remaining, quota_color, theme, weekly=False):
        self._forecast = forecast
        self._remaining = remaining
        self._quota_color = quota_color
        self._theme = theme
        self._weekly = weekly
        self.update()

    def paintEvent(self, event):
        if not self._forecast or not self._theme:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        h = self.height()
        margin = 3
        track = max(1, w - 2 * margin)
        top = 2
        t = self._theme
        bg_color = QColor(t.get('forecast_bg', '#293344'))
        text_color = QColor(t.get('forecast_text', '#8995a8'))
        font = QFont('Segoe UI', 8)
        fm = QFontMetrics(font)
        painter.setFont(font)

        # Track background
        painter.fillRect(QRectF(margin, top, w - 2 * margin, h - 2 * top), bg_color)

        # Remaining fill
        remaining = min(1, max(0, self._remaining or 0))
        if remaining > 0:
            painter.fillRect(QRectF(margin, top, track * remaining, h - 2 * top),
                           QColor(self._quota_color))

        now = datetime.now(timezone.utc)
        labels = []
        for point in self._forecast:
            try:
                reset = datetime.fromisoformat(point['reset'])
                seconds = max(0, (reset - now).total_seconds())
            except (ValueError, KeyError):
                continue
            if self._weekly:
                text = '0' + tr('unit_day') if seconds <= 0 else '< 1' + tr('unit_day') if seconds < 86400 else f'{int(seconds // 86400)}' + tr('unit_day')
            else:
                minutes = math.ceil(seconds / 60)
                hrs, mins = divmod(minutes, 60)
                text = f'{hrs}{tr("unit_hour")} {mins:02}{tr("unit_minute")}'
            x = margin + track * min(1, max(0, point.get('remaining', 0)))
            text_w = fm.horizontalAdvance(text)
            left = x - text_w - 3
            if left < margin:
                left = x + 3
            left = max(margin, min(left, w - margin - text_w))
            labels.append((x, left, text, text_w))

        # Draw time labels
        label_end = -1
        for x, left, text, text_w in labels:
            if left < label_end + 3:
                continue
            painter.fillRect(QRectF(left - 1, 1, text_w + 2, fm.height()), bg_color)
            painter.setPen(text_color)
            painter.drawText(QPointF(left, 1 + fm.ascent()), text)
            label_end = left + text_w

        # Draw markers
        marker_pen = QPen(text_color, 2)
        painter.setPen(marker_pen)
        for x, left, text, text_w in labels:
            painter.drawLine(QPointF(x, top), QPointF(x, h - top))

        # Hover highlight
        if 0 <= self._hover_index < len(labels):
            x, left, text, text_w = labels[self._hover_index]
            painter.fillRect(QRectF(left - 1, 1, text_w + 2, fm.height()), bg_color)
            painter.setPen(QColor(self._theme.get('text', '#edf2fa')))
            painter.drawText(QPointF(left, 1 + fm.ascent()), text)

        painter.end()

    def mouseMoveEvent(self, event):
        if not self._forecast:
            return
        w = self.width()
        margin = 3
        track = max(1, w - 2 * margin)
        now = datetime.now(timezone.utc)
        best = -1
        best_dist = 999
        for i, point in enumerate(self._forecast):
            try:
                x = margin + track * min(1, max(0, point.get('remaining', 0)))
                dist = abs(x - event.position().x())
                if dist < 8 and dist < best_dist:
                    best = i
                    best_dist = dist
            except (KeyError, TypeError):
                pass
        if best != self._hover_index:
            self._hover_index = best
            self.update()

    def leaveEvent(self, event):
        if self._hover_index != -1:
            self._hover_index = -1
            self.update()


class SegmentedControl(QWidget):
    """A horizontal segmented button control."""

    value_changed = Signal(str)

    def __init__(self, values, parent=None, columns=0):
        super().__init__(parent)
        layout = QGridLayout(self) if columns else QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._buttons = {}
        self._current = values[0] if values else ''
        for index, value in enumerate(values):
            btn = QPushButton(value)
            btn.setProperty('segment', True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked, v=value: self._select(v))
            if columns:
                layout.addWidget(btn, index // columns, index % columns)
            else:
                layout.addWidget(btn)
            self._buttons[value] = btn
        self._update_styles()

    def _select(self, value):
        if value != self._current:
            self._current = value
            self._update_styles()
            self.value_changed.emit(value)

    def _update_styles(self):
        for value, btn in self._buttons.items():
            btn.setProperty('active', value == self._current)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def get(self):
        return self._current

    def set(self, value):
        if value in self._buttons:
            self._current = value
            self._update_styles()


class AccountCard(QFrame):
    """A clickable card representing one account in the sidebar."""

    clicked = Signal(str)  # emits account name
    remove_requested = Signal(str)

    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.account_name = name
        self._selected = False
        self._active_families = ()
        self._rainbow_phase = 0
        self._is_active = False
        self.setProperty('class', 'card')
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(32)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)

        heading = QHBoxLayout()
        heading.setContentsMargins(0, 0, 0, 0)
        heading.setSpacing(2)
        self.heading_label = QLabel()
        self.heading_label.setTextFormat(Qt.PlainText)
        self.heading_label.setFont(QFont('Segoe UI', 12, QFont.Bold))
        self.heading_label.setWordWrap(True)
        heading.addWidget(self.heading_label, 1)
        self.priority_control = PriorityControl()
        heading.addWidget(self.priority_control)
        self.remove_button = QPushButton('×')
        self.remove_button.setFixedSize(22, 22)
        self.remove_button.setProperty('class', 'danger')
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self.account_name))
        heading.addWidget(self.remove_button)
        layout.addLayout(heading)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setFont(QFont('Segoe UI', 10))
        self.status_label.setProperty('class', 'warning')
        self.status_label.hide()
        layout.addWidget(self.status_label)
        self.uptime_label = QLabel()
        self.uptime_label.setWordWrap(True)
        self.uptime_label.setFont(QFont('Segoe UI', 9))
        self.uptime_label.setProperty('class', 'muted')
        self.uptime_label.hide()
        layout.addWidget(self.uptime_label)

        self.quota_container = QWidget()
        self.quota_layout = QVBoxLayout(self.quota_container)
        self.quota_layout.setContentsMargins(0, 0, 0, 0)
        self.quota_layout.setSpacing(2)
        layout.addWidget(self.quota_container)

        self.verification_frame = QWidget()
        self.verification_frame.setVisible(False)
        self.verification_layout = QHBoxLayout(self.verification_frame)
        self.verification_layout.setContentsMargins(0, 2, 0, 2)
        self.verification_layout.setSpacing(4)
        layout.addWidget(self.verification_frame)

        self.quota_rows = {}
        self.countdown_labels = {}

    def set_selected(self, selected, theme_colors):
        self._selected = selected
        border = theme_colors.get('border_selected') if selected else theme_colors.get('border')
        bg = theme_colors.get('card_selected') if selected else theme_colors.get('card_alt', theme_colors.get('card'))
        self.setStyleSheet(
            f'AccountCard {{ background-color: {bg}; border: 1px solid {border}; border-radius: 10px; }}')

    def set_heading(self, text):
        self.heading_label.setText(text)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.account_name)
        super().mousePressEvent(event)


class RainbowBorderWidget(QWidget):
    """Overlay widget that draws animated rainbow borders on active account cards."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._phase = 0
        self._active = False

    def set_active(self, active, phase=0):
        self._active = active
        self._phase = phase
        self.update()

    def paintEvent(self, event):
        if not self._active:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        radius = 10
        pen_width = 2.5
        inset = pen_width / 2 + 0.5

        # Build path around the rounded rect
        path = QPainterPath()
        path.addRoundedRect(QRectF(inset, inset, w - 2 * inset, h - 2 * inset), radius, radius)

        # Sample colors along the path
        length = path.length()
        if length < 1:
            painter.end()
            return

        segments = max(4, int(length / 4))
        prev = path.pointAtPercent(0)
        for i in range(1, segments + 1):
            pct = i / segments
            pt = path.pointAtPercent(pct)
            hue = (self._phase + pct) % 1.0
            r, g, b = colorsys.hsv_to_rgb(hue, 0.72, 1.0)
            color = QColor(round(r * 255), round(g * 255), round(b * 255))
            pen = QPen(color, pen_width, Qt.SolidLine, Qt.RoundCap)
            painter.setPen(pen)
            painter.drawLine(QPointF(prev.x(), prev.y()), QPointF(pt.x(), pt.y()))
            prev = pt

        painter.end()


class ProviderBadge(QWidget):
    """Draws small provider icon badges on account cards."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._families = ()
        self._theme = {}
        self.setFixedSize(60, 20)

    def set_families(self, families, theme):
        self._families = families
        self._theme = theme
        self.update()

    def paintEvent(self, event):
        if not self._families:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        h = self.height()
        for index, family in enumerate(reversed(self._families)):
            x = w - 12 - 22 * index
            y = h / 2
            bg_color = QColor(self._theme.get(f'badge_{family}', '#334d77'))
            painter.setBrush(QBrush(bg_color))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(QRectF(x - 10, y - 9, 20, 18), 4, 4)
            if family == 'gemini':
                self._draw_gemini_icon(painter, x, y, 6)
            else:
                self._draw_claude_icon(painter, x, y, 6)
        painter.end()

    @staticmethod
    def _draw_gemini_icon(painter, cx, cy, size):
        """Draw a diamond-shaped Gemini icon."""
        points = [QPointF(cx, cy - size), QPointF(cx + size * 0.65, cy),
                  QPointF(cx, cy + size), QPointF(cx - size * 0.65, cy)]
        grad = QLinearGradient(cx - size, cy - size, cx + size, cy + size)
        grad.setColorAt(0, QColor(75, 157, 255))
        grad.setColorAt(1, QColor(215, 103, 212))
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.NoPen)
        path = QPainterPath()
        path.moveTo(points[0])
        for p in points[1:]:
            path.lineTo(p)
        path.closeSubpath()
        painter.drawPath(path)

    @staticmethod
    def _draw_claude_icon(painter, cx, cy, size):
        """Draw a sunburst Claude icon."""
        color = QColor('#d98b6b')
        painter.setPen(QPen(color, 1.5))
        painter.setBrush(QBrush(color))
        for ray in range(8):
            angle = ray * math.pi / 4
            x2 = cx + size * 0.9 * math.cos(angle)
            y2 = cy + size * 0.9 * math.sin(angle)
            painter.drawLine(QPointF(cx, cy), QPointF(x2, y2))
        painter.drawEllipse(QPointF(cx, cy), size * 0.35, size * 0.35)


class QuotaRowWidget(QWidget):
    """A row displaying one quota bucket with icon, label, bar, and countdown."""

    def __init__(self, kind, window, parent=None):
        super().__init__(parent)
        self._kind = kind
        self._window = window
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 1, 3, 1)
        layout.setSpacing(4)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(14, 14)
        if window == '5h':
            icon = QPixmap(14, 14)
            icon.fill(Qt.transparent)
            painter = QPainter(icon)
            painter.setRenderHint(QPainter.Antialiasing)
            draw = ProviderBadge._draw_gemini_icon if kind == 'gemini' else ProviderBadge._draw_claude_icon
            draw(painter, 7, 7, 6)
            painter.end()
            self.icon_label.setPixmap(icon)
        layout.addWidget(self.icon_label)

        self.text_label = QLabel()
        self.text_label.setFont(QFont('Segoe UI', 11))
        self.text_label.setFixedWidth(76)
        layout.addWidget(self.text_label)

        self.bar = ReserveBar()
        layout.addWidget(self.bar, 1)

        self.countdown = QLabel()
        self.countdown.setFont(QFont('Segoe UI', 12, QFont.Bold))
        self.countdown.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.countdown.setFixedWidth(68)
        layout.addWidget(self.countdown)

    def update_data(self, text, remaining, countdown_text, countdown_color, quota_color):
        signature = (text, remaining, countdown_text, countdown_color, quota_color)
        if getattr(self, '_rendered', None) == signature:
            return
        self._rendered = signature
        self.text_label.setText(text)
        self.text_label.setFixedWidth(max(76, self.text_label.fontMetrics().horizontalAdvance(text) + 2))
        self.text_label.setStyleSheet(f'color: {quota_color};')
        self.bar.set_value(remaining)
        self.bar.set_color(quota_color)
        self.countdown.setText(countdown_text)
        self.countdown.setFixedWidth(max(68, self.countdown.fontMetrics().horizontalAdvance(countdown_text) + 2))
        self.countdown.setStyleSheet(f'color: {countdown_color};')


class DetailQuotaRow(QFrame):
    """A larger quota display row used in the account detail panel."""

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setProperty('class', 'card')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 8)
        layout.setSpacing(5)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        self.title_label = QLabel(title)
        self.title_label.setFont(QFont('Segoe UI', 13))
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        self.value_label = QLabel()
        self.value_label.setFont(QFont('Segoe UI', 12, QFont.Bold))
        header_layout.addWidget(self.value_label)
        layout.addWidget(header)

        self.bar = ReserveBar(large=True)
        layout.addWidget(self.bar)

        self.reset_label = QLabel()
        self.reset_label.setFont(QFont('Segoe UI', 11))
        self.reset_label.setProperty('class', 'muted')
        layout.addWidget(self.reset_label)

    def update_data(self, value_text, remaining, value_color, reset_text):
        signature = (value_text, remaining, value_color, reset_text)
        if getattr(self, '_rendered', None) == signature:
            return
        self._rendered = signature
        self.value_label.setText(value_text)
        self.value_label.setStyleSheet(f'color: {value_color};')
        self.bar.set_value(remaining)
        self.bar.set_color(value_color)
        self.reset_label.setText(reset_text)
