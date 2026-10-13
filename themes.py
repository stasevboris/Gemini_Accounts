"""Theme system for Gemini Accounts (PySide6).

Provides dark and light palettes and generates Qt Style Sheets on the fly.
Usage:
    from themes import ThemeManager
    tm = ThemeManager()
    tm.apply(app, 'dark')  # app is a QApplication or QWidget
"""

from PySide6.QtGui import QColor, QPalette

DARK = {
    'bg':               '#10141d',
    'panel':            '#191f2b',
    'card':             '#222a38',
    'card_alt':         '#202938',
    'text':             '#edf2fa',
    'muted':            '#9daec4',
    'accent':           '#739aff',
    'accent_hover':     '#87a8ff',
    'green':            '#66d7b0',
    'green_dim':        '#66e2a7',
    'button':           '#303b50',
    'button_hover':     '#3d4b64',
    'button_text':      '#edf2fa',
    'button_primary_text': '#101728',
    'border':           '#344155',
    'border_selected':  '#739aff',
    'separator':        '#43516a',
    'input_bg':         '#222a38',
    'input_border':     '#3a465c',
    'input_focus':      '#4a6fa5',
    'progress_track':   '#354157',
    'warning':          '#ffbd93',
    'warning_bg':       '#3b3020',
    'warn_text':        '#f7ca70',
    'error':            '#ff8d8d',
    'card_selected':    '#303e59',
    'card_hover':       '#334158',
    'scrollbar':        '#3d4b64',
    'scrollbar_hover':  '#536278',
    'tooltip_bg':       '#2a3347',
    'tooltip_border':   '#43516a',
    'forecast_bg':      '#293344',
    'forecast_text':    '#8995a8',
    'badge_gemini':     '#334d77',
    'badge_claude':     '#654332',
    'model_text':       '#bac9df',
}

LIGHT = {
    'bg':               '#f0f2f5',
    'panel':            '#ffffff',
    'card':             '#ffffff',
    'card_alt':         '#f7f8fa',
    'text':             '#1a1f36',
    'muted':            '#5f6d7f',
    'accent':           '#3c66df',
    'accent_hover':     '#3156c5',
    'green':            '#167458',
    'green_dim':        '#18785c',
    'button':           '#e2e6ed',
    'button_hover':     '#d0d5de',
    'button_text':      '#1a1f36',
    'button_primary_text': '#ffffff',
    'border':           '#d4d9e3',
    'border_selected':  '#4a7cff',
    'separator':        '#d4d9e3',
    'input_bg':         '#ffffff',
    'input_border':     '#c5ccd8',
    'input_focus':      '#4a7cff',
    'progress_track':   '#dde1e9',
    'warning':          '#8b5615',
    'warning_bg':       '#fff4db',
    'warn_text':        '#94650f',
    'error':            '#b83245',
    'card_selected':    '#e8edff',
    'card_hover':       '#f0f3ff',
    'scrollbar':        '#c5ccd8',
    'scrollbar_hover':  '#a8b1be',
    'tooltip_bg':       '#ffffff',
    'tooltip_border':   '#d4d9e3',
    'forecast_bg':      '#e2e6ed',
    'forecast_text':    '#5f6d7f',
    'badge_gemini':     '#d4e2ff',
    'badge_claude':     '#ffe0cc',
    'model_text':       '#5a6a80',
}

THEMES = {'dark': DARK, 'light': LIGHT}


def _qss(t):
    """Build a Qt Style Sheet from a theme palette dict *t*."""
    return f"""
    /* ── Global ─────────────────────────────────────────── */
    * {{
        font-family: 'Segoe UI', 'Microsoft YaHei UI', 'Noto Sans SC', 'Arial', sans-serif;
    }}
    QMainWindow, QDialog {{
        background-color: {t['bg']};
    }}
    QWidget#root {{
        background-color: {t['bg']};
    }}
    QLabel#vpnBanner {{
        background-color: {t['warning_bg']};
        color: {t['warning']};
        padding: 10px;
        border-radius: 8px;
        font-weight: bold;
    }}
    QFrame[class="skeleton"] {{
        background-color: {t['card_hover']};
        border-radius: 8px;
    }}
    QMenu {{
        background-color: {t['panel']};
        color: {t['text']};
        border: 1px solid {t['border']};
        padding: 6px;
    }}
    QMenu::item {{ padding: 6px 18px; }}
    QMenu::item:selected {{ background-color: {t['card_selected']}; }}
    QWidget#sidebar {{
        background-color: {t['panel']};
    }}
    QWidget#body, QWidget#detail, QWidget#statsView {{
        background-color: transparent;
    }}

    /* ── Labels ─────────────────────────────────────────── */
    QLabel {{
        color: {t['text']};
        background: transparent;
    }}
    QLabel[class="muted"] {{
        color: {t['muted']};
    }}
    QLabel[class="warning"] {{
        color: {t['warning']};
    }}
    QLabel[class="warn"] {{
        color: {t['warn_text']};
    }}
    QLabel[class="green"] {{
        color: {t['green']};
    }}
    QLabel[class="accent"] {{
        color: {t['accent']};
    }}

    /* ── Buttons ────────────────────────────────────────── */
    QPushButton {{
        background-color: {t['button']};
        color: {t['button_text']};
        border: none;
        border-radius: 9px;
        padding: 8px 18px;
        font-size: 13px;
        font-weight: bold;
    }}
    QPushButton:hover {{
        background-color: {t['button_hover']};
    }}
    QPushButton:pressed {{
        background-color: {t['border']};
    }}
    QPushButton:disabled {{
        color: {t['muted']};
        background-color: {t['button']};
    }}
    QPushButton[primary="true"] {{
        background-color: {t['accent']};
        color: {t['button_primary_text']};
    }}
    QPushButton[primary="true"]:hover {{
        background-color: {t['accent_hover']};
    }}
    QPushButton[flat="true"] {{
        background-color: transparent;
        padding: 0px;
    }}
    QPushButton[class="danger"] {{
        padding: 0px;
        color: {t['warning']};
    }}
    QComboBox[compact="true"] {{
        padding: 2px 20px 2px 4px;
        font-size: 11px;
        min-height: 20px;
    }}
    QComboBox[compact="true"]::drop-down {{
        width: 16px;
    }}
    QPushButton[flat="true"]:hover {{
        background-color: {t['button']};
    }}

    /* ── Inputs ─────────────────────────────────────────── */
    QLineEdit {{
        background-color: {t['input_bg']};
        color: {t['text']};
        border: 1px solid {t['input_border']};
        border-radius: 8px;
        padding: 8px 12px;
        font-size: 13px;
    }}
    QLineEdit:focus {{
        border-color: {t['input_focus']};
    }}
    QSpinBox, QDoubleSpinBox {{
        background-color: {t['input_bg']};
        color: {t['text']};
        border: 1px solid {t['input_border']};
        border-radius: 4px;
        padding: 1px 3px;
        font-size: 13px;
    }}
    QSpinBox:focus, QDoubleSpinBox:focus {{
        border-color: {t['input_focus']};
    }}
    QSpinBox QLineEdit, QDoubleSpinBox QLineEdit {{
        padding: 0;
        border: none;
        border-radius: 0;
        background: transparent;
        color: {t['text']};
    }}

    QTableWidget {{
        background-color: {t['panel']};
        color: {t['text']};
        gridline-color: {t['border']};
        border: 1px solid {t['border']};
    }}
    QHeaderView::section {{
        background-color: {t['button']};
        color: {t['text']};
        border: none;
        border-bottom: 1px solid {t['border']};
        padding: 6px 8px;
    }}

    /* ── Scroll areas ──────────────────────────────────── */
    QScrollArea {{
        background: transparent;
        border: none;
    }}
    QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 8px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {t['scrollbar']};
        border-radius: 4px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {t['scrollbar_hover']};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
        height: 0px;
    }}
    QScrollBar:horizontal {{
        height: 0px;
    }}

    /* ── Combo box ─────────────────────────────────────── */
    QComboBox {{
        background-color: {t['card']};
        color: {t['text']};
        border: 1px solid {t['input_border']};
        border-radius: 8px;
        padding: 6px 12px;
        font-size: 13px;
        min-height: 28px;
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QComboBox::down-arrow {{ image: none; width: 0px; height: 0px; }}
    QComboBox QAbstractItemView {{
        background-color: {t['panel']};
        color: {t['text']};
        border: 1px solid {t['border']};
        border-radius: 8px;
        padding: 4px;
        selection-background-color: {t['card_selected']};
        selection-color: {t['text']};
    }}

    /* ── Check box ─────────────────────────────────────── */
    QCheckBox {{
        color: {t['text']};
        spacing: 8px;
        font-size: 13px;
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border-radius: 4px;
        border: 2px solid {t['input_border']};
        background: {t['input_bg']};
    }}
    QCheckBox::indicator:checked {{
        background: {t['accent']};
        border-color: {t['accent']};
    }}

    /* ── Text edit ─────────────────────────────────────── */
    QTextEdit, QPlainTextEdit {{
        background-color: {t['card']};
        color: {t['text']};
        border: none;
        border-radius: 10px;
        padding: 10px;
        font-size: 12px;
        font-family: 'Segoe UI', 'Microsoft YaHei UI', sans-serif;
    }}

    /* ── Cards ─────────────────────────────────────────── */
    QFrame[class="card"] {{
        background-color: {t['card']};
        border: 1px solid {t['border']};
        border-radius: 10px;
    }}
    QFrame[class="card-selected"] {{
        background-color: {t['card']};
        border: 1px solid {t['border_selected']};
        border-radius: 10px;
    }}
    QFrame[class="card-mode"] {{
        background-color: {t['card']};
        border: none;
        border-radius: 14px;
    }}

    /* ── Progress bars ─────────────────────────────────── */
    QProgressBar {{
        background-color: {t['progress_track']};
        border: none;
        border-radius: 3px;
        max-height: 6px;
        min-height: 6px;
        text-align: center;
    }}
    QProgressBar::chunk {{
        background-color: {t['green']};
        border-radius: 3px;
    }}
    QProgressBar[size="large"] {{
        max-height: 9px;
        min-height: 9px;
        border-radius: 5px;
    }}
    QProgressBar[size="large"]::chunk {{
        border-radius: 5px;
    }}

    /* ── Tooltips ──────────────────────────────────────── */
    QToolTip {{
        background-color: {t['tooltip_bg']};
        color: {t['text']};
        border: 1px solid {t['tooltip_border']};
        border-radius: 6px;
        padding: 6px 10px;
        font-size: 12px;
    }}

    /* ── Segmented control ─────────────────────────────── */
    QPushButton[segment="true"] {{
        background-color: {t['card']};
        color: {t['muted']};
        border: 1px solid {t['border']};
        border-radius: 8px;
        padding: 5px 14px;
        font-size: 12px;
        font-weight: normal;
    }}
    QPushButton[segment="true"]:hover {{
        background-color: {t['card_hover']};
    }}
    QPushButton[segment="true"][active="true"] {{
        background-color: {t['accent']};
        color: {t['button_primary_text']};
        border-color: {t['accent']};
        font-weight: bold;
    }}

    /* ── Message box ──────────────────────────────────── */
    QMessageBox {{
        background-color: {t['panel']};
    }}
    QMessageBox QLabel {{
        color: {t['text']};
        font-size: 13px;
    }}
    QMessageBox QPushButton {{
        min-width: 80px;
        min-height: 32px;
    }}

    /* ── Input dialog ─────────────────────────────────── */
    QInputDialog {{
        background-color: {t['panel']};
    }}
    QInputDialog QLabel {{
        color: {t['text']};
    }}

    /* ── File dialog ──────────────────────────────────── */
    QFileDialog {{
        background-color: {t['panel']};
    }}
    """


class ThemeManager:
    """Manages theme switching and persistence."""

    def __init__(self):
        self.current = 'dark'
        self._cache = {}

    def qss(self, name=None):
        name = name or self.current
        if name not in self._cache:
            self._cache[name] = _qss(THEMES[name])
        return self._cache[name]

    def colors(self, name=None):
        return THEMES[name or self.current]

    def apply(self, widget, name=None):
        if name:
            self.current = name
        colors = self.colors()
        widget.setStyleSheet(self.qss())
        widget.ensurePolished()
        palette = QPalette(widget.palette())
        for role, key in ((QPalette.Window, 'bg'), (QPalette.WindowText, 'text'),
                          (QPalette.Base, 'input_bg'), (QPalette.AlternateBase, 'card_alt'),
                          (QPalette.Text, 'text'), (QPalette.Button, 'button'),
                          (QPalette.ButtonText, 'button_text'), (QPalette.Highlight, 'accent'),
                          (QPalette.HighlightedText, 'button_primary_text'),
                          (QPalette.ToolTipBase, 'tooltip_bg'), (QPalette.ToolTipText, 'text')):
            palette.setColor(role, QColor(colors[key]))
        palette.setColor(QPalette.Disabled, QPalette.Text, QColor(colors['muted']))
        palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(colors['muted']))
        widget.setPalette(palette)

    def toggle(self):
        self.current = 'light' if self.current == 'dark' else 'dark'
        return self.current

    def color(self, key):
        return THEMES[self.current].get(key, '#ff00ff')
