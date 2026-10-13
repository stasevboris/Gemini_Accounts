"""Claude subscription account panel for the Qt application."""
import time
import urllib.parse
from datetime import datetime, timezone

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel,
    QPushButton, QFrame, QDialog, QMessageBox, QFileDialog, QLineEdit)

from account_status import account_status, safe_detail
from auth_browser import open_authorization_tab
from backend import AccountError
from claude_auth import ClaudeAuth
from locales import tr
from widgets import QuotaBar
from policy_ui import SubscriptionCards
from policy_widgets import ActionGrid


class ClaudeAccountsPanel(QScrollArea):
    def __init__(self, host):
        super().__init__(host)
        self.host = host
        self.rows, self.busy, self.checked, self.drawn, self.login_dialog = [], False, 0, None, None
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)
        self.title = QLabel()
        self.title.setFont(QFont('Segoe UI', 22, QFont.Bold))
        layout.addWidget(self.title)
        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        controls = ActionGrid()
        self.buttons = []
        for key, callback in (('claude_add', self.add_account), ('claude_import', self.import_account),
                              ('chatgpt_refresh', lambda: self.refresh(force=True))):
            button = QPushButton()
            button.clicked.connect(callback)
            controls.addWidget(button)
            self.buttons.append((key, button))
        layout.addWidget(controls)
        self.cards = SubscriptionCards(host, 'claude', [
            ('api_pause', self.toggle_account), ('chatgpt_check', self.check_account), ('chatgpt_remove', self.remove_account)])
        self.cards_layout = self.cards.body_layout
        layout.addWidget(self.cards)
        layout.addStretch()
        self.setWidget(content)
        self.render()

    def refresh(self, force=False):
        host = self.host
        if host.closed or not host.controller.key or self.busy:
            return
        if not force and time.monotonic() - self.checked < 60:
            return
        self.busy = True
        def load():
            try:
                return ClaudeAuth(host.controller).accounts_with_quotas(maintain_pool=True), None
            except Exception as error:
                return None, safe_detail(error) if isinstance(error, AccountError) else tr('action_generic_error')
        def done(result):
            self.busy, self.checked = False, time.monotonic()
            rows, error = result
            if error:
                host.show_notice(error, 'warning')
                return
            self.rows = rows
            host.account_uptime.update_many('claude', rows)
            for account in rows:
                quota = account.get('quota') or {}
                host.token_capacity.observe_quota('claude', account['name'], quota.get('plan_type') or account.get('plan_type'),
                                                  host.token_capacity.oauth_groups('claude', quota))
            host.check_account_alerts()
            self.render()
            host.render_token_capacity()
        host.work(load, done)

    def render(self):
        self.title.setText(tr('tab_claude_accounts'))
        self.note.setText(tr('claude_note'))
        for key, button in self.buttons:
            button.setText(tr(key))
        self.cards.render(self.rows)

    def changed(self):
        self.refresh(force=True)
        self.host.work(self.host.integrations.refresh_desktop_model_labels,
                       lambda _: self.host.show_notice(tr('chatgpt_login_done')))

    def toggle_account(self, account):
        self.host.work(lambda: self.host.controller.request('/auth-files/status', 'PATCH',
                       {'name': account['name'], 'disabled': not account.get('disabled')}),
                       lambda _: self.changed(), mutation=True)

    def remove_account(self, account):
        if QMessageBox.question(self, tr('chatgpt_remove'),
                tr('chatgpt_remove_confirm', name=self.host.display_name(account)),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.host.work(lambda: self.host.controller.request('/auth-files?' + urllib.parse.urlencode({'name': account['name']}), 'DELETE'),
                       lambda _: self.changed(), mutation=True)

    def check_account(self, account):
        def done(model):
            self.host.show_notice(tr('claude_check_ok', model=model))
            getattr(self.host.controller, '_claude_usage_cache', {}).pop(account['name'], None)
            self.refresh(force=True)
        self.host.work(lambda: ClaudeAuth(self.host.controller).probe(account), done, mutation=True)

    def import_account(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('claude_import'), '', 'JSON (*.json)')
        if path:
            self.host.work(lambda: ClaudeAuth(self.host.controller).import_file(path), lambda _: self.changed(), mutation=True)

    def add_account(self):
        if self.login_dialog:
            self.login_dialog.raise_()
            return
        auth = ClaudeAuth(self.host.controller)
        def ready(result):
            url, state = result
            try:
                open_authorization_tab(url, provider='claude')
            except AccountError as error:
                self.host.work(lambda: auth.cancel_login(state), lambda _: None)
                self.host.show_notice(safe_detail(error), 'warning')
                return
            dialog = QDialog(self)
            dialog.setWindowTitle(tr('claude_add'))
            dialog.setMinimumWidth(470)
            layout = QVBoxLayout(dialog)
            info = QLabel(tr('claude_login_wait'))
            info.setWordWrap(True)
            layout.addWidget(info)
            callback = QLineEdit()
            callback.setEchoMode(QLineEdit.Password)
            callback.setPlaceholderText(tr('claude_callback_hint'))
            callback.setObjectName('claudeOAuthCallback')
            layout.addWidget(callback)
            submit = QPushButton(tr('claude_callback_submit'))
            def submit_code():
                text = callback.text().strip()
                if not text:
                    return
                submit.setEnabled(False)
                def load():
                    try:
                        auth.submit_callback(text, state)
                        return None
                    except AccountError as error:
                        return safe_detail(error)
                def done(error):
                    if self.login_dialog is not dialog:
                        return
                    submit.setEnabled(True)
                    if error:
                        info.setText(error)
                    else:
                        callback.clear()
                self.host.work(load, done, mutation=True)
            submit.clicked.connect(submit_code)
            layout.addWidget(submit)
            cancel = QPushButton(tr('chatgpt_cancel'))
            cancel.clicked.connect(dialog.reject)
            layout.addWidget(cancel)
            timer = QTimer(dialog)
            started, pending, completed = time.monotonic(), [False], [False]
            def finish(_):
                timer.stop()
                self.login_dialog = None
                if not completed[0]:
                    self.host.work(lambda: auth.cancel_login(state), lambda _: None)
            dialog.finished.connect(finish)
            def poll():
                if pending[0]:
                    return
                if time.monotonic() - started > 300:
                    dialog.reject()
                    return
                pending[0] = True
                def load():
                    try:
                        return auth.login_status(state), None
                    except AccountError as error:
                        return {}, safe_detail(error)
                def checked(result):
                    pending[0] = False
                    if self.login_dialog is not dialog:
                        return
                    status, error = result
                    if error:
                        info.setText(error)
                    elif status.get('status') == 'ok':
                        completed[0] = True
                        dialog.accept()
                        self.changed()
                    elif status.get('status') == 'error':
                        info.setText(safe_detail(status.get('error') or tr('action_generic_error')))
                self.host.work(load, checked)
            timer.timeout.connect(poll)
            timer.start(1500)
            self.login_dialog = dialog
            dialog.open()
        self.host.work(auth.begin_login, ready, mutation=True)
