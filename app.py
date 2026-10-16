import ctypes
import copy
import hashlib
import math
import colorsys
import time
import webbrowser
from pathlib import Path
import os
import sys
import winreg
from datetime import datetime, timezone
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QGraphicsOpacityEffect,
    QHBoxLayout, QLabel, QPushButton, QScrollArea, QFrame, QSplitter,
    QStackedWidget, QLineEdit, QComboBox, QCheckBox, QTextEdit, QDialog,
    QMessageBox, QFileDialog, QInputDialog, QSizePolicy, QToolTip, QProgressBar, QGridLayout, QLayout, QSystemTrayIcon, QMenu,
    QDoubleSpinBox, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView)
from PySide6.QtCore import (Qt, Signal, QObject, QRunnable, QThreadPool, QTimer,
    QSize, QRectF, QPointF, QMargins, QPropertyAnimation, QEasingCurve)
from PySide6.QtGui import (QIcon, QFont, QFontMetrics, QColor, QPainter, QPen,
    QBrush, QPainterPath, QPixmap, QCursor, QGuiApplication)
from PySide6.QtNetwork import QNetworkInterface
from backend import Controller, AccountError
from activity import Activity
from account_uptime import AccountUptime
from alert_tracker import AlertTracker, account_alert_conditions
from token_capacity import TokenCapacity
from team_ui import TeamPanel
from routing import rank_accounts, quota_projection, quota_entry, weekly_threshold, weekly_depleted
from integrations import Integrations
import api_keys
from chatgpt_ui import ChatGPTPanelMixin
from claude_ui import ClaudeAccountsPanel
from policy_ui import PolicyControlsMixin
from quota_limits import account_priority, quota_floor, blocked_families, clear_quota_limits, quota_policy_lock, oauth_quota_groups
from account_status import account_status, google_account_status, safe_detail
from model_names import model_name
from locales import tr, set_language, current_language, LANGUAGES, display_reason
from themes import ThemeManager, THEMES
from widgets import (QuotaBar, ForecastWidget, SegmentedControl, AccountCard,
    RainbowBorderWidget, ProviderBadge, QuotaRowWidget, DetailQuotaRow, ui_icon, ThemedComboBox)

SIDEBAR_WIDTH = 400
MODEL_LABELS = {
    'claude-sonnet-4-5': 'Gemini 3.1 Pro Low',
    'claude-haiku-4-5': 'Gemini 3 Flash',
    'claude-sonnet-4-6': 'Claude Sonnet 4.6',
    'claude-opus-4-6-thinking': 'Claude Opus 4.6 Thinking',
}


# ── Async worker ──────────────────────────────────────────────────────

class WorkerSignals(QObject):
    finished = Signal(object, object)

class Worker(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    def run(self):
        try:
            result = self.fn()
            self.signals.finished.emit(result, None)
        except Exception as exc:
            self.signals.finished.emit(None, exc)


# ── Main application window ──────────────────────────────────────────

class App(PolicyControlsMixin, ChatGPTPanelMixin, QMainWindow):
    def __init__(self):
        super().__init__()
        self.controller = Controller()
        self.model_aliases = self.controller.model_aliases()
        self.integrations = Integrations(self.controller)
        self.theme = ThemeManager()
        self.items = []
        self.selected = None
        self.model_cache = {}
        self.quota_cache = {}
        self.quota_pending = set()
        self.google_startup_checked = set()
        self.google_startup_probes = {}
        self.account_widgets = {}
        self.detail_account = object()
        self.detail_quota_widgets = {}
        self.model_widgets = {}
        self.drawn_models = None
        self.busy = False
        self._workers = set()
        self.pending_login = None
        self.login_url = None
        self.login_callback_uri = None
        self.login_callback_input = None
        self.account_uptime = AccountUptime(self.controller.data_dir / 'account-uptime.json')
        self.alert_tracker = AlertTracker()
        self.token_capacity = TokenCapacity(self.controller.data_dir / 'token-capacity.json')
        self.capacity_usage_ready = False
        self.activity = Activity(self.controller.data_dir / 'activity.json')
        self.activity_state = copy.deepcopy(self.activity.state)
        self.activity_started = False
        self.activity_busy = False
        self.api_stats = api_keys.Stats(self.controller.data_dir / 'api-key-stats.json').snapshot()
        self.api_stats_busy = False
        self.chatgpt_accounts = []
        self.chatgpt_busy = False
        self.chatgpt_checked = 0
        self.chatgpt_login_dialog = None
        self.gateway_jobs = []
        self.gateway_jobs_checked = 0
        self.activity_rows = {}
        self.policy_busy = False
        self.policy_pending = False
        self.policy_rows = []
        self.policy_group = 'gemini'
        self.details_collapsed = False
        self.closed = False
        self.available_update = None
        self.pending_update = None
        self.activity_strategy = 'unknown'
        self.vpn_active = True
        self.vpn_check_busy = False
        self.is_mini = False
        self._expanded_size = QSize(1120, 850)

        # Restore preferences
        saved_lang = self.controller.preferences.get('language', 'en')
        set_language(saved_lang)
        saved_theme = self.controller.preferences.get('theme', 'dark')
        self.theme.current = saved_theme if saved_theme in THEMES else 'dark'

        self._build_ui()
        self.theme.apply(self, self.theme.current)
        self.apply_mica()
        self.refresh_toolbar_icons()

        # Timers
        QTimer.singleShot(120, self, lambda: self.refresh(prepare=True) if not self.closed else None)
        self._quota_timer = QTimer(self)
        self._quota_timer.timeout.connect(self.periodic_quota)
        self._quota_timer.start(60000)
        self._countdown_timer = QTimer(self)
        self._countdown_timer.timeout.connect(self.tick_countdowns)
        self._countdown_timer.start(15000)
        self._animate_timer = QTimer(self)
        self._animate_timer.timeout.connect(self.animate_active_borders)
        self._animate_timer.start(100)
        self._gateway_timer = QTimer(self)
        self._gateway_timer.timeout.connect(self.poll_gateway_jobs)
        self._gateway_timer.start(1000)
        self._api_timer = QTimer(self)
        self._api_timer.timeout.connect(self.poll_api_stats)
        self._api_timer.timeout.connect(self.refresh_chatgpt_accounts)
        self._api_timer.timeout.connect(self.claude_accounts_panel.refresh)
        self._api_timer.start(5000)
        self._init_desktop_controls()
        QTimer.singleShot(30000, self.check_for_updates)
        if self.controller.preferences.get('details-collapsed'):
            QTimer.singleShot(180, self.toggle_details)

    # ── UI construction ───────────────────────────────────────────────

    def _build_ui(self):
        self.setWindowTitle(tr('app_title'))
        icon = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'app.ico'
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))

        screen = QGuiApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else QRectF(0, 0, 1920, 1080)
        h = max(680, min(int(avail.height()) - 48, 1300))
        self.resize(1120, h)
        self.setMinimumSize(990, 680)

        central = QWidget()
        central.setObjectName('root')
        central.setAttribute(Qt.WA_StyledBackground)
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._build_sidebar()
        main_layout.addWidget(self.sidebar)
        self._build_body()
        main_layout.addWidget(self.body_container, 1)
        self.build_provider_controls()

    def _init_desktop_controls(self):
        icon = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'app.ico'
        self.tray_icon = QSystemTrayIcon(QIcon(str(icon)), self)
        self.tray_menu = QMenu(self)
        self.action_show = self.tray_menu.addAction(tr('tray_show'))
        self.action_show.triggered.connect(self.show_window)
        self.action_exit = self.tray_menu.addAction(tr('tray_exit'))
        self.action_exit.triggered.connect(self.exit_app)
        
        self.tray_icon.setContextMenu(self.tray_menu)
        self.theme.apply(self.tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_activated)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon.show()

        # VPN Monitoring
        self._vpn_timer = QTimer(self)
        self._vpn_timer.timeout.connect(self.check_vpn)
        self._vpn_timer.start(4000)
        QTimer.singleShot(0, self.check_vpn)

    def _build_sidebar(self):
        self.sidebar = QWidget()
        self.sidebar.setObjectName('sidebar')
        self.sidebar.setFixedWidth(SIDEBAR_WIDTH)
        layout = QVBoxLayout(self.sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 6, 12, 4)
        title = QLabel(tr('sidebar_title'))
        title.setFont(QFont('Segoe UI', 15, QFont.Bold))
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.theme_button = QPushButton('☀' if self.theme.current == 'dark' else '🌙')
        self.theme_button.setProperty('flat', True)
        self.theme_button.setFixedSize(28, 26)
        self.theme_button.setFont(QFont('Segoe UI', 15))
        self.theme_button.setToolTip(tr('tip_theme_toggle'))
        self.theme_button.clicked.connect(self.toggle_theme)
        header_layout.addWidget(self.theme_button)

        self.lang_combo = ThemedComboBox()
        self.lang_combo.setProperty('compact', True)
        self.lang_combo.setFixedWidth(64)
        self.lang_combo.setFixedHeight(26)
        for code, name in LANGUAGES.items():
            self.lang_combo.addItem(code.upper(), code)
        self.lang_combo.setCurrentIndex(list(LANGUAGES.keys()).index(current_language()))
        self.lang_combo.setToolTip(tr('tip_language'))
        self.lang_combo.currentIndexChanged.connect(self.change_language)
        header_layout.addWidget(self.lang_combo)

        self.models_button = QPushButton('⚙')
        self.models_button.setProperty('flat', True)
        self.models_button.setFixedSize(26, 26)
        self.models_button.setFont(QFont('Segoe UI', 17))
        self.models_button.setToolTip(tr('tip_model_settings'))
        self.models_button.clicked.connect(self.model_settings)

        self.details_toggle = QPushButton('☰')
        self.details_toggle.setProperty('flat', True)
        self.details_toggle.setFixedSize(28, 26)
        self.details_toggle.setFont(QFont('Segoe UI', 20))
        self.details_toggle.setToolTip(tr('tip_toggle_sidebar'))
        self.details_toggle.clicked.connect(self.toggle_details)
        layout.addWidget(header)

        # Add account button
        self.add_button = QPushButton(tr('btn_add_account'))
        self.add_button.setProperty('primary', True)
        self.add_button.setFixedHeight(30)
        self.add_button.setToolTip(tr('tip_add_account'))
        self.add_button.clicked.connect(self.add_account)
        btn_container = QWidget()
        btn_layout = QHBoxLayout(btn_container)
        btn_layout.setContentsMargins(16, 0, 16, 6)
        btn_layout.addWidget(self.add_button, 1)
        btn_layout.addWidget(self.models_button)
        btn_layout.addWidget(self.details_toggle)
        layout.addWidget(btn_container)

        # Account list scroll area
        self.account_scroll = QScrollArea()
        self.account_scroll.setWidgetResizable(True)
        self.account_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.account_list_widget = QWidget()
        self.account_list_layout = QVBoxLayout(self.account_list_widget)
        self.account_list_layout.setSizeConstraint(QLayout.SetMinAndMaxSize)
        self.account_list_layout.setContentsMargins(12, 0, 12, 0)
        self.account_list_layout.setSpacing(1)
        self.account_list_layout.addStretch()
        self._build_skeleton()
        self.account_list_layout.insertWidget(0, self.skeleton_widget)
        self.account_scroll.setWidget(self.account_list_widget)
        layout.addWidget(self.account_scroll, 1)

        # Service status
        self.service = QLabel(tr('status_connecting'))
        self.service.setFont(QFont('Segoe UI', 10))
        self.service.setProperty('class', 'muted')
        self.service.setContentsMargins(18, 2, 18, 2)
        layout.addWidget(self.service)

        # Total quota (5h)
        self.total_quota_frame = QWidget()
        tq_layout = QVBoxLayout(self.total_quota_frame)
        tq_layout.setContentsMargins(18, 0, 18, 0)
        tq_layout.setSpacing(1)
        tq_header = QWidget()
        tq_h_layout = QHBoxLayout(tq_header)
        tq_h_layout.setContentsMargins(0, 0, 0, 0)
        self.total_quota_title = QLabel(tr('quota_5h_pooled'))
        self.total_quota_title.setFont(QFont('Segoe UI', 11))
        self.total_quota_title.setWordWrap(True)
        self.total_quota_title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        tq_h_layout.addWidget(self.total_quota_title, 1)
        self.total_quota_value = QLabel('—')
        self.total_quota_value.setFont(QFont('Segoe UI', 12, QFont.Bold))
        self.total_quota_value.setProperty('class', 'muted')
        tq_h_layout.addWidget(self.total_quota_value)
        tq_layout.addWidget(tq_header)
        self.total_quota_bar = QuotaBar()
        tq_layout.addWidget(self.total_quota_bar)
        self.forecast_widget = ForecastWidget()
        self.forecast_widget.setVisible(False)
        tq_layout.addWidget(self.forecast_widget)
        layout.addWidget(self.total_quota_frame)
        self.total_forecast = []
        self.total_remaining = None

        # Total quota (weekly)
        weekly_frame = QWidget()
        self.total_weekly_frame = weekly_frame
        wq_layout = QVBoxLayout(weekly_frame)
        wq_layout.setContentsMargins(18, 0, 18, 6)
        wq_layout.setSpacing(1)
        wq_header = QWidget()
        wq_h_layout = QHBoxLayout(wq_header)
        wq_h_layout.setContentsMargins(0, 0, 0, 0)
        self.total_weekly_title = QLabel(tr('quota_1w_pooled'))
        self.total_weekly_title.setFont(QFont('Segoe UI', 11))
        self.total_weekly_title.setWordWrap(True)
        self.total_weekly_title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        wq_h_layout.addWidget(self.total_weekly_title, 1)
        self.total_weekly_value = QLabel('—')
        self.total_weekly_value.setFont(QFont('Segoe UI', 12, QFont.Bold))
        self.total_weekly_value.setProperty('class', 'muted')
        wq_h_layout.addWidget(self.total_weekly_value)
        wq_layout.addWidget(wq_header)
        self.total_weekly_bar = QuotaBar()
        wq_layout.addWidget(self.total_weekly_bar)
        self.weekly_forecast_widget = ForecastWidget()
        self.weekly_forecast_widget.setVisible(False)
        wq_layout.addWidget(self.weekly_forecast_widget)
        layout.addWidget(weekly_frame)
        
        # Bottom controls (Mini Mode & Autostart)
        bottom_controls = QWidget()
        bc_layout = QHBoxLayout(bottom_controls)
        bc_layout.setContentsMargins(18, 0, 18, 16)
        
        self.chk_autostart = QCheckBox(tr('chk_autostart'))
        self.chk_autostart.setToolTip(tr('tip_autostart'))
        if hasattr(self, 'is_autostart'):
            self.chk_autostart.setChecked(self.is_autostart())
        self.chk_autostart.toggled.connect(self.set_autostart)
        bc_layout.addWidget(self.chk_autostart)
        bc_layout.addStretch()
        
        self.btn_mini = QPushButton(tr('btn_mini_mode'))
        self.btn_mini.setToolTip(tr('tip_mini_mode'))
        self.btn_mini.clicked.connect(self.toggle_mini_mode)
        bc_layout.addWidget(self.btn_mini)
        
        layout.addWidget(bottom_controls)

        self.total_weekly_forecast = []
        self.total_weekly_remaining = None


    def _build_skeleton(self):
        self.skeleton_widget = QWidget()
        layout = QVBoxLayout(self.skeleton_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.skel_effect = QGraphicsOpacityEffect(self.skeleton_widget)
        self.skeleton_widget.setGraphicsEffect(self.skel_effect)
        self.skel_anim = QPropertyAnimation(self.skel_effect, b"opacity", self)
        self.skel_anim.setDuration(800)
        self.skel_anim.setStartValue(0.4)
        self.skel_anim.setEndValue(1.0)
        self.skel_anim.setLoopCount(-1) # Infinite ping-pong
        self.skel_anim.setEasingCurve(QEasingCurve.InOutSine)
        
        for _ in range(4):
            skel = QFrame()
            skel.setFixedHeight(120)
            skel.setProperty('class', 'skeleton')
            layout.addWidget(skel)
        layout.addStretch()
        
        self.skel_anim.start()
        return self.skeleton_widget

    def _build_body(self):
        self.body_container = QWidget()
        body_outer = QVBoxLayout(self.body_container)
        body_outer.setContentsMargins(32, 28, 32, 28)
        body_outer.setSpacing(0)

        # VPN Banner
        self.vpn_banner = QLabel(tr('vpn_warning_banner'))
        self.vpn_banner.setAlignment(Qt.AlignCenter)
        self.vpn_banner.setObjectName('vpnBanner')
        self.vpn_banner.setWordWrap(True)
        self.vpn_banner.setVisible(not self.vpn_active)
        body_outer.addWidget(self.vpn_banner)
        body_outer.addSpacing(15)


        # Header row
        header = QWidget()
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 0)
        heading = QLabel(tr('heading_saved_accounts'))
        heading.setFont(QFont('Segoe UI', 24, QFont.Bold))
        heading.setWordWrap(True)
        h_layout.addWidget(heading, 1)
        h_layout.addStretch()
        conn_btn = QPushButton(tr('btn_connect_apps'))
        conn_btn.setToolTip(tr('tip_connect_apps'))
        conn_btn.clicked.connect(self.connection_settings)
        h_layout.addWidget(conn_btn)
        body_outer.addWidget(header)

        subtitle = QLabel(tr('subtitle_switch'))
        subtitle.setFont(QFont('Segoe UI', 14))
        subtitle.setWordWrap(True)
        subtitle.setProperty('class', 'muted')
        subtitle.setContentsMargins(0, 4, 0, 24)
        body_outer.addWidget(subtitle)

        # Mode card
        self.mode_frame = QFrame()
        self.mode_frame.setProperty('class', 'card-mode')
        mode_layout = QVBoxLayout(self.mode_frame)
        mode_layout.setContentsMargins(18, 15, 18, 15)
        mode_layout.setSpacing(4)
        self.mode_label = QLabel(tr('loading_accounts'))
        self.mode_label.setFont(QFont('Segoe UI', 14, QFont.Bold))
        self.mode_label.setToolTip(tr('mode_count_hint'))
        self.mode_label.setWordWrap(True)
        mode_layout.addWidget(self.mode_label)
        self.mode_note = QLabel(tr('mode_connected_clients'))
        self.mode_note.setFont(QFont('Segoe UI', 12))
        self.mode_note.setWordWrap(True)
        self.mode_note.setProperty('class', 'muted')
        mode_layout.addWidget(self.mode_note)
        self.mode_activity = QLabel(tr('last_request_waiting'))
        self.mode_activity.setFont(QFont('Segoe UI', 12))
        self.mode_activity.setWordWrap(True)
        self.mode_activity.setProperty('class', 'muted')
        mode_layout.addWidget(self.mode_activity)
        self.pool_button = QPushButton(tr('btn_use_all_auto'))
        self.pool_button.setToolTip(tr('tip_use_all'))
        self.pool_button.clicked.connect(lambda: self.action(
            lambda: self.controller.route(), tr('action_routing_enabled')))
        mode_layout.addWidget(self.pool_button)
        body_outer.addWidget(self.mode_frame)

        # View switcher
        self.view_switch = SegmentedControl([tr('tab_account_quotas'), tr('tab_routing_stats'), tr('tab_api_keys'), tr('tab_chatgpt'), tr('tab_claude_accounts'), tr('team_tab')], columns=3)
        self.view_switch.value_changed.connect(self.change_view)
        body_outer.addWidget(self.view_switch)

        # Stacked views
        self.view_stack = QStackedWidget()

        # Detail view (account & quotas)
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.detail_widget = QWidget()
        self.detail_layout = QVBoxLayout(self.detail_widget)
        self.detail_layout.setSizeConstraint(QLayout.SetMinAndMaxSize)
        self.detail_layout.setContentsMargins(0, 0, 0, 0)
        self.detail_layout.setSpacing(0)
        self.detail_layout.addStretch()
        self.detail_scroll.setWidget(self.detail_widget)
        self.view_stack.addWidget(self.detail_scroll)

        # Stats view (routing statistics)
        self.stats_scroll = QScrollArea()
        self.stats_scroll.setWidgetResizable(True)
        self.stats_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.stats_widget = QWidget()
        self.stats_layout = QVBoxLayout(self.stats_widget)
        self.stats_layout.setContentsMargins(0, 10, 0, 0)
        self.stats_layout.setSpacing(8)
        self._build_stats_view()
        self.stats_scroll.setWidget(self.stats_widget)
        self.view_stack.addWidget(self.stats_scroll)

        self.api_scroll = QScrollArea()
        self.api_scroll.setWidgetResizable(True)
        self.api_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.api_widget = QWidget()
        self.api_layout = QVBoxLayout(self.api_widget)
        self.api_layout.setContentsMargins(0, 10, 0, 0)
        self.api_layout.setSpacing(10)
        heading = QLabel(tr('tab_api_keys'))
        heading.setFont(QFont('Segoe UI', 22, QFont.Bold))
        self.api_layout.addWidget(heading)
        note = QLabel(tr('api_note'))
        note.setWordWrap(True)
        note.setProperty('class', 'muted')
        self.api_layout.addWidget(note)
        self.api_add_button = QPushButton(tr('api_add'))
        self.api_add_button.clicked.connect(lambda: self.edit_api_profile())
        self.api_layout.addWidget(self.api_add_button)
        self.api_cards = QWidget()
        self.api_cards_layout = QVBoxLayout(self.api_cards)
        self.api_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.api_cards_layout.setSpacing(10)
        self.api_layout.addWidget(self.api_cards)
        self.api_layout.addStretch()
        self.api_scroll.setWidget(self.api_widget)
        self.view_stack.addWidget(self.api_scroll)
        self.render_api_profiles()
        self.build_chatgpt_panel()
        if not hasattr(self, 'claude_accounts_panel'):
            self.claude_accounts_panel = ClaudeAccountsPanel(self)
        else:
            self.claude_accounts_panel.render()
        self.view_stack.addWidget(self.claude_accounts_panel)
        if not hasattr(self, 'team_panel'):
            self.team_panel = TeamPanel(self)
        else:
            self.team_panel.render()
        self.view_stack.addWidget(self.team_panel)

        body_outer.addWidget(self.view_stack, 1)

        # Bottom notice
        self.notice = QLabel(tr('notice_signins_preserved'))
        self.notice.setFont(QFont('Segoe UI', 12))
        self.notice.setProperty('class', 'muted')
        self.notice.setWordWrap(True)
        self.notice.setContentsMargins(0, 12, 0, 0)
        body_outer.addWidget(self.notice)

    def _build_stats_view(self):
        self.stats_title = QLabel(tr('stats_auto_routing'))
        self.stats_title.setFont(QFont('Segoe UI', 22, QFont.Bold))
        self.stats_layout.addWidget(self.stats_title)

        btn_diag_save = QPushButton(tr('btn_save_diag'))
        btn_diag_save.setToolTip(tr('tip_save_diag'))
        btn_diag_save.clicked.connect(self.save_diagnostic_log)
        self.stats_layout.addWidget(btn_diag_save)
        btn_diag_send = QPushButton(tr('btn_send_diag'))
        btn_diag_send.setToolTip(tr('tip_send_diag'))
        btn_diag_send.clicked.connect(self.send_diagnostic_log)
        self.stats_layout.addWidget(btn_diag_send)
        self.update_button = QPushButton(tr('btn_check_updates'))
        self.update_button.setToolTip(tr('tip_check_updates'))
        self.update_button.clicked.connect(self.check_for_updates)
        self.stats_layout.addWidget(self.update_button)

        self.stats_strategy = QLabel(tr('stats_starting'))
        self.stats_strategy.setFont(QFont('Segoe UI', 13))
        self.stats_strategy.setProperty('class', 'muted')
        self.stats_strategy.setWordWrap(True)
        self.stats_layout.addWidget(self.stats_strategy)

        priority_heading = QLabel(tr('stats_priority_heading'))
        priority_heading.setFont(QFont('Segoe UI', 15, QFont.Bold))
        self.stats_layout.addWidget(priority_heading)

        self.policy_control = SegmentedControl([tr('stats_current_model'), tr('models_gemini_group'), 'Claude / GPT'])
        pref_group = self.controller.preferences.get('reset-group')
        if pref_group == 'gemini':
            self.policy_control.set(tr('models_gemini_group'))
        elif pref_group == 'claude':
            self.policy_control.set('Claude / GPT')
        self.policy_control.value_changed.connect(self.set_policy_group)
        self.stats_layout.addWidget(self.policy_control)

        self.policy_label = QLabel(tr('stats_loading_quotas'))
        self.policy_label.setFont(QFont('Segoe UI', 12))
        self.policy_label.setProperty('class', 'muted')
        self.policy_label.setWordWrap(True)
        self.stats_layout.addWidget(self.policy_label)

        self.stats_latest = QLabel(tr('stats_last_success_none'))
        self.stats_latest.setFont(QFont('Segoe UI', 16, QFont.Bold))
        self.stats_latest.setWordWrap(True)
        self.stats_layout.addWidget(self.stats_latest)

        self.stats_note = QLabel(tr('stats_accounts_note'))
        self.stats_note.setFont(QFont('Segoe UI', 12))
        self.stats_note.setProperty('class', 'muted')
        self.stats_note.setWordWrap(True)
        self.stats_layout.addWidget(self.stats_note)

        self.stats_totals = QLabel('')
        self.stats_totals.setFont(QFont('Segoe UI', 13))
        self.stats_totals.setWordWrap(True)
        self.stats_layout.addWidget(self.stats_totals)

        self.capacity_heading = QLabel(tr('capacity_heading'))
        self.capacity_heading.setFont(QFont('Segoe UI', 16, QFont.Bold))
        self.stats_layout.addWidget(self.capacity_heading)
        self.capacity_note = QLabel(tr('capacity_note'))
        self.capacity_note.setProperty('class', 'muted')
        self.capacity_note.setWordWrap(True)
        self.stats_layout.addWidget(self.capacity_note)
        capacity_controls = QHBoxLayout()
        capacity_controls.addWidget(QLabel(tr('capacity_share')))
        self.capacity_share = QDoubleSpinBox()
        self.capacity_share.setRange(1, 100)
        self.capacity_share.setDecimals(1)
        self.capacity_share.setSuffix(' %')
        self.capacity_share.setKeyboardTracking(False)
        self.capacity_share.setValue(float(self.controller.preferences.get('token-capacity-share', 20)))
        self.capacity_share.valueChanged.connect(lambda _: self.render_token_capacity())
        self.capacity_share.editingFinished.connect(self.save_capacity_share)
        capacity_controls.addWidget(self.capacity_share)
        capacity_controls.addStretch()
        self.stats_layout.addLayout(capacity_controls)
        self.capacity_empty = QLabel(tr('capacity_collecting'))
        self.capacity_empty.setProperty('class', 'muted')
        self.capacity_empty.setWordWrap(True)
        self.stats_layout.addWidget(self.capacity_empty)
        self.capacity_table = QTableWidget(0, 6)
        self.capacity_table.setHorizontalHeaderLabels([tr('capacity_provider'), tr('capacity_plan'),
            tr('capacity_model'), tr('capacity_window'), tr('capacity_estimate'), tr('capacity_samples')])
        self.capacity_table.verticalHeader().setVisible(False)
        self.capacity_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.capacity_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.capacity_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.capacity_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.capacity_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        for column in (3, 4, 5):
            self.capacity_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeToContents)
        self.capacity_table.setMinimumHeight(72)
        self.capacity_table.setMaximumHeight(240)
        self.capacity_table.setVisible(False)
        self.stats_layout.addWidget(self.capacity_table)

        self.forecast_heading = QLabel(tr('quota_eta_heading'))
        self.forecast_heading.setFont(QFont('Segoe UI', 16, QFont.Bold))
        self.stats_layout.addWidget(self.forecast_heading)
        self.forecast_note = QLabel(tr('quota_eta_note'))
        self.forecast_note.setProperty('class', 'muted')
        self.forecast_note.setWordWrap(True)
        self.stats_layout.addWidget(self.forecast_note)
        self.forecast_empty = QLabel(tr('quota_eta_collecting'))
        self.forecast_empty.setProperty('class', 'muted')
        self.forecast_empty.setWordWrap(True)
        self.stats_layout.addWidget(self.forecast_empty)
        self.forecast_table = QTableWidget(0, 7)
        self.forecast_table.setHorizontalHeaderLabels([tr('capacity_provider'), tr('quota_eta_account'),
            tr('capacity_model'), tr('capacity_window'), tr('quota_eta_to_reserve'),
            tr('quota_eta_reset'), tr('quota_eta_outlook')])
        self.forecast_table.verticalHeader().setVisible(False)
        self.forecast_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.forecast_table.setSelectionMode(QAbstractItemView.NoSelection)
        for column in (0, 1, 3, 4, 5, 6):
            self.forecast_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeToContents)
        self.forecast_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.forecast_table.setMinimumHeight(72)
        self.forecast_table.setMaximumHeight(260)
        self.forecast_table.setVisible(False)
        self.stats_layout.addWidget(self.forecast_table)

        self.stats_accounts_widget = QWidget()
        self.stats_accounts_layout = QVBoxLayout(self.stats_accounts_widget)
        self.stats_accounts_layout.setContentsMargins(0, 0, 0, 0)
        self.stats_accounts_layout.setSpacing(4)
        self.stats_layout.addWidget(self.stats_accounts_widget)

        journal_heading = QLabel(tr('stats_journal_heading'))
        journal_heading.setFont(QFont('Segoe UI', 16, QFont.Bold))
        self.stats_layout.addWidget(journal_heading)

        self.journal_filter = SegmentedControl([tr('stats_filter_all'), tr('stats_filter_switches'), tr('stats_filter_errors')])
        self.journal_filter.value_changed.connect(lambda _: self.render_activity())
        self.stats_layout.addWidget(self.journal_filter)

        self.stats_journal = QTextEdit()
        self.stats_journal.setReadOnly(True)
        self.stats_journal.setMinimumHeight(300)
        self.stats_layout.addWidget(self.stats_journal)

        self.stats_observed = QLabel('')
        self.stats_observed.setFont(QFont('Segoe UI', 12))
        self.stats_observed.setProperty('class', 'muted')
        self.stats_observed.setWordWrap(True)
        self.stats_layout.addWidget(self.stats_observed)
        self.stats_layout.addStretch()

    # ── Utilities ─────────────────────────────────────────────────────

    def work(self, fn, done, mutation=False):
        if mutation and self.busy:
            return
        if mutation:
            self.busy = True
            self.add_button.setEnabled(False)
            self.pool_button.setEnabled(False)
            self.set_policy_controls_enabled(False)
        worker = Worker(fn)
        self._workers.add(worker)
        def on_finished(result, error):
            self._workers.discard(worker)
            if self.closed:
                return
            if mutation:
                self.busy = False
                self.add_button.setEnabled(not self.pending_login)
                self.pool_button.setEnabled(True)
                self.set_policy_controls_enabled(True)
            if error:
                msg = str(error) if isinstance(error, AccountError) else tr('action_generic_error')
                self.show_notice(msg, 'warning')
                self.service.setText(tr('status_attention'))
                self.set_label_color(self.service, 'warning')
            else:
                done(result)
        worker.signals.finished.connect(on_finished, Qt.QueuedConnection)
        QThreadPool.globalInstance().start(worker)

    def show_notice(self, text, style='green'):
        self.notice.setText(text)
        color_key = {'green': 'green', 'warning': 'warning', 'accent': 'accent', 'warn': 'warn_text'}.get(style, 'green')
        self.set_label_color(self.notice, color_key)

    @staticmethod
    def set_label_color(label, role):
        label.setStyleSheet('')
        label.setProperty('class', 'warn' if role == 'warn_text' else role)
        label.style().unpolish(label)
        label.style().polish(label)

    def display_name(self, account):
        if self.controller.preferences.get('hide-account-names'):
            ident = hashlib.sha256(account['name'].encode()).hexdigest()[:6]
            return tr('private_account', id=ident)
        return (self.controller.preferences.get('labels', {}).get(account['name'])
                or account.get('email') or tr('google_account'))

    @staticmethod
    def activity_time(value):
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone().strftime('%d.%m %H:%M:%S')
        except (ValueError, AttributeError):
            return '—'

    @staticmethod
    def time_until_reset(value, now=None, days_only=False):
        try:
            reset = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if not reset.tzinfo:
                return '—'
            seconds = (reset - (now or datetime.now(timezone.utc))).total_seconds()
        except (ValueError, AttributeError):
            return '—'
        day, hour, minute = tr('unit_day'), tr('unit_hour'), tr('unit_minute')
        if days_only:
            return '0' + day if seconds <= 0 else '< 1' + day if seconds < 86400 else f'{int(seconds // 86400)}{day}'
        if seconds <= 0:
            return '0' + minute
        if seconds < 60:
            return '< 1' + minute
        minutes = int(seconds // 60)
        days, minutes = divmod(minutes, 1440)
        hours, minutes = divmod(minutes, 60)
        if days:
            return f'{days}{day} {hours}{hour}'
        if hours:
            return f'{hours}{hour} {minutes}{minute}'
        return f'{minutes}{minute}'

    @staticmethod
    def quota_percent(remaining):
        if remaining is None:
            return '—'
        if 0 < remaining < .001:
            return '<0,1%'
        return f'{remaining * 100:.1f}'.replace('.', ',') + '%'

    def quota_color(self, remaining):
        t = self.theme.colors()
        if remaining is None:
            return t['muted']
        if remaining > .3:
            return t['green']
        if remaining > .1:
            return t['warn_text']
        return t['error']

    @staticmethod
    def reset_color(value, now=None, bounds=None, theme_name='dark'):
        try:
            moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
            seconds = (moment - (now or datetime.now(timezone.utc))).total_seconds()
        except (ValueError, TypeError, AttributeError):
            return THEMES[theme_name]['muted']
        if seconds <= 0:
            return THEMES[theme_name]['green_dim']
        minimum, maximum = bounds or (0, 7 * 86400)
        ratio = min(1, max(0, (seconds - minimum) / (maximum - minimum))) if maximum > minimum else .5
        green, amber, red = ((22, 116, 88), (148, 101, 15), (184, 50, 69)) if theme_name == 'light' else ((102, 226, 167), (245, 197, 107), (255, 68, 85))
        if ratio <= .5:
            start, end, frac = green, amber, ratio * 2
        else:
            start, end, frac = amber, red, (ratio - .5) * 2
        return '#' + ''.join(f'{round(a + (b - a) * frac):02x}' for a, b in zip(start, end))

    @staticmethod
    def model_family(model):
        if model == 'claude-sonnet-4-5' or model.startswith('gemini'):
            return 'gemini'
        if model.startswith(('claude', 'gpt', 'o1', 'o3', 'o4')):
            return 'claude'
        return None

    @staticmethod
    def quota_wait_text(waiting, now=None):
        now = time.time() if now is None else now
        resets = {}
        for job in waiting:
            family = App.model_family(job.get('upstream_model') or job.get('model', ''))
            if family:
                resets[family] = min(resets.get(family, float('inf')), job['retry_at'])
        labels = []
        for family, title in (('claude', 'Claude'), ('gemini', 'Gemini')):
            if family in resets:
                minutes = math.ceil(max(0, resets[family] - now) / 60)
                duration = f'{minutes // 60}h {minutes % 60:02}m' if minutes >= 60 else f'{minutes}m'
                labels.append(f'until {title} · {duration}')
        return '  /  '.join(labels) or 'Waiting'

    # ── Details toggle ────────────────────────────────────────────────

    def toggle_details(self):
        self.set_compact_mode(not self.details_collapsed)

    def set_compact_mode(self, collapsed, on_top=False):
        if not collapsed:
            self.body_container.setVisible(True)
            self.sidebar.setFixedWidth(SIDEBAR_WIDTH)
            self.setMinimumSize(990, 680)
            self.resize(self._expanded_size)
        else:
            if not self.details_collapsed:
                self._expanded_size = self.size()
            self.body_container.setVisible(False)
            self.sidebar.setMaximumWidth(16777215)
            self.sidebar.setMinimumWidth(SIDEBAR_WIDTH)
            self.setMinimumSize(SIDEBAR_WIDTH, 500)
            self.resize(SIDEBAR_WIDTH, max(500, self.height()))
        self.details_collapsed = collapsed
        self.is_mini = collapsed and on_top
        if bool(self.windowFlags() & Qt.WindowStaysOnTopHint) != self.is_mini:
            visible = self.isVisible()
            self.setWindowFlag(Qt.WindowStaysOnTopHint, self.is_mini)
            if visible:
                self.show()
        self.btn_mini.setText(tr('btn_full_mode') if collapsed else tr('btn_mini_mode'))
        self.controller.preferences['details-collapsed'] = self.details_collapsed
        self.controller.save()
        self.draw_account_list()

    # ── View switching ────────────────────────────────────────────────

    def change_view(self, value):
        views = [tr('tab_account_quotas'), tr('tab_routing_stats'), tr('tab_api_keys'), tr('tab_chatgpt'),
                 tr('tab_claude_accounts'), tr('team_tab')]
        self.view_stack.setCurrentIndex(views.index(value))
        if self.view_stack.currentIndex() == 2:
            self.render_api_profiles()
            self.poll_api_stats()
        elif self.view_stack.currentIndex() == 3:
            self.render_chatgpt_accounts()
            self.refresh_chatgpt_accounts()
        elif self.view_stack.currentIndex() == 4:
            self.claude_accounts_panel.render()
            self.claude_accounts_panel.refresh()
        elif self.view_stack.currentIndex() == 5:
            self.team_panel.render()
            self.team_panel.refresh()
    def render_api_profiles(self):
        rows = api_keys.profiles(self.controller)
        signature = (repr(rows), current_language(), self.theme.current)
        if signature == getattr(self, '_api_drawn', None):
            for row in rows:
                self._api_metrics[row['id']].setText(self.api_metrics_text(row))
            return
        self._api_drawn = signature
        self._api_metrics = {}
        layout = self.api_cards_layout
        while layout.count():
            widget = layout.takeAt(0).widget()
            if widget:
                widget.hide()
                widget.deleteLater()
        if not rows:
            empty = QLabel(tr('api_empty'))
            empty.setWordWrap(True)
            layout.addWidget(empty)
        for row in rows:
            card = QFrame()
            card.setObjectName('apiCard')
            card.setFrameShape(QFrame.StyledPanel)
            cl = QVBoxLayout(card)
            title = QLabel(row['label'] + ' · ' + tr('api_enabled' if row.get('enabled', True) else 'api_disabled'))
            title.setFont(QFont('Segoe UI', 14, QFont.Bold))
            title.setTextFormat(Qt.PlainText)
            title.setWordWrap(True)
            cl.addWidget(title)
            address = QLabel(row['base_url'])
            address.setTextFormat(Qt.PlainText)
            address.setWordWrap(True)
            address.setProperty('class', 'muted')
            cl.addWidget(address)
            models = QLabel('\n'.join('API · ' + model_name(model, {}) for model in row['models']))
            models.setTextFormat(Qt.PlainText)
            models.setWordWrap(True)
            cl.addWidget(models)
            metrics = QLabel(self.api_metrics_text(row))
            self._api_metrics[row['id']] = metrics
            metrics.setTextFormat(Qt.PlainText)
            metrics.setWordWrap(True)
            cl.addWidget(metrics)
            buttons = QHBoxLayout()
            for key, callback in (
                ('api_edit', lambda checked=False, row=row: self.edit_api_profile(row)),
                ('api_pause' if row.get('enabled', True) else 'api_resume', lambda checked=False, row=row: self.toggle_api_profile(row)),
                ('api_remove', lambda checked=False, row=row: self.remove_api_profile(row))):
                button = QPushButton(tr(key))
                button.clicked.connect(callback)
                buttons.addWidget(button)
            cl.addLayout(buttons)
            layout.addWidget(card)

    def api_metrics_text(self, row):
        stats = self.api_stats.get(row['id'], {})
        count = stats.get('success', 0) + stats.get('failed', 0)
        text = tr('api_stats', success=stats.get('success', 0), failed=stats.get('failed', 0),
                  input=f"{stats.get('input_tokens', 0):,}", output=f"{stats.get('output_tokens', 0):,}",
                  seconds=f"{stats.get('latency_ms', 0) / max(count, 1) / 1000:.1f}")
        if stats.get('last_at'):
            text += '\n' + tr('api_last', model=model_name(stats['last_model'], {}),
                              status=stats['last_status'], time=self.activity_time(stats['last_at']))
        if stats.get('exhausted'):
            text += '\n' + tr('api_exhausted')
        elif stats.get('unavailable'):
            text += '\n' + tr('api_unavailable')
        elif stats.get('failure') == 'rate_limited':
            text += '\n' + tr('api_rate_limited')
        retry_at = max((b.get('retry_at', 0) for b in stats.get('cooldowns', {}).values()), default=0)
        if retry_at > time.time():
            text += '\n' + tr('api_retry_at', time=time.strftime('%H:%M:%S', time.localtime(retry_at)))
        return text

    def poll_api_stats(self):
        if self.closed or self.api_stats_busy or self.view_stack.currentIndex() != 2:
            return
        self.api_stats_busy = True
        def done(stats):
            self.api_stats_busy = False
            if stats is not None:
                self.api_stats = stats
                self.render_api_profiles()
        self.work(self.controller.api_key_status, done)

    def api_profiles_changed(self):
        self.render_api_profiles()
        self.work(self.integrations.refresh_desktop_model_labels,
                  lambda _: self.show_notice(tr('api_saved')))

    def toggle_api_profile(self, row):
        api_keys.save_profile(self.controller, dict(row, enabled=not row.get('enabled', True)))
        self.api_profiles_changed()

    def remove_api_profile(self, row):
        if QMessageBox.question(self, tr('api_remove'), tr('api_remove_confirm', name=row['label'])) != QMessageBox.Yes:
            return
        api_keys.remove_profile(self.controller, row['id'])
        self.api_profiles_changed()

    def edit_api_profile(self, row=None):
        row = row or {}
        dialog = QDialog(self)
        dialog.setWindowTitle(tr('api_edit') if row else tr('api_add'))
        dialog.setMinimumWidth(520)
        layout = QVBoxLayout(dialog)
        fields = QGridLayout()
        label = QLineEdit(row.get('label', ''))
        label.setObjectName('apiLabelInput')
        kind = ThemedComboBox()
        kind.setObjectName('apiProviderInput')
        kind.addItem('TokenHarbor', 'tokenharbor')
        kind.addItem(tr('api_anthropic'), 'anthropic')
        kind.addItem('Flua · Anthropic', 'flua')
        preset = 'flua' if row.get('base_url', '').rstrip('/').removesuffix('/v1') == 'https://api.flua.ink' else row.get('kind', 'tokenharbor')
        kind.setCurrentIndex(max(0, kind.findData(preset)))
        base = QLineEdit(row.get('base_url', 'https://tokenharbor.ai'))
        base.setObjectName('apiUrlInput')
        key = QLineEdit()
        key.setObjectName('apiKeyInput')
        key.setEchoMode(QLineEdit.Password)
        key.setPlaceholderText(tr('api_key_keep') if row else tr('api_key'))
        models = QTextEdit()
        models.setPlainText('\n'.join(row.get('models', ['claude-haiku-5.5:free'])))
        models.setObjectName('apiModelsInput')
        models.setAcceptRichText(False)
        models.setMaximumHeight(95)
        def provider_changed():
            defaults = {'tokenharbor': ('https://tokenharbor.ai', 'claude-haiku-5.5:free'),
                        'anthropic': ('https://api.anthropic.com', ''),
                        'flua': ('https://api.flua.ink', 'claude-opus-5-5')}
            url, model = defaults[kind.currentData()]
            if not base.text().strip() or base.text().rstrip('/') in {item[0] for item in defaults.values()}:
                base.setText(url)
            if not row and models.toPlainText().strip() in {item[1] for item in defaults.values()}:
                models.setPlainText(model)
        kind.currentIndexChanged.connect(provider_changed)
        for index, (caption, widget) in enumerate((('api_label', label), ('api_provider', kind),
                                                  ('api_url', base), ('api_key', key), ('api_models', models))):
            fields.addWidget(QLabel(tr(caption)), index, 0)
            fields.addWidget(widget, index, 1)
        fields.setColumnStretch(1, 1)
        layout.addLayout(fields)
        enabled = QCheckBox(tr('api_enabled'))
        enabled.setChecked(row.get('enabled', True))
        layout.addWidget(enabled)
        rotate = QCheckBox(tr('api_rotate'))
        rotate.setObjectName('apiRotateInput')
        rotate.setChecked(row.get('rotate', True))
        rotate.setToolTip(tr('api_rotate_hint'))
        layout.addWidget(rotate)
        load = QPushButton(tr('api_load_models'))
        layout.addWidget(load)
        check = QPushButton(tr('api_check'))
        check.setObjectName('apiCheckButton')
        layout.addWidget(check)
        check_on_save = QCheckBox(tr('api_check_on_save'))
        check_on_save.setChecked(True)
        layout.addWidget(check_on_save)
        check_hint = QLabel(tr('api_check_hint'))
        check_hint.setWordWrap(True)
        check_hint.setProperty('class', 'muted')
        layout.addWidget(check_hint)
        message = QLabel('')
        message.setWordWrap(True)
        layout.addWidget(message)
        closed = [False]
        dialog.finished.connect(lambda _: closed.__setitem__(0, True))
        def values():
            return dict(row, label=label.text(), kind='anthropic' if kind.currentData() == 'flua' else kind.currentData(), base_url=base.text(),
                        key=key.text().strip(), models=models.toPlainText().replace(',', '\n').splitlines(), enabled=enabled.isChecked(), rotate=rotate.isChecked())
        def fetch():
            value = values()
            try:
                value['key'] = api_keys.profile_key(self.controller, value)
            except (AccountError, ValueError) as error:
                message.setText(str(error))
                return
            # Validate the URL before sending a credential; do not persist edits yet.
            from urllib.parse import urlsplit
            url = urlsplit(value['base_url'])
            if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment or not value['key']:
                message.setText(tr('api_invalid'))
                return
            load.setEnabled(False)
            message.setText(tr('api_loading'))
            def operation():
                try:
                    return api_keys.fetch_models(value), None
                except Exception:
                    return [], tr('api_load_error')
            def loaded(result):
                if closed[0]:
                    return
                load.setEnabled(True)
                choices, error = result
                message.setText(error or '')
                if choices:
                    chosen, accepted = QInputDialog.getItem(dialog, tr('api_models'), tr('api_choose_model'), choices, 0, False)
                    if accepted and chosen not in models.toPlainText().splitlines():
                        models.append(chosen)
            self.work(operation, loaded)
        load.clicked.connect(fetch)
        save = QPushButton(tr('api_save'))
        save.setObjectName('apiSaveButton')
        layout.addWidget(save)
        def persist(value):
            api_keys.save_profile(self.controller, value)
            dialog.accept()
            self.api_profiles_changed()
        def verify(saving=False):
            try:
                value = api_keys.validated_profile(self.controller, values())
            except (AccountError, ValueError) as error:
                message.setText(str(error))
                return
            controls = [label, kind, base, key, models, enabled, rotate, load, check, check_on_save, save]
            for control in controls:
                control.setEnabled(False)
            message.setText(tr('api_checking'))
            def operation():
                try:
                    return api_keys.verify_profile(self.controller, value), None
                except AccountError as error:
                    return None, str(error)
            def done(result):
                if closed[0]:
                    return
                for control in controls:
                    control.setEnabled(True)
                checked, error = result
                if error:
                    message.setText(tr('api_check_failed', error=error))
                elif saving:
                    persist(value)
                else:
                    message.setText(tr('api_check_ok', model=checked['model']))
            self.work(operation, done)
        def apply():
            try:
                value = api_keys.validated_profile(self.controller, values())
            except (AccountError, ValueError) as error:
                message.setText(str(error))
                return
            old = next((p for p in api_keys.profiles(self.controller, private=True) if p['id'] == row.get('id')), {})
            changed = any(value.get(k) != old.get(k) for k in ('key', 'kind', 'base_url', 'models'))
            if changed and check_on_save.isChecked():
                verify(saving=True)
            else:
                persist(value)
        check.clicked.connect(lambda: verify())
        save.clicked.connect(apply)
        self.theme.apply(dialog)
        dialog.exec()

    # ── Data loading ──────────────────────────────────────────────────

    def refresh(self, prepare=False):
        if self.busy:
            return
        for cached in self.quota_cache.values():
            cached['checked'] = 0
        def load():
            if prepare or not self.controller.key:
                self.controller.prepare()
            self.integrations.reconcile_desktop_routes()
            return self.controller.accounts()
        self.work(load, self.loaded, mutation=True)

    def loaded(self, items):
        if items and (self.controller.data_dir / 'installation.json').exists() and not self.controller.preferences.get('connections-offered'):
            self.controller.preferences['connections-offered'] = True
            self.controller.save()
            QTimer.singleShot(500, self.connection_settings)
        self.items = items
        self.account_uptime.update_many('antigravity', items)
        self.check_account_alerts()
        self.service.setText(tr('status_connected'))
        self.set_label_color(self.service, 'green')
        if self.selected not in {a['name'] for a in items}:
            self.selected = items[0]['name'] if items else None
        enabled = [a for a in items if not a['disabled']]
        if not enabled:
            mode = tr('mode_no_accounts')
        elif len(enabled) == len(items) and self.controller.preferences.get('mode') != 'single':
            mode = tr('mode_auto_routing', count=len(enabled))
        elif len(enabled) == 1:
            mode = tr('mode_for_claude', name=self.display_name(enabled[0]))
        else:
            mode = tr('mode_enabled_of', enabled=len(enabled), total=len(items))
        self.mode_label.setText(mode)
        self.draw_account_list()
        if self.detail_account != self.selected:
            self.draw_detail()
        else:
            self.update_detail_account()
        for account in items:
            self.fetch_quota(account['name'])
        self.queue_policy()
        if not self.activity_started:
            self.activity_started = True
            self.start_activity()

    # ── Account list ──────────────────────────────────────────────────

    def draw_account_list(self):
        self.update_total_quota()
        accounts = sorted(self.items, key=self.account_sort_key)
        names = [a['name'] for a in accounts]
        pending_count = sum(1 for a in accounts if a.get('access_issue') == 'verification')
        depleted_count = sum(a.get('access_issue') != 'verification' and self.account_weekly_depleted(a['name']) for a in accounts)
        ready_count = len(accounts) - pending_count - depleted_count
        signature = (current_language(), self.theme.current, tuple(
            (a['name'], a.get('access_issue'), self.account_connection_issue(a),
             self.account_weekly_depleted(a['name']), tuple((g['kind'], b['window'])
             for g in self.quota_groups(a['name']) for b in self.visible_quota_buckets(g))) for a in sorted(accounts, key=lambda a: a['name'])))
        if signature == getattr(self, '_account_structure', None) and len(self.account_widgets) == len(accounts):
            positions = sorted(self.account_list_layout.indexOf(card) for card in self.account_widgets.values())
            for position, account in zip(positions, accounts):
                self.account_list_layout.insertWidget(position, self.account_widgets[account['name']])
                self.refresh_account_card(account)
            return
        self._account_structure = signature

        # Clear existing widgets
        while self.account_list_layout.count() > 1:
            item = self.account_list_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self.account_widgets = {}

        t = self.theme.colors()
        for index, account in enumerate(accounts):
            section = None
            if pending_count and index == 0:
                section = (tr('group_verification_required', count=pending_count), True)
            elif ready_count and index == pending_count and (pending_count or depleted_count):
                section = (tr('group_other_accounts', count=ready_count), False)
            elif depleted_count and index == pending_count + ready_count:
                threshold = weekly_threshold(self.controller.preferences) * 100
                section = (tr('group_weekly_empty', count=depleted_count) if threshold == 0 else
                           tr('group_weekly_depleted', count=depleted_count, percent=f'{threshold:g}'), True)
            if section:
                if index:
                    sep = QFrame()
                    sep.setFixedHeight(1)
                    sep.setStyleSheet(f'background-color: {t["separator"]};')
                    self.account_list_layout.insertWidget(self.account_list_layout.count() - 1, sep)
                title, pending = section
                group_label = QLabel(title)
                group_label.setFont(QFont('Segoe UI', 11, QFont.Bold))
                group_label.setStyleSheet(f'color: {t["warn_text"] if pending else t["muted"]};')
                self.account_list_layout.insertWidget(self.account_list_layout.count() - 1, group_label)

            name = account['name']
            card = AccountCard(name)
            self.configure_priority_control(card.priority_control, name, 'google')
            card.set_heading(self.account_heading(account))
            plan = self.quota_cache.get(name, {}).get('data', {}).get('subscription')
            if plan:
                card.set_heading(self.account_heading(account) + ' · ' + plan)
            selected = not self.details_collapsed and name == self.selected
            card.set_selected(selected, t)
            card.clicked.connect(self.select_account)
            card.remove_button.setToolTip(tr('tip_remove'))
            card.remove_requested.connect(self.remove_account)
            card.setToolTip(self.account_tooltip(account))
            cached_quota = self.quota_is_cached(account)
            if account.get('access_issue') or self.account_connection_issue(account) or blocked_families(self.controller.preferences, name, self.quota_groups(name)):
                status = self.account_status_text(account)
                if cached_quota:
                    status += '\n' + tr('account_cached_quota')
            else:
                status = tr('account_cached_quota') if cached_quota else ''
            card.status_label.setText(status)
            card.status_label.setVisible(bool(status))
            uptime_text = self.uptime_text('antigravity', name)
            card.uptime_label.setText(uptime_text)
            card.uptime_label.setVisible(bool(uptime_text))

            # Quota rows in card
            groups = self.quota_groups(name)
            for group in groups:
                for bucket in sorted(self.visible_quota_buckets(group), key=lambda b: b['window'] != '5h'):
                    remaining = bucket.get('remaining')
                    text = self.sidebar_quota_text(group, bucket)
                    qrow = QuotaRowWidget(group['kind'], bucket['window'])
                    self.bind_reserve_bar(qrow.bar, name, 'google', group['kind'], bucket['window'])
                    countdown_text = self.time_until_reset(
                        bucket.get('reset'), days_only=bucket['window'] == 'weekly')
                    bounds = {'5h': (0, 5 * 3600), 'weekly': (0, 7 * 86400)}
                    cd_color = self.reset_color(bucket.get('reset'), bounds=bounds[bucket['window']], theme_name=self.theme.current)
                    q_color = t['muted'] if cached_quota else self.quota_color(remaining)
                    if cached_quota:
                        cd_color = t['muted']
                    qrow.update_data(text, remaining, countdown_text, cd_color, q_color)
                    card.quota_layout.addWidget(qrow)
                    card.quota_rows[(group['kind'], bucket['window'])] = qrow
                    card.countdown_labels[(group['kind'], bucket['window'])] = qrow.countdown

            # Verification buttons
            if account.get('access_issue') == 'verification':
                v_btn = QPushButton(tr('btn_verify'))
                v_btn.setToolTip(tr('tip_verify'))
                v_btn.setFixedHeight(24)
                v_btn.clicked.connect(lambda checked, n=name: self.open_verification(n))
                card.verification_layout.addWidget(v_btn)
                refresh_btn = QPushButton('↻')
                refresh_btn.setToolTip(tr('tip_refresh_link'))
                refresh_btn.setFixedSize(26, 24)
                refresh_btn.setFont(QFont('Segoe UI', 16))
                refresh_btn.clicked.connect(lambda checked, n=name: self.refresh_verification_link(n))
                card.verification_layout.addWidget(refresh_btn)
                copy_btn = QPushButton('⧉')
                copy_btn.setToolTip(tr('tip_copy_link'))
                copy_btn.setFixedSize(26, 24)
                copy_btn.clicked.connect(lambda checked, n=name: self.copy_verification_link(n))
                card.verification_layout.addWidget(copy_btn)
                retry_btn = QPushButton(tr('btn_i_verified'))
                retry_btn.setToolTip(tr('tip_i_verified'))
                retry_btn.setFixedHeight(24)
                retry_btn.clicked.connect(lambda checked, n=name: self.retry_verification(n))
                card.verification_layout.addWidget(retry_btn)
                card.verification_frame.setVisible(True)

            self.account_widgets[name] = card
            self.account_list_layout.insertWidget(self.account_list_layout.count() - 1, card)

    def refresh_account_card(self, account):
        card = self.account_widgets[account['name']]
        card.priority_control.set_value(account_priority(self.controller.preferences, account['name']))
        t = self.theme.colors()
        plan = self.quota_cache.get(account['name'], {}).get('data', {}).get('subscription')
        card.set_heading(self.account_heading(account) + (' · ' + plan if plan else ''))
        card.set_selected(not self.details_collapsed and account['name'] == self.selected, t)
        card.setToolTip(self.account_tooltip(account))
        cached = self.quota_is_cached(account)
        status = self.account_status_text(account) if account.get('access_issue') or self.account_connection_issue(account) or blocked_families(self.controller.preferences, account['name'], self.quota_groups(account['name'])) else ''
        if cached:
            status += ('\n' if status else '') + tr('account_cached_quota')
        card.status_label.setText(status)
        card.status_label.setVisible(bool(status))
        uptime_text = self.uptime_text('antigravity', account['name'])
        card.uptime_label.setText(uptime_text)
        card.uptime_label.setVisible(bool(uptime_text))
        for group in self.quota_groups(account['name']):
            for bucket in self.visible_quota_buckets(group):
                row = card.quota_rows[(group['kind'], bucket['window'])]
                row.bar.set_floor(quota_floor(self.controller.preferences, account['name'], group['kind'], bucket['window']))
                bounds = (0, 5 * 3600) if bucket['window'] == '5h' else (0, 7 * 86400)
                cd_color = t['muted'] if cached else self.reset_color(bucket.get('reset'), bounds=bounds, theme_name=self.theme.current)
                color = t['muted'] if cached else self.quota_color(bucket.get('remaining'))
                row.update_data(self.sidebar_quota_text(group, bucket), bucket.get('remaining'),
                    self.time_until_reset(bucket.get('reset'), days_only=bucket['window'] == 'weekly'), cd_color, color)

    def account_heading(self, account):
        marker = '!' if account.get('access_issue') or self.account_connection_issue(account) else 'Ⅱ' if account.get('disabled') else '●'
        return marker + '  ' + self.display_name(account)

    def account_weekly_depleted(self, name):
        gemini = next((group for group in self.quota_groups(name) if group['kind'] == 'gemini'), {})
        weekly = next((bucket.get('remaining') for bucket in gemini.get('buckets', []) if bucket['window'] == 'weekly'), None)
        return weekly_depleted(weekly, weekly_threshold(self.controller.preferences))

    def account_sort_key(self, account):
        if account.get('access_issue') == 'verification':
            return (0, 0)
        row = rank_accounts([account], self.quota_cache, self.target_policy_group(),
                            preferences=self.controller.preferences)
        tier = 4 if account.get('disabled') else (row[0]['tier'] if row else 2)
        return (2 if self.account_weekly_depleted(account['name']) else 1,
                0 if tier <= 1 else tier, -account_priority(self.controller.preferences, account['name']),
                self.account_reset_order(account['name']))

    def visible_quota_buckets(self, group):
        weekly = next((bucket.get('remaining') for bucket in group['buckets'] if bucket['window'] == 'weekly'), None)
        hide = weekly_depleted(weekly, weekly_threshold(self.controller.preferences))
        return [bucket for bucket in group['buckets'] if not (hide and bucket['window'] == '5h')]

    @staticmethod
    def account_connection_issue(account):
        return account.get('access_issue') == 'login' or (
            account.get('status') == 'error' and not account.get('restriction_reason'))

    def account_status_text(self, account):
        issue = account.get('access_issue')
        if issue in ('verification', 'login', 'denied'):
            return tr({'verification': 'account_verification_required',
                       'login': 'account_sign_in_again', 'denied': 'account_denied'}[issue])
        if account.get('disabled'):
            return tr('account_paused')
        reserved = blocked_families(self.controller.preferences, account['name'], self.quota_groups(account['name']))
        if reserved:
            return tr('Quota reserve reached') + ' · ' + ' / '.join('Gemini' if kind == 'gemini' else 'Claude' for kind in sorted(reserved))
        if self.account_connection_issue(account):
            return tr('account_connection_error')
        return tr('account_enabled_status')

    def uptime_text(self, provider, name):
        value = self.account_uptime.display(provider, name)
        if not value:
            return ''
        minutes = max(0, int(value['seconds'] // 60))
        days, hours, minutes = minutes // 1440, minutes // 60 % 24, minutes % 60
        duration = (f"{days}{tr('unit_day')} {hours}{tr('unit_hour')}" if days else
                    f"{hours}{tr('unit_hour')} {minutes:02}{tr('unit_minute')}")
        if value['running']:
            return tr('uptime_valid', time=duration)
        if value.get('confirmed_auth_loss'):
            return tr('uptime_stopped', time=duration)
        return tr('uptime_unknown')

    def check_account_alerts(self):
        settings = self.controller.preferences.get('notifications', {})
        if not isinstance(settings, dict):
            settings = {}
        events = []
        providers = [
            ('antigravity', 'Google', self.items),
            ('codex', 'ChatGPT', self.chatgpt_accounts),
            ('claude', 'Claude', self.claude_accounts_panel.rows if hasattr(self, 'claude_accounts_panel') else []),
        ]
        for provider, title, accounts in providers:
            for account in accounts or []:
                name = account.get('name')
                if not name:
                    continue
                groups = []
                if provider == 'antigravity':
                    cached = self.quota_cache.get(name, {})
                    if cached.get('data') and not self.quota_is_cached(account):
                        groups = cached['data'].get('groups', [])
                elif provider in ('codex', 'claude'):
                    quota = account.get('quota') or {}
                    if not quota.get('error'):
                        groups = oauth_quota_groups(quota, provider)
                auth_lost, reached = account_alert_conditions(account, groups, self.controller.preferences)
                if self.alert_tracker.transition('auth:' + provider + ':' + name, auth_lost):
                    if settings.get('auth-required', True):
                        events.append(tr('alert_auth_body', name=self.display_name(account)))
                for kind, window, floor_percent in reached:
                    key = f'quota:{provider}:{name}:{kind}:{window}'
                    if self.alert_tracker.transition(key, True) and settings.get('quota-reserve', True):
                        window_label = tr('period_5h') if window == '5h' else tr('period_weekly')
                        family_names = {'gemini': 'Gemini', 'claude': 'Claude / GPT', 'openai': 'ChatGPT',
                                        'claude-opus': 'Claude Opus', 'claude-sonnet': 'Claude Sonnet'}
                        events.append(tr('alert_quota_body', name=self.display_name(account),
                                         service=family_names.get(kind, title), window=window_label, floor=floor_percent))
                # Clear reserve transitions only when fresh quota data was available.
                fresh_quota = (provider == 'antigravity' and bool(groups) or
                               provider in ('codex', 'claude') and bool(groups))
                if fresh_quota:
                    active_quota_keys = {f'quota:{provider}:{name}:{kind}:{window}'
                                         for kind, window, _ in reached}
                    for group in groups:
                        kind = group.get('kind')
                        for bucket in group.get('buckets', []):
                            window, remaining = bucket.get('window'), bucket.get('remaining')
                            if (not kind or not window or isinstance(remaining, bool) or
                                    not isinstance(remaining, (int, float)) or not math.isfinite(remaining) or
                                    not 0 <= remaining <= 1):
                                continue
                            key = f'quota:{provider}:{name}:{kind}:{window}'
                            if key not in active_quota_keys:
                                self.alert_tracker.transition(key, False)
        if events and QSystemTrayIcon.isSystemTrayAvailable() and hasattr(self, 'tray_icon'):
            lines = events[:3]
            if len(events) > 3:
                lines.append(tr('alert_more', count=len(events) - 3))
            self.tray_icon.showMessage(tr('alert_title'), '\n'.join(lines),
                                       QSystemTrayIcon.Warning, 7000)

    def quota_is_cached(self, account):
        cached = self.quota_cache.get(account['name'], {})
        if not cached.get('data', {}).get('groups'):
            return False
        if cached.get('error') or cached.get('data', {}).get('summary_error') or self.account_connection_issue(account):
            return True
        at = cached.get('at')
        return at is not None and (datetime.now(timezone.utc) - at).total_seconds() > 180

    def account_tooltip(self, account):
        parts = [self.account_status_text(account), tr('account_quota_hint')]
        cached = self.quota_cache.get(account['name'], {})
        if cached.get('at'):
            parts.append(tr('quota_updated_at', time=cached['at'].strftime('%H:%M:%S')))
        if self.quota_is_cached(account):
            parts.append(tr('quota_cached_data'))
        error = cached.get('error') or cached.get('data', {}).get('summary_error')
        if error:
            parts.append(display_reason(error))
        for probe in self.google_startup_probes.get(account['name'], []):
            state = self.controller.quota_starts.get(account['name'] + ':' + probe['kind'], {})
            if probe['status'] != 200:
                message = tr('google_startup_failed', status=probe['status'])
            else:
                message = tr('google_startup_confirmed' if state.get('weekly_started') is True else 'google_startup_unconfirmed')
            parts.append(('Gemini' if probe['kind'] == 'gemini' else 'Claude / GPT') + ': ' + message)
        last_model = self.last_account_model(account['name'])
        if last_model:
            parts.append(last_model)
        return '\n'.join(parts)

    def account_reset_order(self, name):
        resets = []
        window = 'weekly' if self.account_weekly_depleted(name) else '5h'
        for group in self.quota_groups(name):
            if group.get('kind') != 'gemini':
                continue
            for bucket in group['buckets']:
                if bucket.get('window') != window:
                    continue
                try:
                    reset = datetime.fromisoformat(bucket['reset'].replace('Z', '+00:00'))
                    if reset.tzinfo:
                        resets.append(reset.timestamp())
                except (KeyError, ValueError, TypeError, AttributeError):
                    pass
        return min(resets, default=float('inf'))

    def sidebar_account_status(self, account):
        label, severity, detail = google_account_status(account, self.quota_groups(account['name']))
        status = tr(label)
        last = max(self.activity_state['latest'].values(), key=lambda e: e['at'], default=None)
        if label == 'Available' and last and last['name'] == account['name'] and not account['disabled']:
            try:
                moment = datetime.fromisoformat(last['at'].replace('Z', '+00:00')).astimezone()
                status = tr('account_last_response', time=moment.strftime('%H:%M:%S'))
            except (ValueError, TypeError):
                pass
        if account.get('access_issue') == 'verification':
            status = tr('account_verification_required')
        elif account.get('access_issue') == 'login':
            status = tr('account_sign_in_again')
        elif account.get('access_issue') == 'denied':
            status = tr('account_denied')
        return status + ' · ' + tr('account_responses', count=account.get('success') or 0)

    @staticmethod
    def sidebar_quota_text(group, bucket):
        period = tr('period_weekly') if bucket['window'] == 'weekly' else tr('period_5h')
        remaining = bucket.get('remaining')
        return period + ' · ' + App.quota_percent(remaining)

    def select_account(self, name):
        if self.details_collapsed:
            return
        self.selected = name
        self.loaded(self.items)

    # ── Detail view ───────────────────────────────────────────────────

    def draw_detail(self):
        # Clear existing content
        while self.detail_layout.count() > 1:
            item = self.detail_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self.detail_account = self.selected
        self.detail_quota_widgets = {}
        self.model_widgets = {}
        self.drawn_models = None

        account = next((a for a in self.items if a['name'] == self.selected), None)
        if not account:
            heading = QLabel(tr('detail_add_first'))
            heading.setFont(QFont('Segoe UI', 22, QFont.Bold))
            self.detail_layout.insertWidget(0, heading)
            hint = QLabel(tr('detail_add_hint'))
            hint.setProperty('class', 'muted')
            hint.setWordWrap(True)
            self.detail_layout.insertWidget(1, hint)
            return

        pos = 0
        def add(widget):
            nonlocal pos
            self.detail_layout.insertWidget(pos, widget)
            pos += 1

        self.detail_heading = QLabel(self.display_name(account))
        self.detail_heading.setFont(QFont('Segoe UI', 22, QFont.Bold))
        add(self.detail_heading)

        if not self.controller.preferences.get('hide-account-names') and self.display_name(account) != account.get('email') and account.get('email'):
            email_label = QLabel(account['email'])
            email_label.setProperty('class', 'muted')
            add(email_label)

        status = tr('detail_paused') if account['disabled'] else tr('detail_enabled')
        self.detail_status = QLabel(status)
        self.detail_status.setProperty('class', 'muted')
        add(self.detail_status)

        quota_heading = QLabel(tr('detail_remaining_quota'))
        quota_heading.setFont(QFont('Segoe UI', 17, QFont.Bold))
        quota_heading.setContentsMargins(0, 8, 0, 0)
        add(quota_heading)

        self.quota_updated = QLabel(tr('detail_loading_quotas'))
        self.quota_updated.setFont(QFont('Segoe UI', 12))
        self.quota_updated.setProperty('class', 'muted')
        add(self.quota_updated)

        for group in self.quota_groups(account['name']):
            group_label = QLabel(group['name'])
            group_label.setFont(QFont('Segoe UI', 15, QFont.Bold))
            add(group_label)
            for bucket in sorted(group['buckets'], key=lambda b: b['window'] != '5h'):
                title = tr('detail_weekly_quota') if bucket['window'] == 'weekly' else tr('detail_5h_quota')
                row = DetailQuotaRow(title)
                self.bind_reserve_bar(row.bar, account['name'], 'google', group['kind'], bucket['window'])
                remaining = bucket.get('remaining')
                color = self.quota_color(remaining)
                value_text = tr('quota_no_data') if remaining is None else tr('quota_remaining', percent=self.quota_percent(remaining))
                reset = bucket.get('reset')
                if reset:
                    try:
                        date = datetime.fromisoformat(reset.replace('Z', '+00:00')).astimezone()
                        reset_text = tr('quota_reset_at', date=date.strftime('%d.%m %H:%M'))
                    except (ValueError, KeyError):
                        reset_text = tr('quota_reset_unknown')
                else:
                    reset_text = tr('quota_reset_unknown')
                row.update_data(value_text, remaining, color, reset_text)
                self.detail_quota_widgets[(group['kind'], bucket['window'])] = row
                add(row)

        bars_hint = QLabel(tr('detail_bars_hint'))
        bars_hint.setFont(QFont('Segoe UI', 12))
        bars_hint.setProperty('class', 'muted')
        bars_hint.setWordWrap(True)
        add(bars_hint)

        # Actions
        actions = QWidget()
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 8, 0, 16)
        use_btn = QPushButton(tr('btn_use_only_this'))
        use_btn.setProperty('primary', True)
        use_btn.setToolTip(tr('tip_use_only'))
        use_btn.clicked.connect(lambda: self.action(
            lambda: self.controller.route(account['name']), tr('action_account_selected')))
        actions_layout.addWidget(use_btn)
        self.pause_button = QPushButton(tr('btn_resume') if account['disabled'] else tr('btn_pause'))
        self.pause_button.setToolTip(tr('tip_pause_resume'))
        self.pause_button.clicked.connect(self.pause_selected)
        actions_layout.addWidget(self.pause_button)
        actions_layout.addStretch()
        remove_btn = QPushButton(tr('btn_remove_account'))
        remove_btn.setToolTip(tr('tip_remove'))
        remove_btn.clicked.connect(self.remove_selected_account)
        actions_layout.addWidget(remove_btn)
        add(actions)

        # Rename
        rename_frame = QWidget()
        rename_layout = QHBoxLayout(rename_frame)
        rename_layout.setContentsMargins(0, 0, 0, 20)
        self.rename_entry = QLineEdit()
        self.rename_entry.setPlaceholderText(tr('placeholder_label'))
        self.rename_entry.setText('' if self.controller.preferences.get('hide-account-names') else self.controller.preferences.get('labels', {}).get(account['name'], ''))
        rename_layout.addWidget(self.rename_entry, 1)
        save_btn = QPushButton(tr('btn_save_label'))
        save_btn.setToolTip(tr('tip_save_label'))
        save_btn.clicked.connect(lambda: self.rename(account, self.rename_entry.text()))
        rename_layout.addWidget(save_btn)
        add(rename_frame)

        self.unavailable_label = QLabel('')
        self.unavailable_label.setStyleSheet(f'color: {self.theme.color("warning")};')
        self.unavailable_label.setWordWrap(True)
        add(self.unavailable_label)

        pause_hint = QLabel(tr('detail_pause_hint'))
        pause_hint.setFont(QFont('Segoe UI', 12))
        pause_hint.setProperty('class', 'muted')
        pause_hint.setWordWrap(True)
        add(pause_hint)

        self.update_detail_account()

    def update_detail_account(self):
        account = next((a for a in self.items if a['name'] == self.selected), None)
        if not account or self.detail_account != self.selected:
            return
        if hasattr(self, 'detail_heading'):
            self.detail_heading.setText(self.display_name(account))
        if hasattr(self, 'detail_status'):
            self.detail_status.setText(self.account_status_text(account))
        if hasattr(self, 'pause_button'):
            self.pause_button.setText(tr('btn_resume') if account['disabled'] else tr('btn_pause'))
        if hasattr(self, 'unavailable_label'):
            self.unavailable_label.setText(self.account_status_text(account) if account.get('unavailable') or account.get('access_issue') else '')
        self.update_detail_quota()

    def update_detail_quota(self):
        cached = self.quota_cache.get(self.selected, {})
        if cached:
            time_str = cached['at'].strftime('%H:%M:%S') if cached.get('at') else ''
            self.quota_updated.setText(tr('quota_updated_at', time=time_str) if time_str else tr('quota_not_received'))
        else:
            self.quota_updated.setText(tr('detail_loading_quotas'))
        account = next((a for a in self.items if a['name'] == self.selected), {})
        stale = bool(account) and self.quota_is_cached(account)
        error = cached.get('error') or (cached.get('data', {}).get('summary_error') if cached else None)
        if error:
            text = tr('quota_load_error') + (' ' + tr('quota_cached_data') if stale else '')
            self.quota_updated.setText(text)
            self.quota_updated.setToolTip(display_reason(error))
            self.quota_updated.setStyleSheet(f'color: {self.theme.color("warning")};')
        elif stale:
            self.quota_updated.setText(tr('account_cached_quota'))
            self.quota_updated.setToolTip(self.account_tooltip(account))
            self.quota_updated.setStyleSheet(f'color: {self.theme.color("warning")};')
        else:
            self.quota_updated.setToolTip(tr('account_quota_hint'))
            self.quota_updated.setStyleSheet(f'color: {self.theme.color("muted")};')

        for group in self.quota_groups(self.selected):
            for bucket in group['buckets']:
                row = self.detail_quota_widgets.get((group['kind'], bucket['window']))
                if row:
                    row.bar.set_floor(quota_floor(self.controller.preferences, self.selected, group['kind'], bucket['window']))
                    remaining = bucket.get('remaining')
                    color = self.theme.color('muted') if stale else self.quota_color(remaining)
                    value_text = tr('quota_no_data') if remaining is None else tr('quota_remaining', percent=self.quota_percent(remaining))
                    reset = bucket.get('reset')
                    if reset:
                        try:
                            date = datetime.fromisoformat(reset.replace('Z', '+00:00')).astimezone()
                            reset_text = tr('quota_reset_at', date=date.strftime('%d.%m %H:%M'))
                        except (ValueError, KeyError):
                            reset_text = tr('quota_reset_unknown')
                    else:
                        reset_text = tr('quota_reset_unknown')
                    row.update_data(value_text, remaining, color, reset_text)

    # ── Quota management ──────────────────────────────────────────────

    def quota_groups(self, name):
        data = self.quota_cache.get(name, {}).get('data', {})
        groups = {g['kind']: g for g in data.get('groups', [])}
        result = []
        for kind, title, model in [('gemini', 'Gemini', 'claude-sonnet-4-5'), ('claude', 'Claude / GPT', 'claude-sonnet-4-6')]:
            group = groups.get(kind, {})
            buckets = {b['window']: b for b in group.get('buckets', [])}
            result.append({'kind': kind, 'name': group.get('name', title), 'buckets': [
                buckets.get('5h', {'window': '5h', **data.get('models', {}).get(model, {})}),
                buckets.get('weekly', {'window': 'weekly'})]})
        return result

    def update_total_quota(self):
        accounts = [a for a in self.items if not a.get('disabled')]
        values, weekly_values, entries, weekly_entries = [], [], [], []
        for account in accounts:
            cached = self.quota_cache.get(account['name'], {})
            if self.quota_is_cached(account):
                continue
            for group in self.quota_groups(account['name']):
                if group['kind'] == 'gemini':
                    weekly = next(b for b in group['buckets'] if b['window'] == 'weekly')
                    wv = weekly.get('remaining')
                    if isinstance(wv, (int, float)) and not isinstance(wv, bool) and 0 <= wv <= 1:
                        weekly_values.append(wv)
                        weekly_entries.append({'remaining': wv, 'reset': weekly.get('reset'), 'weekly_remaining': 1})
                    bucket = next(b for b in group['buckets'] if b['window'] == '5h')
                    v = bucket.get('remaining')
                    if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 1:
                        entry = quota_entry(account, bucket, weekly, 'gemini', preferences=self.controller.preferences)
                        values.append(0 if entry.get('weekly_remaining') == 0 else entry['remaining'])
                        entries.append(entry)

        # Weekly
        weekly_remaining = sum(weekly_values) / len(weekly_values) if weekly_values else None
        if len(weekly_values) != len(accounts):
            self.total_weekly_title.setText(tr('quota_1w_data', count=len(weekly_values), total=len(accounts)))
        else:
            self.total_weekly_title.setText(tr('quota_1w_pooled'))
        wc = self.quota_color(weekly_remaining)
        self.total_weekly_value.setText(self.quota_percent(weekly_remaining))
        self.total_weekly_value.setStyleSheet(f'color: {wc};')
        self.total_weekly_bar.set_value(weekly_remaining)
        self.total_weekly_bar.set_color(wc)
        self.total_weekly_remaining = weekly_remaining
        self.total_weekly_forecast = quota_projection(weekly_entries, exhausted_only=False)
        if self.total_weekly_forecast:
            self.total_weekly_bar.setVisible(False)
            self.weekly_forecast_widget.setVisible(True)
            self.weekly_forecast_widget.set_data(self.total_weekly_forecast, weekly_remaining, wc, self.theme.colors(), weekly=True)
        else:
            self.weekly_forecast_widget.setVisible(False)
            self.total_weekly_bar.setVisible(True)

        # 5h
        remaining = sum(values) / len(values) if values else None
        if len(values) != len(accounts):
            self.total_quota_title.setText(tr('quota_5h_data', count=len(values), total=len(accounts)))
        else:
            self.total_quota_title.setText(tr('quota_5h_pooled'))
        c = self.quota_color(remaining)
        self.total_quota_value.setText(self.quota_percent(remaining))
        self.total_quota_value.setStyleSheet(f'color: {c};')
        self.total_quota_bar.set_value(remaining)
        self.total_quota_bar.set_color(c)
        self.total_remaining = remaining
        self.total_forecast = quota_projection(entries)
        if self.total_forecast:
            self.total_quota_bar.setVisible(False)
            self.forecast_widget.setVisible(True)
            self.forecast_widget.set_data(self.total_forecast, remaining, c, self.theme.colors())
        else:
            self.forecast_widget.setVisible(False)
            self.total_quota_bar.setVisible(True)
        self.update_policy_summaries()

    def fetch_quota(self, name):
        if name in self.quota_pending:
            return
        cached = self.quota_cache.get(name)
        if cached and time.monotonic() - cached.get('checked', 0) < 30:
            return
        account = next((a for a in self.items if a['name'] == name), None)
        if not account:
            return
        self.quota_pending.add(name)
        startup = name not in self.google_startup_checked
        def fetch():
            try:
                data = self.controller.quotas(account)
                last_used = {}
                for model, event in self.activity_state['latest'].items():
                    actual = event.get('upstream_model') or self.model_aliases.get(event.get('model') or model, event.get('model') or model)
                    family = self.model_family(actual)
                    if family and event['name'] == name:
                        try:
                            at = datetime.fromisoformat(event['at'].replace('Z', '+00:00')).timestamp()
                            last_used[family] = max(last_used.get(family, 0), at)
                        except (ValueError, TypeError):
                            pass
                started = self.controller.start_full_quota_windows(account, data, last_used=last_used, startup=startup)
                if any(r['status'] == 200 for r in started):
                    try:
                        fresh = self.controller.quotas(account)
                        self.controller.confirm_quota_starts(account, started, data, fresh)
                        data = fresh
                    except AccountError:
                        pass
                return data, None, started
            except AccountError as exc:
                return None, str(exc), []
            except Exception:
                return None, tr('quota_load_error'), []
        def done(result):
            self.quota_pending.discard(name)
            data, error, started = result
            if data is not None and not data.get('summary_error'):
                self.google_startup_checked.add(name)
            if startup and started:
                self.google_startup_probes[name] = started
                probes = [r for rows in self.google_startup_probes.values() for r in rows]
                ok = sum(r['status'] == 200 for r in probes)
                confirmed = sum(self.controller.quota_starts.get(account_name + ':' + r['kind'], {}).get('weekly_started') is True
                                for account_name, rows in self.google_startup_probes.items() for r in rows)
                self.show_notice(tr('google_startup_report', accounts=len(self.google_startup_probes),
                                    ok=ok, confirmed=confirmed, failed=len(probes) - ok), 'warning' if len(probes) != ok else 'green')
            old = self.quota_cache.get(name, {})
            if data is not None:
                self.token_capacity.observe_quota('antigravity', name, data.get('subscription'), data.get('groups', []))
            if data is not None and data.get('summary_error') and old.get('data', {}).get('groups'):
                data['groups'] = old['data']['groups']
                data['summary_error'] += ' ' + tr('quota_cached_data')
            self.quota_cache[name] = {
                'data': data if data is not None else old.get('data', {}),
                'at': datetime.now().astimezone() if data is not None else old.get('at'),
                'checked': time.monotonic(), 'error': error}
            self.check_account_alerts()
            self.draw_account_list()
            self.update_total_quota()
            if self.selected == name:
                self.update_detail_quota()
            self.queue_policy()
        self.work(fetch, done)

    def periodic_quota(self):
        if not self.busy:
            for account in self.items:
                self.fetch_quota(account['name'])

    def tick_countdowns(self):
        self.draw_account_list()
        self.update_total_quota()

    # ── Activity ──────────────────────────────────────────────────────

    def start_activity(self):
        def enable():
            self.controller.request('/usage-statistics-enabled', 'PUT', {'value': True})
        self.work(enable, lambda _: self.poll_activity())

    def poll_activity(self):
        if self.closed:
            return
        if self.activity_busy:
            QTimer.singleShot(5000, self.poll_activity)
            return
        self.activity_busy = True
        def fetch():
            try:
                accounts, records, strategy = self.controller.activity_snapshot()
                try:
                    inventory = self.controller.activity_inventory()
                    if not isinstance(inventory, list):
                        inventory = []
                except (AccountError, OSError, ValueError, TypeError):
                    inventory = []
                state = copy.deepcopy(self.activity.ingest(records, accounts))
                return accounts, state, strategy, None, self.controller.quota_wait_status(), records, inventory
            except Exception:
                return None, None, None, tr('proxy_unreachable'), {'jobs': []}, [], []
        def done(result):
            self.activity_busy = False
            accounts, state, strategy, error, quota_wait, records, inventory = result
            if error:
                self.stats_strategy.setText(error)
                self.set_label_color(self.stats_strategy, 'warning')
            else:
                self.items = accounts
                self.activity_state = state
                self.activity_strategy = strategy
                self.account_uptime.update_many('antigravity', accounts)
                if inventory:
                    self.token_capacity.observe_usage(records, inventory, bootstrap=not self.capacity_usage_ready)
                    self.capacity_usage_ready = True
                self.check_account_alerts()
                self.render_activity()
                self.draw_account_list()
                waiting = [j for j in quota_wait.get('jobs', []) if j.get('state') == 'waiting']
                if waiting:
                    self.service.setText(self.quota_wait_text(waiting))
                    self.set_label_color(self.service, 'warn_text')
                else:
                    self.service.setText(tr('status_connected'))
                    self.set_label_color(self.service, 'green')
                latest = max(state['latest'].values(), key=lambda e: e['at'], default=None)
                if latest:
                    try:
                        age = (datetime.now(timezone.utc) - datetime.fromisoformat(latest['at'].replace('Z', '+00:00'))).total_seconds()
                    except (ValueError, TypeError):
                        age = 9999
                    if 0 <= age < 120:
                        self.fetch_quota(latest['name'])
                self.queue_policy()
            if not self.closed:
                QTimer.singleShot(5000, self.poll_activity)
        self.work(fetch, done)

    def render_activity(self):
        state = self.activity_state
        by_name = {a['name']: a for a in self.items}
        def name(key):
            return self.display_name(by_name[key]) if key in by_name else self.display_name({'name': key, 'email': key}) if key else tr('unknown_account')
        strategy = self.activity_strategy
        if self.policy_rows:
            text = tr('stats_strategy_earliest') + ' • ' + (tr('models_gemini_group') if self.policy_group == 'gemini' else 'Claude / GPT')
        elif strategy == 'fill-first':
            text = tr('stats_strategy_fill')
        elif strategy == 'round-robin':
            text = tr('stats_strategy_roundrobin')
        else:
            text = tr('activity_strategy', strategy=strategy)
        enabled = sum(not a['disabled'] for a in self.items)
        self.stats_strategy.setText(f'{text} • ' + tr('stats_enabled_accounts', count=enabled))
        self.set_label_color(self.stats_strategy, 'muted')
        if self.policy_rows:
            self.render_policy()

        latest = sorted(state['latest'].values(), key=lambda e: e['at'], reverse=True)
        if latest:
            last = latest[0]
            self.stats_latest.setText(tr('stats_last_success', name=name(last['name'])) + '\n' +
                model_name(last.get('upstream_model') or last['model'], self.model_aliases) + ' • ' + self.activity_time(last['at']))
            self.mode_activity.setText(tr('stats_last_response', name=name(last['name']), time=self.activity_time(last['at'])))

        stats = state['stats']
        success = sum(v['success'] for v in stats.values())
        failed = sum(v['failed'] for v in stats.values())
        tokens = sum(v['tokens'] for v in stats.values())
        switches = sum(bool(e['switch']) for e in state['events'])
        self.stats_totals.setText(tr('stats_totals', success=success, failed=failed, switches=switches, tokens=f'{tokens:,}'))

        # Update account rows in stats
        while self.stats_accounts_layout.count():
            item = self.stats_accounts_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for account in self.items:
            key = account['name']
            own = stats.get(key, {})
            count = own.get('success', 0) + own.get('failed', 0)
            average = own.get('latency_ms', 0) / count / 1000 if count else 0
            status = self.account_status_text(account)
            retries = []
            for cd in account.get('cooldowns') or []:
                try:
                    retry = datetime.fromisoformat(cd['retry_at'].replace('Z', '+00:00'))
                    if retry > datetime.now(timezone.utc):
                        model = tr('activity_all_models') if cd.get('scope') == 'credential' else model_name(cd.get('model_key') or '', self.model_aliases)
                        retries.append(tr('activity_model_retry', model=model,
                            time=self.time_until_reset(retry.isoformat())))
                except (KeyError, ValueError, TypeError, AttributeError):
                    pass
            if retries:
                status += '\n' + '\n'.join(dict.fromkeys(retries))
            elif account.get('restriction_reason'):
                status += '\n' + display_reason(account['restriction_reason'])
            label = QLabel(f"{name(key)} • {status}\n" +
                tr('activity_proxy_stats', success=account.get('success') or 0, failed=account.get('failed') or 0) +
                '\n' + tr('activity_observed', count=count, tokens=f'{own.get("tokens", 0):,}', avg=f'{average:.1f}') +
                (' • ' + tr('activity_last', time=self.activity_time(own['last'])) if own.get('last') else ''))
            label.setFont(QFont('Segoe UI', 13))
            label.setWordWrap(True)
            self.stats_accounts_layout.addWidget(label)

        # Journal
        mode = self.journal_filter.get()
        all_label = tr('stats_filter_all')
        switches_label = tr('stats_filter_switches')
        events = [e for e in state['events'] if mode == all_label or (mode == switches_label and e['switch']) or (mode != all_label and mode != switches_label and e['failed'])]
        lines = []
        for e in reversed(events[-100:]):
            title = tr('event_switch') if e['switch'] else tr('event_error') if e['failed'] else tr('event_response')
            route = (name(e['from']) + ' → ' if e['from'] else '') + name(e['name'])
            metrics = tr('event_metrics', seconds=f"{e['latency_ms'] / 1000:.1f}", tokens=f"{e['tokens']:,}")
            lines.append(f"{self.activity_time(e['at'])} • {title}\n{route} • {model_name(e.get('upstream_model') or e['model'], self.model_aliases)}\n{display_reason(e['reason'])} • {metrics}\n")
        content = '\n'.join(lines) or tr('stats_no_events')
        self.stats_journal.setPlainText(content)
        self.stats_observed.setText(tr('stats_monitoring_since', time=self.activity_time(state['since'])))
        self.render_token_capacity()

    def save_capacity_share(self):
        if not hasattr(self, 'capacity_share'):
            return
        self.controller.preferences['token-capacity-share'] = self.capacity_share.value()
        self.controller.save()

    def render_token_capacity(self):
        if not hasattr(self, 'capacity_table'):
            return
        rows = [row for row in self.token_capacity.rows() if row.get('ready')]
        self.capacity_table.setRowCount(len(rows))
        share = self.capacity_share.value() / 100 if hasattr(self, 'capacity_share') else .2
        provider_names = {'antigravity': 'Google', 'codex': 'ChatGPT', 'claude': 'Claude'}
        for index, row in enumerate(rows):
            provider_label = provider_names.get(row['provider'], row['provider'])
            if row['provider'] == 'antigravity':
                provider_label += ' · ' + ('Gemini' if row['family'] == 'gemini' else 'Claude')
            values = [provider_label, row['plan'], model_name(row['model'], {}),
                      tr('period_5h') if row['window'] == '5h' else tr('period_weekly'),
                      f"{int(round(row['capacity'] * share)):,}", str(row['samples_count'])]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 4:
                    cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    cell.setToolTip(tr('capacity_range_tooltip', minimum=f"{row['min_capacity']:,}",
                                       maximum=f"{row['max_capacity']:,}"))
                self.capacity_table.setItem(index, column, cell)
        self.capacity_empty.setVisible(not rows)
        self.capacity_table.setVisible(bool(rows))
        self.render_quota_forecasts()

    @staticmethod
    def format_eta(seconds):
        if seconds <= 0:
            return tr('quota_eta_now')
        minutes = max(1, math.ceil(seconds / 60))
        days, hours, minutes = minutes // 1440, minutes // 60 % 24, minutes % 60
        if days:
            return tr('quota_eta_days', days=days, hours=hours)
        if hours:
            return tr('quota_eta_hours', hours=hours, minutes=minutes)
        return tr('quota_eta_minutes', minutes=minutes)

    def render_quota_forecasts(self):
        if not hasattr(self, 'forecast_table'):
            return
        now = time.time()
        candidates = []
        provider_names = {'antigravity': 'Google', 'codex': 'ChatGPT', 'claude': 'Claude'}

        def add_account(provider, account, plan, groups):
            if account.get('disabled') or not groups:
                return
            floors = {}
            for group in groups:
                kind = group.get('kind')
                for bucket in group.get('buckets', []):
                    window = bucket.get('window')
                    if kind and window:
                        floors.setdefault(kind, {})[window] = quota_floor(
                            self.controller.preferences, account['name'], kind, window) / 100
            forecasts = self.token_capacity.forecasts(provider, account['name'], plan, groups, floors=floors, now=now)
            for forecast in forecasts:
                candidates.append((provider_names.get(provider, provider), self.display_name(account), forecast))

        for account in self.items:
            cached = self.quota_cache.get(account['name'], {})
            if not cached.get('data') or self.quota_is_cached(account):
                continue
            data = cached['data']
            add_account('antigravity', account, data.get('subscription'), data.get('groups', []))
        for provider, accounts in (('codex', self.chatgpt_accounts), ('claude', self.claude_accounts_panel.rows)):
            for account in accounts:
                quota = account.get('quota') or {}
                if quota.get('error'):
                    continue
                add_account(provider, account, quota.get('plan_type') or account.get('plan_type'),
                            oauth_quota_groups(quota, provider))

        candidates.sort(key=lambda item: (item[2]['eta_seconds'], item[0], item[1], item[2]['model']))
        self.forecast_table.setRowCount(len(candidates))
        for index, (provider, account_name, row) in enumerate(candidates):
            window = tr('period_5h') if row['window'] == '5h' else tr('period_weekly')
            eta = self.format_eta(row['eta_seconds'])
            reset_delta = row.get('reset_at') - now if row.get('reset_at') is not None else None
            reset_text = self.format_eta(reset_delta) if reset_delta is not None else tr('quota_reset_unknown')
            if row['reserve_reached']:
                outlook = tr('quota_eta_reserve_reached')
            elif reset_delta is None:
                outlook = tr('quota_eta_reset_unknown')
            elif row['eta_seconds'] < max(0, reset_delta):
                outlook = tr('quota_eta_before_reset')
            else:
                outlook = tr('quota_eta_reset_first')
            values = [provider, account_name, model_name(row['model'], {}), window, eta, reset_text, outlook]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 4:
                    cell.setToolTip(tr('quota_eta_confidence', count=row['samples_count']))
                if column == 6 and outlook == tr('quota_eta_before_reset'):
                    cell.setForeground(QBrush(QColor(self.theme.color('warning'))))
                self.forecast_table.setItem(index, column, cell)
        self.forecast_empty.setVisible(not candidates)
        self.forecast_table.setVisible(bool(candidates))

    # ── Policy ────────────────────────────────────────────────────────

    def set_policy_group(self, value):
        gemini_label = tr('models_gemini_group')
        self.controller.preferences['reset-group'] = {'Gemini': 'gemini', gemini_label: 'gemini', 'Claude / GPT': 'claude'}.get(value, 'auto')
        self.controller.save()
        self.queue_policy()

    def target_policy_group(self):
        choice = self.controller.preferences.get('reset-group', 'auto')
        if choice in ('gemini', 'claude'):
            return choice
        latest = sorted(self.activity_state['latest'].values(), key=lambda e: e['at'], reverse=True)
        if latest:
            model = latest[0].get('upstream_model') or self.model_aliases.get(latest[0]['model'], latest[0]['model'])
            if model == 'claude-sonnet-4-5' or model.startswith('gemini'):
                return 'gemini'
            if model.startswith(('claude', 'gpt')):
                return 'claude'
        return 'gemini'

    def queue_policy(self):
        if self.closed or self.policy_pending:
            return
        self.policy_pending = True
        QTimer.singleShot(1200, self._apply_policy)

    def _apply_policy(self):
        self.policy_pending = False
        if self.policy_busy or self.busy or self.quota_pending:
            self.queue_policy()
            return
        if self.controller.preferences.get('mode') == 'single':
            self.policy_label.setText(tr('policy_manual'))
            return
        group = self.target_policy_group()
        rows = rank_accounts(self.items, self.quota_cache, group,
                             priorities=self.controller.preferences.get('account-priorities', {}),
                             preferences=self.controller.preferences)
        title = tr('models_gemini_group') if group == 'gemini' else 'Claude / GPT'
        if not rows or all(r['tier'] == 2 for r in rows):
            return
        if self.policy_rows == rows and self.policy_group == group:
            actual = {a['name']: a.get('priority') for a in self.items}
            if all(actual.get(r['name']) == r['priority'] for r in rows):
                return
        self.policy_busy = True
        def apply():
            try:
                return self.controller.apply_reset_priority(rows), None
            except Exception as exc:
                return False, str(exc) if isinstance(exc, AccountError) else tr('action_generic_error')
        def done(result):
            self.policy_busy = False
            applied, error = result
            if error:
                self.policy_label.setText(error)
                self.set_label_color(self.policy_label, 'warning')
                return
            if not applied:
                self.queue_policy()
                return
            self.policy_rows, self.policy_group = rows, group
            self.render_policy()
        self.work(apply, done)

    def render_policy(self):
        if self.controller.preferences.get('mode') == 'single':
            self.policy_label.setText(tr('policy_manual'))
            return
        title = tr('models_gemini_group') if self.policy_group == 'gemini' else 'Claude / GPT'
        names = {a['name']: self.display_name(a) for a in self.items}
        lines = [tr('policy_ranking', title=title)]
        for idx, row in enumerate(self.policy_rows, 1):
            reset = ' • ' + self.activity_time(row['reset']) if row.get('reset') else ''
            lines.append(f"{idx}. {names.get(row['name'], self.display_name({'name': row['name'], 'email': row['name']}))} — {display_reason(row['reason'])}{reset}")
        lines.append(tr('policy_footer'))
        self.policy_label.setText('\n'.join(lines))
        self.set_label_color(self.policy_label, 'muted')
        self.mode_note.setText(tr('policy_mode_note', title=title))

    # ── Gateway jobs ──────────────────────────────────────────────────

    def poll_gateway_jobs(self):
        if self.closed or not self.controller.key:
            return
        def done(snapshot):
            if self.closed:
                return
            self.gateway_jobs = snapshot.get('jobs', [])
            self.gateway_jobs_checked = time.monotonic()
        self.work(self.controller.quota_wait_status, done)

    def active_provider_accounts(self):
        if time.monotonic() - getattr(self, 'gateway_jobs_checked', 0) > 10:
            return {}
        aliases = getattr(self, 'model_aliases', {})
        running = {self.model_family(j.get('upstream_model') or aliases.get(j.get('model'), j.get('model', '')))
                   for j in self.gateway_jobs if j.get('state') == 'running'}
        enabled = {a['name'] for a in self.items if not a.get('disabled')}
        latest = {}
        for model, event in self.activity_state['latest'].items():
            actual = event.get('upstream_model') or aliases.get(event.get('model') or model, event.get('model') or model)
            family = self.model_family(actual)
            if family and family in running and not event.get('failed') and (family not in latest or event['at'] > latest[family]['at']):
                latest[family] = event
        return {f: e['name'] for f, e in latest.items() if e['name'] in enabled}

    def last_account_model(self, name, now=None):
        stats = self.activity_state.get('stats', {}).get(name, {})
        candidates = [e for e in self.activity_state.get('events', []) if e.get('name') == name]
        candidates += [e for e in self.activity_state.get('latest', {}).values() if e.get('name') == name]
        if stats.get('last_model') and stats.get('last'):
            candidates.insert(0, {'at': stats['last'], 'upstream_model': stats['last_model']})
        last = max(candidates, key=lambda e: e.get('at', ''), default={})
        try:
            timestamp = datetime.fromisoformat(last['at'].replace('Z', '+00:00'))
            age = ((now or datetime.now(timezone.utc)) - timestamp).total_seconds()
            if not 0 <= age < 60:
                return ''
        except (KeyError, ValueError, TypeError, AttributeError):
            return ''
        model = last.get('upstream_model') or last.get('model')
        return model_name(model, getattr(self, 'model_aliases', None)) if model else ''

    def animate_active_borders(self):
        # Simplified for PySide6 — update card styling for active accounts
        providers = self.active_provider_accounts()
        active = set(providers.values())
        for name, card in self.account_widgets.items():
            account = next((a for a in self.items if a['name'] == name), {'name': name})
            card.setToolTip(self.account_tooltip(account))
            if name in active:
                families = tuple(k for k in ('gemini', 'claude') if providers.get(k) == name)
                phase = (time.monotonic() / 8) % 1
                # Rainbow border via stylesheet
                rgb = colorsys.hsv_to_rgb(phase, 0.72, 1.0)
                border_color = '#' + ''.join(f'{round(v * 255):02x}' for v in rgb)
                card.setStyleSheet(f'AccountCard {{ border: 2px solid {border_color}; border-radius: 10px; background-color: {self.theme.color("card_alt")}; }}')
            else:
                t = self.theme.colors()
                selected = not self.details_collapsed and name == self.selected
                card.set_selected(selected, t)

    # ── Actions ───────────────────────────────────────────────────────


    def action(self, fn, message):
        if self.busy:
            return
        def perform():
            fn()
            return self.controller.accounts()
        def done(items):
            self.show_notice(message, 'green')
            self.loaded(items)
        self.work(perform, done, mutation=True)

    def pause_selected(self):
        account = next((a for a in self.items if a['name'] == self.selected), None)
        if account:
            self.action(lambda: self.controller.pause(account), tr('action_status_updated'))

    def remove_selected_account(self):
        App.remove_account(self, self.selected)

    def remove_account(self, name):
        if self.busy:
            return
        account = next((a for a in self.items if a['name'] == name), None)
        if not account:
            return
        name = account['name']
        identity = self.display_name(account) if self.controller.preferences.get('hide-account-names') else account.get('email') or self.display_name(account)
        reply = QMessageBox.question(self, tr('confirm_remove_title'),
            tr('confirm_remove_body', email=identity),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        def remove():
            self.controller.remove_account(name)
            return self.controller.accounts()
        def done(items):
            self.quota_cache.pop(name, None)
            self.show_notice(tr('action_removed'), 'green')
            self.loaded(items)
        self.work(remove, done, mutation=True)

    def rename(self, account, label):
        try:
            self.controller.rename(account['name'], label)
            self.loaded(self.items)
        except OSError:
            self.show_notice(tr('action_label_error'), 'warning')

    # ── Verification ──────────────────────────────────────────────────

    def open_verification(self, name):
        account = next((a for a in self.items if a['name'] == name), None)
        if account and account.get('verification_url'):
            webbrowser.open(account['verification_url'])

    def copy_verification_link(self, name):
        account = next((a for a in self.items if a['name'] == name), None)
        if account and account.get('verification_url'):
            QApplication.clipboard().setText(account['verification_url'])
            self.show_notice(tr('action_verification_copied'), 'green')
        else:
            self.show_notice(tr('action_verification_refresh_first'), 'warn')

    def retry_verification(self, name):
        account = next((a for a in self.items if a['name'] == name), None)
        if account:
            self.action(lambda: self.controller.retry_verified_account(account), tr('action_verified_retry'))

    def refresh_verification_link(self, name):
        account = next((a for a in self.items if a['name'] == name), None)
        if not account or self.busy:
            return
        def refresh():
            result = self.controller.refresh_verification_url(account)
            return self.controller.accounts(), result
        def done(result):
            accounts, issue = result
            self.loaded(accounts)
            if issue.get('verification_url'):
                webbrowser.open(issue['verification_url'])
                self.show_notice(tr('action_verification_opened'), 'green')
            else:
                self.show_notice(tr('action_verification_accepted'), 'green')
        self.work(refresh, done, mutation=True)

    # ── Login flow ────────────────────────────────────────────────────

    def add_account(self):
        if self.busy or self.pending_login:
            return
        self.work(self.controller.begin_login_details, self.login_started, mutation=True)

    def login_started(self, result):
        if not isinstance(result, (tuple, list)) or len(result) not in (2, 3):
            self.pending_login = None
            self.add_button.setEnabled(True)
            self.show_notice(str(result)[:300] or tr('login_failed'), 'warning')
            return
        if len(result) == 3:
            self.login_url, state, self.login_callback_uri = result
        else:
            # Keep compatibility with callers and tests that provide the legacy pair.
            self.login_url, state = result
            self.login_callback_uri = None
        self.pending_login = (state, time.monotonic())
        self.add_button.setEnabled(False)
        self.show_notice(tr('login_browser_hint'), 'accent')
        dialog = self.login_dialog = QDialog(self)
        dialog.setWindowTitle(tr('win_add_account'))
        dialog.setMinimumSize(500, 390)
        dialog.resize(520, 420)
        dl = QVBoxLayout(dialog)
        dl.setContentsMargins(24, 22, 24, 20)
        heading = QLabel(tr('login_heading'))
        heading.setFont(QFont('Segoe UI', 21, QFont.Bold))
        heading.setAlignment(Qt.AlignCenter)
        heading.setWordWrap(True)
        dl.addWidget(heading)
        hint = QLabel(tr('login_hint'))
        hint.setFont(QFont('Segoe UI', 12))
        hint.setProperty('class', 'muted')
        hint.setWordWrap(True)
        dl.addWidget(hint)
        browser_buttons = QHBoxLayout()
        reopen_btn = QPushButton(tr('btn_reopen_signin'))
        reopen_btn.setToolTip(tr('login_browser_hint'))
        reopen_btn.clicked.connect(lambda: webbrowser.open(self.login_url or ''))
        browser_buttons.addWidget(reopen_btn)
        copy_btn = QPushButton(tr('login_copy_url'))
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(self.login_url or ''))
        browser_buttons.addWidget(copy_btn)
        dl.addLayout(browser_buttons)
        if self.login_callback_uri:
            callback_hint = QLabel(tr('login_callback_hint'))
            callback_hint.setWordWrap(True)
            callback_hint.setProperty('class', 'muted')
            dl.addWidget(callback_hint)
            self.login_callback_input = QLineEdit()
            self.login_callback_input.setObjectName('googleOAuthCallback')
            self.login_callback_input.setEchoMode(QLineEdit.Password)
            self.login_callback_input.setPlaceholderText(tr('login_callback_placeholder'))
            self.login_callback_input.setClearButtonEnabled(True)
            dl.addWidget(self.login_callback_input)
            self.login_callback_status = QLabel('')
            self.login_callback_status.setWordWrap(True)
            self.login_callback_status.setProperty('class', 'muted')
            dl.addWidget(self.login_callback_status)
            submit_btn = QPushButton(tr('login_complete_callback'))
            def submit_callback():
                text = self.login_callback_input.text()
                if not text or not self.pending_login or not self.login_callback_uri:
                    return
                submit_btn.setEnabled(False)
                self.login_callback_input.clear()
                active_state = self.pending_login[0]
                redirect_uri = self.login_callback_uri
                def forward():
                    try:
                        self.controller.submit_google_callback(text, redirect_uri, active_state)
                    except AccountError as error:
                        return safe_detail(error)
                def forwarded(error):
                    if self.login_dialog is not dialog or not dialog.isVisible():
                        return
                    submit_btn.setEnabled(True)
                    if error:
                        self.login_callback_status.setText(error)
                        self.login_callback_status.setProperty('class', 'warning')
                    else:
                        self.login_callback_status.setText(tr('login_callback_forwarded'))
                        self.login_callback_status.setProperty('class', 'muted')
                    self.login_callback_status.style().unpolish(self.login_callback_status)
                    self.login_callback_status.style().polish(self.login_callback_status)
                self.work(forward, forwarded, mutation=True)
            submit_btn.clicked.connect(submit_callback)
            dl.addWidget(submit_btn)
        wait_label = QLabel(tr('login_waiting'))
        wait_label.setFont(QFont('Segoe UI', 11))
        wait_label.setProperty('class', 'muted')
        wait_label.setWordWrap(True)
        dl.addWidget(wait_label)
        cancel_btn = QPushButton(tr('chatgpt_cancel'))
        cancel_btn.clicked.connect(lambda: self.finish_login(tr('login_cancelled'), False, cancel=True))
        dl.addWidget(cancel_btn)
        dialog.finished.connect(lambda _: self._google_login_dialog_closed(dialog))
        dialog.show()
        webbrowser.open(self.login_url)
        QTimer.singleShot(1800, self.poll_login)

    def _google_login_dialog_closed(self, dialog):
        if self.login_dialog is dialog and self.pending_login:
            self.finish_login(tr('login_cancelled'), False, cancel=True)

    def poll_login(self):
        if not self.pending_login or self.closed:
            return
        state, started = self.pending_login
        if time.monotonic() - started > 310:
            self.finish_login(tr('login_timeout'), False, cancel=True)
            return
        def poll():
            try:
                return self.controller.login_status(state)
            except AccountError:
                return {'status': 'wait'}
        def done(result):
            if not self.pending_login or self.pending_login[0] != state:
                return
            if result.get('status') == 'ok':
                self.finish_login(tr('login_saved'), True)
            elif result.get('status') == 'error':
                self.finish_login(tr('login_failed'), False)
            else:
                QTimer.singleShot(1800, self.poll_login)
        self.work(poll, done)

    def finish_login(self, message, success, cancel=False):
        state = self.pending_login[0] if self.pending_login else None
        self.pending_login = None
        self.login_url = None
        self.login_callback_uri = None
        if self.login_callback_input is not None:
            self.login_callback_input.clear()
            self.login_callback_input = None
        dialog = getattr(self, 'login_dialog', None)
        self.login_dialog = None
        self.add_button.setEnabled(True)
        if dialog is not None and dialog.isVisible():
            dialog.close()
        if cancel and not success and state:
            self.work(lambda: self.controller.cancel_login(state), lambda _: None)
        self.show_notice(message, 'green' if success else 'warning')
        if success:
            def reconcile():
                results = self.controller.reconcile_new_login()
                return results, self.controller.accounts()
            def done(result):
                results, items = result
                self.loaded(items)
                pending = next((r for r in results if r.get('access_issue') == 'verification'), None)
                error = next((r for r in results if r.get('status') == 'error'), None)
                if pending:
                    self.show_notice(tr('login_needs_verification'), 'warn')
                    if pending.get('verification_url'):
                        webbrowser.open(pending['verification_url'])
                elif error:
                    self.show_notice(error['message'], 'warning')
                else:
                    msg = tr('login_verified_auto') if self.controller.preferences.get('mode') != 'single' else tr('login_verified_manual')
                    self.show_notice(msg, 'green')
            self.work(reconcile, done, mutation=True)

    # ── Updates ───────────────────────────────────────────────────────

    def check_for_updates(self):
        from updater import check_update
        self.update_button.setEnabled(False)
        self.update_button.setText(tr('update_checking'))
        def done(release):
            self.available_update = release
            if release:
                self.update_button.setText(tr('update_to_version', version=release['version']))
                self.update_button.clicked.disconnect()
                self.update_button.clicked.connect(self.install_update)
            else:
                self.update_button.setText(tr('update_up_to_date'))
            self.update_button.setEnabled(True)
        self.work(check_update, done)

    def install_update(self):
        if not self.available_update:
            return
        from updater import download_update
        self.update_button.setEnabled(False)
        self.update_button.setText(tr('update_downloading'))
        def downloaded(path):
            self.pending_update = path
            self.apply_pending_update()
        self.work(lambda: download_update(self.controller, self.available_update), downloaded)

    def apply_pending_update(self):
        if self.closed or not self.pending_update:
            return
        import json
        import urllib.request
        def idle():
            request = urllib.request.Request('http://127.0.0.1:8317/v0/management/quota-wait',
                headers={'Authorization': 'Bearer ' + self.controller.key})
            try:
                with urllib.request.urlopen(request, timeout=3) as response:
                    return not json.load(response).get('jobs')
            except OSError:
                return False
        def done(is_idle):
            if is_idle and not self.busy and not self.pending_login:
                from updater import launch_update
                launch_update(self.controller, self.pending_update)
                self.update_button.setText(tr('update_installing'))
            else:
                self.update_button.setText(tr('update_waiting'))
                QTimer.singleShot(5000, self.apply_pending_update)
        self.work(idle, done)

    # ── Diagnostics ───────────────────────────────────────────────────

    def save_diagnostic_log(self):
        from gateway_diagnostics import export_diagnostics
        destination, _ = QFileDialog.getSaveFileName(self, tr('diag_saved'),
            'GeminiAccounts-diagnostics-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.zip',
            'Diagnostic archive (*.zip)')
        if destination:
            self.work(lambda: export_diagnostics(self.controller, destination),
                lambda path: QMessageBox.information(self, tr('diag_saved'), str(path)))

    def send_diagnostic_log(self):
        from gateway_diagnostics import send_diagnostics, DEFAULT_ENDPOINT, read_upload_token, save_upload_token
        endpoint = self.controller.preferences.get('diagnostics-endpoint') or DEFAULT_ENDPOINT
        if not endpoint:
            endpoint, ok = QInputDialog.getText(self, tr('diag_recipient'), tr('diag_endpoint_prompt'))
            if not ok or not endpoint:
                return
        from urllib.parse import urlparse
        parsed = urlparse(endpoint)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            QMessageBox.warning(self, tr('diag_recipient'), tr('diag_invalid_url'))
            return
        token = read_upload_token(self.controller, endpoint)
        if not token:
            token, ok = QInputDialog.getText(self, tr('diag_recipient'),
                tr('diag_token_prompt', host=parsed.hostname), QLineEdit.Password)
            if not ok or not token:
                return
        reply = QMessageBox.question(self, tr('btn_send_diag'),
            f'Recipient: {endpoint}\n\n' +
            'The ZIP contains request phases, models, errors, timings, account cooldowns and active requests. '
            'Email addresses are replaced with account labels. Prompts, generated text, passwords and authentication tokens are excluded.'
            '\n\nSend this diagnostic archive now?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        save_upload_token(self.controller, endpoint, token.strip())
        self.controller.preferences['diagnostics-endpoint'] = endpoint
        self.controller.save()
        self.work(lambda: send_diagnostics(self.controller, endpoint),
            lambda status: QMessageBox.information(self, tr('diag_saved'), tr('diag_sent', status=status)))

    # ── Model settings dialog ─────────────────────────────────────────

    def model_settings(self):
        if hasattr(self, 'model_dialog') and self.model_dialog.isVisible():
            self.model_dialog.raise_()
            return
        dialog = self.model_dialog = QDialog(self)
        dialog.setWindowTitle(tr('win_model_selection'))
        dialog.setMinimumSize(550, 395)
        dialog.resize(600, 440)
        dl = QVBoxLayout(dialog)
        dl.setContentsMargins(24, 20, 24, 24)
        dl.setSpacing(8)

        heading = QLabel(tr('models_heading'))
        heading.setFont(QFont('Segoe UI', 23, QFont.Bold))
        heading.setWordWrap(True)
        dl.addWidget(heading)
        hint = QLabel(tr('models_hint'))
        hint.setFont(QFont('Segoe UI', 12))
        hint.setProperty('class', 'muted')
        hint.setWordWrap(True)
        dl.addWidget(hint)

        controls = QWidget()
        cl = QGridLayout(controls)
        cl.setContentsMargins(0, 10, 0, 0)
        selectors = {}
        options = {}
        current = self.controller.selected_family_models()
        for row, group in enumerate(('claude', 'gemini')):
            label = QLabel(tr('models_claude_group') if group == 'claude' else tr('models_gemini_group'))
            label.setFixedWidth(145)
            cl.addWidget(label, row, 0)
            selector = ThemedComboBox()
            selector.setEnabled(False)
            selector.addItem(tr('models_loading'))
            cl.addWidget(selector, row, 1)
            selectors[group] = selector
        cl.setColumnStretch(1, 1)
        dl.addWidget(controls)

        # Client update checkbox
        codex_path = self.integrations.paths()['codex'][0]
        try:
            managed_codex = '# BEGIN Gemini Accounts managed provider' in codex_path.read_text('utf-8-sig')
        except OSError:
            managed_codex = False
        backups = self.integrations.backups()
        managed_clients = [client for client, paths in self.integrations.paths().items()
                           if any(str(path.resolve()) in backups for path in paths)]
        if managed_codex and 'codex' not in managed_clients:
            managed_clients.append('codex')
        if self.integrations.legacy_desktop_preset() and 'claude_desktop' not in managed_clients:
            managed_clients.append('claude_desktop')

        update_check = QCheckBox(tr('models_update_clients'))
        update_check.setChecked(bool(managed_clients))
        update_check.setEnabled(bool(managed_clients))
        dl.addWidget(update_check)

        status = QLabel(tr('models_loading_catalog'))
        status.setFont(QFont('Segoe UI', 12))
        status.setProperty('class', 'muted')
        status.setWordWrap(True)
        dl.addWidget(status)

        def apply_models():
            selected = {g: options[g][s.currentText()] for g, s in selectors.items()}
            if update_check.isChecked():
                paths = '\n'.join(str(p) for c in managed_clients for p in self.integrations.paths()[c])
                reply = QMessageBox.question(dialog, tr('confirm_allow_setup_title'),
                    tr('confirm_model_files', paths=paths),
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if reply != QMessageBox.Yes:
                    return
            apply_btn.setEnabled(False)
            update_client = update_check.isChecked()
            def change():
                changed = False
                try:
                    prev_entries = self.controller.request('/oauth-model-alias').get('oauth-model-alias', {}).get('antigravity', [])
                    prev_prefs = copy.deepcopy(self.controller.preferences)
                    aliases = self.controller.set_family_models(selected['gemini'], selected['claude'])
                    changed = True
                    if update_client:
                        self.integrations.apply(managed_clients)
                    return aliases, None
                except Exception as error:
                    if changed:
                        try:
                            self.controller.request('/oauth-model-alias', 'PATCH', {'provider': 'antigravity', 'aliases': prev_entries})
                            self.controller.preferences = prev_prefs
                            self.controller.save()
                        except Exception:
                            pass
                    return None, str(error)
            def done(result):
                aliases, error = result
                if not dialog.isVisible():
                    return
                apply_btn.setEnabled(True)
                if error:
                    status.setText(error)
                    self.set_label_color(status, 'warning')
                    return
                self.model_aliases = aliases
                self.activity = Activity(self.controller.data_dir / 'activity.json')
                self.activity_state = copy.deepcopy(self.activity.state)
                msg = tr('models_applied_restart') if update_client else tr('models_applied')
                status.setText(msg)
                self.set_label_color(status, 'green')
                self.render_activity()
            self.work(change, done)

        apply_btn = QPushButton(tr('btn_apply_models'))
        apply_btn.setProperty('primary', True)
        apply_btn.setEnabled(False)
        apply_btn.clicked.connect(apply_models)
        dl.addWidget(apply_btn)

        def load():
            try:
                return self.controller.family_model_choices(), None
            except Exception as e:
                return None, str(e)
        def loaded(result):
            if not dialog.isVisible():
                return
            choices, error = result
            if error:
                status.setText(error)
                self.set_label_color(status, 'warning')
                return
            for group in ('claude', 'gemini'):
                options[group] = {}
                for model in choices[group]:
                    label = model_name(model, {})
                    if label in options[group]:
                        label += f' ({model})'
                    options[group][label] = model
                selectors[group].clear()
                selectors[group].addItems(list(options[group]))
                selectors[group].setEnabled(True)
                sel_label = next((l for l, m in options[group].items() if m == current.get(group)), None)
                if sel_label:
                    selectors[group].setCurrentText(sel_label)
            apply_btn.setEnabled(True)
            status.setText(tr('models_quota_note'))
            self.set_label_color(status, 'muted')
        self.work(load, loaded)
        dialog.show()

    # ── Connection settings dialog ────────────────────────────────────

    def connection_settings(self):
        if hasattr(self, 'conn_dialog') and self.conn_dialog.isVisible():
            self.conn_dialog.raise_()
            return
        dialog = self.conn_dialog = QDialog(self)
        dialog.setWindowTitle(tr('win_connections'))
        dialog.setMinimumSize(620, 480)
        dialog.resize(660, 520)
        dl = QVBoxLayout(dialog)
        dl.setContentsMargins(24, 22, 24, 24)
        dl.setSpacing(8)

        heading = QLabel(tr('conn_heading'))
        heading.setFont(QFont('Segoe UI', 23, QFont.Bold))
        heading.setWordWrap(True)
        dl.addWidget(heading)
        hint = QLabel(tr('conn_hint'))
        hint.setProperty('class', 'muted')
        hint.setWordWrap(True)
        dl.addWidget(hint)

        detected = self.integrations.detected()
        choices = {}
        for client, title_key in [('claude_desktop', 'conn_claude_desktop'), ('codex', 'conn_codex'), ('claude_cli', 'conn_claude_cli')]:
            cb = QCheckBox(tr(title_key) + ('' if detected[client] else tr('conn_not_detected')))
            cb.setChecked(detected[client])
            dl.addWidget(cb)
            choices[client] = cb

        status = QLabel(tr('conn_sessions_preserved'))
        status.setFont(QFont('Segoe UI', 12))
        status.setProperty('class', 'muted')
        status.setWordWrap(True)
        dl.addWidget(status)

        def apply():
            clients = [n for n, cb in choices.items() if cb.isChecked()]
            if not clients:
                status.setText(tr('conn_choose_one'))
                self.set_label_color(status, 'warn_text')
                return
            paths = '\n'.join(str(p) for n in clients for p in self.integrations.paths()[n])
            reply = QMessageBox.question(dialog, tr('confirm_allow_setup_title'),
                tr('confirm_config_files', paths=paths),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
            apply_btn.setEnabled(False)
            def perform():
                try:
                    return self.integrations.apply(clients), None
                except Exception as e:
                    return None, str(e)
            def done(result):
                configured, error = result
                apply_btn.setEnabled(True)
                if error:
                    status.setText(tr('setup_failed', error=error))
                    self.set_label_color(status, 'warn_text')
                else:
                    status.setText(tr('conn_configured'))
                    self.set_label_color(status, 'green')
                    desktops = [n for n in clients if n in ('claude_desktop', 'codex')]
                    if desktops:
                        reply = QMessageBox.question(dialog, tr('confirm_restart_title'), tr('confirm_restart_body'),
                            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                        if reply == QMessageBox.Yes:
                            self.work(lambda: self.integrations.restart_desktop(desktops),
                                lambda _: status.setText(tr('conn_restarted')))
            self.work(perform, done, mutation=True)

        apply_btn = QPushButton(tr('btn_configure_apps'))
        apply_btn.setProperty('primary', True)
        apply_btn.clicked.connect(apply)
        dl.addWidget(apply_btn)
        quota_settings = QPushButton(tr('quota_display_settings'))
        quota_settings.clicked.connect(self.quota_display_settings)
        dl.addWidget(quota_settings)

        def restore():
            reply = QMessageBox.question(dialog, tr('confirm_restore_title'),
                tr('confirm_restore_body'), QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
            def reset():
                with quota_policy_lock:
                    clear_quota_limits(self.controller)
                    count = self.integrations.restore()
                    self.controller.preferences = {'labels': {}, 'mode': 'pool', 'selected': None, 'connections-offered': True}
                    self.controller.save()
                return count
            def done(count):
                status.setText(tr('conn_restored', count=count))
                self.set_label_color(status, 'green')
            self.work(reset, done, mutation=True)

        restore_btn = QPushButton(tr('btn_restore_settings'))
        restore_btn.clicked.connect(restore)
        dl.addWidget(restore_btn)
        dl.addStretch()
        dialog.show()

    def quota_display_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(tr('display_settings'))
        dialog.setMinimumWidth(480)
        layout = QVBoxLayout(dialog)
        options = QHBoxLayout()
        language = ThemedComboBox()
        for code, name in LANGUAGES.items():
            language.addItem(name, code)
        language.setCurrentIndex(language.findData(current_language()))
        language.setToolTip(tr('tip_language'))
        options.addWidget(language, 1)
        theme = ThemedComboBox()
        theme.addItem(tr('theme_light'), 'light')
        theme.addItem(tr('theme_dark'), 'dark')
        theme.setCurrentIndex(theme.findData(self.theme.current))
        options.addWidget(theme, 1)
        layout.addLayout(options)
        visibility_hint = QLabel(tr('service_visibility_hint'))
        visibility_hint.setWordWrap(True)
        layout.addWidget(visibility_hint)
        visibility = {}
        for provider, title in [('google', 'Google · Gemini / Claude'), ('api', tr('tab_api_keys')),
                                ('codex', 'ChatGPT'), ('claude', 'Claude subscription'),
                                ]:
            checkbox = QCheckBox(title)
            checkbox.setObjectName('serviceVisibility_' + provider)
            checkbox.setChecked(self.service_visible(provider))
            visibility[provider] = checkbox
            layout.addWidget(checkbox)
        hint = QLabel(tr('quota_display_hint'))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        threshold = QDoubleSpinBox()
        threshold.setObjectName('weeklyThresholdInput')
        threshold.setRange(0, 100)
        threshold.setDecimals(1)
        threshold.setSuffix(' %')
        threshold.setValue(weekly_threshold(self.controller.preferences) * 100)
        layout.addWidget(threshold)
        privacy = QCheckBox(tr('privacy_names'))
        privacy.setObjectName('hideAccountNamesInput')
        privacy.setChecked(self.controller.preferences.get('hide-account-names', False))
        layout.addWidget(privacy)
        notification_settings = self.controller.preferences.get('notifications', {})
        if not isinstance(notification_settings, dict):
            notification_settings = {}
        notify_auth = QCheckBox(tr('notify_auth_required'))
        notify_auth.setObjectName('notifyAuthRequired')
        notify_auth.setChecked(notification_settings.get('auth-required', True))
        layout.addWidget(notify_auth)
        notify_reserve = QCheckBox(tr('notify_quota_reserve'))
        notify_reserve.setObjectName('notifyQuotaReserve')
        notify_reserve.setChecked(notification_settings.get('quota-reserve', True))
        layout.addWidget(notify_reserve)
        reserve_hint = QLabel(tr('quota_reserve_explanation'))
        reserve_hint.setWordWrap(True)
        layout.addWidget(reserve_hint)
        save = QPushButton(tr('quota_display_save'))
        save.setObjectName('weeklyThresholdSave')
        def apply():
            selected_language, selected_theme = language.currentData(), theme.currentData()
            rebuild = selected_language != current_language() or selected_theme != self.theme.current
            old_notifications = self.controller.preferences.get('notifications', {})
            if not isinstance(old_notifications, dict):
                old_notifications = {}
            new_notifications = {'auth-required': notify_auth.isChecked(),
                                 'quota-reserve': notify_reserve.isChecked()}
            if new_notifications['auth-required'] and not old_notifications.get('auth-required', True):
                self.alert_tracker.clear('auth:')
            if new_notifications['quota-reserve'] and not old_notifications.get('quota-reserve', True):
                self.alert_tracker.clear('quota:')
            self.controller.preferences.update({'low-weekly-percent': threshold.value(),
                'hide-account-names': privacy.isChecked(), 'notifications': new_notifications,
                'service-visibility': {p: box.isChecked() for p, box in visibility.items()},
                'language': selected_language, 'theme': selected_theme})
            self.controller.save()
            dialog.accept()
            if rebuild:
                set_language(selected_language)
                self.theme.current = selected_theme
                self.retranslate_ui()
            else:
                self.draw_account_list()
                self.detail_account = object()
                self.draw_detail()
                self.render_activity()
                self.render_policy()
                self.render_chatgpt_accounts()
                self.claude_accounts_panel.render()
            self.apply_service_visibility()
            self.check_account_alerts()
        save.clicked.connect(apply)
        layout.addWidget(save)
        self.theme.apply(dialog)
        dialog.exec()

    # ── Theme ─────────────────────────────────────────────────────────

    def apply_mica(self):
        # Content remains opaque and uses the selected palette. DWM styles only
        # the native frame, so Windows' global theme cannot replace our surface.
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        if sys.platform == 'win32' and sys.getwindowsversion().build >= 22000:
            try:
                from ctypes import wintypes
                setter = ctypes.windll.dwmapi.DwmSetWindowAttribute
                setter.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
                setter.restype = ctypes.c_long
                dark = ctypes.c_int(self.theme.current == 'dark')
                backdrop = ctypes.c_int(2)
                setter(int(self.winId()), 20, ctypes.byref(dark), ctypes.sizeof(dark))
                setter(int(self.winId()), 38, ctypes.byref(backdrop), ctypes.sizeof(backdrop))
            except (OSError, AttributeError):
                pass

    def refresh_toolbar_icons(self):
        color = self.theme.color('text')
        self.theme_button.setText('')
        self.theme_button.setIcon(ui_icon('sun' if self.theme.current == 'dark' else 'moon', color))
        self.models_button.setText('')
        self.models_button.setIcon(ui_icon('settings', color))
        self.details_toggle.setText('')
        self.details_toggle.setIcon(ui_icon('panel', color))

    def toggle_theme(self):
        new_theme = self.theme.toggle()
        self.theme.apply(self, new_theme)
        self.apply_mica()
        self.refresh_toolbar_icons()
        self.theme.apply(self.tray_menu)
        self.controller.preferences['theme'] = new_theme
        self.controller.save()
        self.draw_account_list()
        if self.detail_account == self.selected:
            self.draw_detail()
        self.render_activity()

    # ── Language ──────────────────────────────────────────────────────

    def change_language(self, index):
        code = self.lang_combo.itemData(index)
        if code and code != current_language():
            set_language(code)
            self.controller.preferences['language'] = code
            self.controller.save()
            self.retranslate_ui()

    def retranslate_ui(self):
        size = self.size()
        view = self.view_stack.currentIndex()
        journal = list(self.journal_filter._buttons).index(self.journal_filter.get())
        # Preserve provider panels and pending OAuth work while rebuilding labels.
        self.claude_accounts_panel.setParent(None)
        self.team_panel.setParent(None)
        old = self.takeCentralWidget()
        old.hide()
        old.deleteLater()
        self._api_drawn = None
        self._account_structure = None
        self._build_ui()
        self.theme.apply(self)
        self.apply_mica()
        self.refresh_toolbar_icons()
        self.action_show.setText(tr('tray_show'))
        self.action_exit.setText(tr('tray_exit'))
        self.theme.apply(self.tray_menu)
        if self.details_collapsed:
            self.body_container.hide()
            self.sidebar.setMaximumWidth(16777215)
            self.sidebar.setMinimumWidth(SIDEBAR_WIDTH)
            self.setMinimumSize(SIDEBAR_WIDTH, 500)
        self.btn_mini.setText(tr('btn_full_mode') if self.details_collapsed else tr('btn_mini_mode'))
        self.resize(size)
        self.view_stack.setCurrentIndex(view)
        self.view_switch.set(list(self.view_switch._buttons)[view])
        self.journal_filter.set(list(self.journal_filter._buttons)[journal])
        self.detail_account = object()
        self.loaded(self.items)
        self.render_activity()
        self.add_button.setEnabled(not self.busy and not self.pending_login)
        self.pool_button.setEnabled(not self.busy)
        self.apply_service_visibility()

    def _rebuild_stats(self):
        self.stats_title.setText(tr('stats_auto_routing'))
        self.stats_note.setText(tr('stats_accounts_note'))
        self.update_button.setText(tr('btn_check_updates'))
        if hasattr(self, 'activity_state'):
            self.render_activity()

    # ── Close ─────────────────────────────────────────────────────────

    def show_window(self):
        self.showNormal()
        self.activateWindow()

    def tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_window()

    def is_autostart(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run', 0, winreg.KEY_READ)
            winreg.QueryValueEx(key, 'GeminiAccounts')
            winreg.CloseKey(key)
            return True
        except:
            return False

    def set_autostart(self, enable):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run', 0, winreg.KEY_SET_VALUE)
            if enable:
                path = Path(sys.argv[0]).resolve()
                command = f'"{path}"' if getattr(sys, 'frozen', False) else f'"{Path(sys.executable).with_name("pythonw.exe")}" "{path}"'
                winreg.SetValueEx(key, 'GeminiAccounts', 0, winreg.REG_SZ, command)
            else:
                try:
                    winreg.DeleteValue(key, 'GeminiAccounts')
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception:
            pass

    def toggle_mini_mode(self):
        self.set_compact_mode(not self.details_collapsed, on_top=True)

    def closeEvent(self, event):
        if not self.closed and QSystemTrayIcon.isSystemTrayAvailable():
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                tr('tray_minimized_title'),
                tr('tray_minimized_text'),
                QSystemTrayIcon.Information,
                2000
            )
        else:
            self._shutdown_ui()
            event.accept()

    def exit_app(self):
        self._shutdown_ui()
        self.close()
        QApplication.quit()

    def _shutdown_ui(self):
        self.team_panel.shutdown()
        self.closed = True
        self._quota_timer.stop()
        self._countdown_timer.stop()
        self._animate_timer.stop()
        self._gateway_timer.stop()
        if hasattr(self, '_vpn_timer'):
            self._vpn_timer.stop()
        self.tray_icon.hide()
        if hasattr(self, 'skel_anim'):
            self.skel_anim.stop()

    def check_vpn(self):
        if self.closed or self.vpn_check_busy:
            return
        self.vpn_check_busy = True
        self.work(self._read_vpn_state, self._vpn_state_received)

    @staticmethod
    def _read_vpn_state():
        try:
            for interface in QNetworkInterface.allInterfaces():
                flags = interface.flags()
                if not flags & QNetworkInterface.IsUp or not flags & QNetworkInterface.IsRunning:
                    continue
                name = (interface.name() + ' ' + interface.humanReadableName()).lower()
                if interface.addressEntries() and any(kw in name for kw in
                    ('windscribe', 'wireguard', 'openvpn', 'wintun', 'tap-windows', 'tun0', 'ikev2', 'tailscale')):
                    return True
            return False
        except Exception:
            return None

    def _vpn_state_received(self, active):
        self.vpn_check_busy = False
        if active is None or active == self.vpn_active:
            return
        self.vpn_active = active
        self.vpn_banner.setVisible(not active)
        if self.tray_icon.isVisible():
            self.tray_icon.showMessage(tr('vpn_status'),
                tr('vpn_connected_msg') if active else tr('vpn_disconnected_msg'),
                QSystemTrayIcon.Information if active else QSystemTrayIcon.Warning, 3000)


# ── Entry point ───────────────────────────────────────────────────────

def main():
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('GeminiAccounts.Desktop')
    ctypes.windll.kernel32.CreateMutexW.restype = ctypes.c_void_p
    ctypes.windll.kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, 'Local\\GeminiAccountsDesktop')
    if ctypes.windll.kernel32.GetLastError() == 183:
        ctypes.windll.user32.MessageBoxW(None, tr('already_running'), tr('app_title'), 0)
        return
    try:
        app = QApplication(sys.argv)
        app.setStyle('Fusion')
        window = App()
        window.show()
        sys.exit(app.exec())
    finally:
        ctypes.windll.kernel32.CloseHandle(mutex)


if __name__ == '__main__':
    main()
