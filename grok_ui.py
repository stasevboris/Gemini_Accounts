"""Grok account pool for the PySide6 application."""
import time
import urllib.parse
import webbrowser
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from account_status import safe_detail
from backend import AccountError
from grok_auth import GrokAuth
from locales import tr
from policy_ui import SubscriptionCards
from policy_widgets import ActionGrid


class GrokAccountsPanel(QScrollArea):
    AUTH = GrokAuth
    KIND = 'grok'
    TITLE = 'tab_grok_accounts'

    def text(self, key, **kwargs):
        return tr(key.replace('grok_', self.KIND + '_', 1), **kwargs)

    def auth(self):
        return self.AUTH(self.host.controller)

    def __init__(self, host):
        super().__init__(host)
        self.host = host
        self.rows = []
        self.busy = False
        self.checked = 0
        self.login_dialog = None
        self.pending_login = None
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)
        self.title = QLabel()
        self.title.setFont(QFont('Segoe UI', 22, QFont.Bold))
        layout.addWidget(self.title)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setProperty('class', 'muted')
        layout.addWidget(self.note)
        controls = ActionGrid()
        self.add_button = QPushButton()
        self.add_button.clicked.connect(self.add_account)
        controls.addWidget(self.add_button)
        self.refresh_button = QPushButton()
        self.refresh_button.clicked.connect(lambda: self.refresh(force=True))
        controls.addWidget(self.refresh_button)
        layout.addWidget(controls)
        self.cards = SubscriptionCards(host, self.KIND, [
            ('api_pause', self.toggle_account),
            ('chatgpt_remove', self.remove_account)], quota_labels=[])
        layout.addWidget(self.cards)
        layout.addStretch()
        self.setWidget(content)
        self.render()

    def render(self):
        self.title.setText(tr(self.TITLE))
        self.note.setText(self.text('grok_note'))
        self.add_button.setText(self.text('grok_add'))
        self.refresh_button.setText(self.text('grok_refresh'))
        self.cards.render(self.rows)

    def refresh(self, force=False):
        host = self.host
        if host.closed or not host.controller.key or self.busy:
            return
        if not force and time.monotonic() - self.checked < 60:
            return
        self.busy = True
        def load():
            try:
                auth = self.auth()
                rows = auth.accounts()
                for account in rows:
                    account['quota'] = auth.quota(account)
                    try:
                        account['available_models'] = auth.models(account)
                    except AccountError:
                        account['available_models'] = []
                return rows, None
            except Exception as error:
                return None, safe_detail(error) if isinstance(error, AccountError) else tr('action_generic_error')
        def done(result):
            self.busy = False
            self.checked = time.monotonic()
            rows, error = result
            if error:
                host.show_notice(error, 'warning')
                return
            self.rows = rows or []
            for provider in {a.get('provider', a.get('type')) for a in self.rows}:
                host.account_uptime.update_many(provider, [a for a in self.rows if a.get('provider', a.get('type')) == provider])
            host.check_account_alerts()
            self.render()
            host.render_token_capacity()
        host.work(load, done)

    def changed(self):
        self.refresh(force=True)
        self.host.work(self.host.integrations.refresh_desktop_model_labels,
                       lambda _: self.host.show_notice(self.text('grok_login_saved'), 'green'))

    def toggle_account(self, account):
        host = self.host
        host.work(lambda: host.controller.request('/auth-files/status', 'PATCH', {
            'name': account['name'], 'disabled': not account.get('disabled')}),
            lambda _: self.changed(), mutation=True)

    def remove_account(self, account):
        host = self.host
        if QMessageBox.question(self, tr('chatgpt_remove'),
                tr('chatgpt_remove_confirm', name=host.display_name(account)),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        host.work(lambda: host.controller.request('/auth-files?' + urllib.parse.urlencode({'name': account['name']}), 'DELETE'),
                  lambda _: self.changed(), mutation=True)

    def add_account(self):
        if self.busy or self.pending_login or self.host.busy:
            return
        self.host.work(lambda: self.auth().begin_login(),
                       self.login_started, mutation=True)

    def login_started(self, result):
        if not isinstance(result, dict):
            self.host.show_notice(self.text('grok_login_failed'), 'warning')
            return
        self.pending_login = (result['state'], time.monotonic(), result['expires_in'])
        self.add_button.setEnabled(False)
        dialog = self.login_dialog = QDialog(self.host)
        dialog.setWindowTitle(self.text('grok_add'))
        dialog.setMinimumWidth(430)
        layout = QVBoxLayout(dialog)
        heading = QLabel(self.text('grok_login_heading'))
        heading.setFont(QFont('Segoe UI', 18, QFont.Bold))
        layout.addWidget(heading)
        note = QLabel(self.text('grok_login_note'))
        note.setWordWrap(True)
        note.setProperty('class', 'muted')
        layout.addWidget(note)
        if result.get('user_code'):
            code = QLineEdit(result['user_code'])
            code.setReadOnly(True)
            code.setEchoMode(QLineEdit.Normal)
            code.setAlignment(Qt.AlignCenter)
            code.setFont(QFont('Segoe UI', 18, QFont.Bold))
            layout.addWidget(code)
            copy = QPushButton(self.text('grok_copy_code'))
            copy.clicked.connect(lambda: QApplication.clipboard().setText(result['user_code']))
            layout.addWidget(copy)
        open_button = QPushButton(self.text('grok_open_login'))
        open_button.clicked.connect(lambda: webbrowser.open(result['url']))
        layout.addWidget(open_button)
        status = QLabel(self.text('grok_signin_pending'))
        status.setWordWrap(True)
        status.setProperty('class', 'muted')
        layout.addWidget(status)
        cancel = QPushButton(tr('chatgpt_cancel'))
        cancel.clicked.connect(lambda: self.finish_login(False, cancel=True))
        layout.addWidget(cancel)
        dialog.finished.connect(lambda _: self._dialog_closed(dialog))
        self.host.theme.apply(dialog)
        dialog.show()
        webbrowser.open(result['url'])
        QTimer.singleShot(1600, self.poll_login)

    def _dialog_closed(self, dialog):
        if self.login_dialog is dialog and self.pending_login:
            self.finish_login(False, cancel=True)

    def poll_login(self):
        if self.host.closed or not self.pending_login:
            return
        state, started, lifetime = self.pending_login
        if time.monotonic() - started > lifetime:
            self.finish_login(False, timed_out=True, cancel=True)
            return
        def load():
            try:
                return self.auth().login_status(state), None
            except AccountError as error:
                return {'status': 'wait'}, safe_detail(error)
        def done(result):
            if not self.pending_login or self.pending_login[0] != state:
                return
            value, error = result
            if value.get('status') == 'ok':
                self.finish_login(True)
            elif value.get('status') == 'error':
                self.finish_login(False)
                self.host.show_notice(self.text('grok_login_failed'), 'warning')
            else:
                QTimer.singleShot(1800, self.poll_login)
        self.host.work(load, done)

    def finish_login(self, success, timed_out=False, cancel=False):
        if not self.pending_login:
            return
        state = self.pending_login[0]
        self.pending_login = None
        dialog = self.login_dialog
        self.login_dialog = None
        self.add_button.setEnabled(True)
        if dialog is not None and dialog.isVisible():
            dialog.close()
        if not success:
            if cancel:
                self.host.work(lambda: self.auth().cancel_login(state), lambda _: None)
            if timed_out:
                self.host.show_notice(self.text('grok_login_timeout'), 'warning')
            return
        self.host.show_notice(self.text('grok_login_saved'), 'green')
        self.changed()
