"""ChatGPT account controls for the PySide6 application."""
import time
import urllib.parse
from datetime import datetime, timezone
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QLabel, QPushButton, QFrame, QDialog, QMessageBox, QFileDialog)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from backend import AccountError
from chatgpt_auth import ChatGPTAuth
from account_status import account_status, safe_detail
from auth_browser import open_authorization_tab
from locales import tr
from widgets import QuotaBar
from policy_ui import SubscriptionCards
from policy_widgets import ActionGrid


class ChatGPTPanelMixin:
    def build_chatgpt_panel(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)
        title = QLabel(tr('tab_chatgpt'))
        title.setFont(QFont('Segoe UI', 22, QFont.Bold))
        layout.addWidget(title)
        note = QLabel(tr('chatgpt_note'))
        note.setWordWrap(True)
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = ActionGrid()
        for key, callback in (('chatgpt_add', self.add_chatgpt_account),
                              ('chatgpt_import', self.import_chatgpt_account),
                              ('chatgpt_refresh', lambda: self.refresh_chatgpt_accounts(force=True))):
            button = QPushButton(tr(key))
            button.clicked.connect(callback)
            buttons.addWidget(button)
        layout.addWidget(buttons)
        self.chatgpt_cards = SubscriptionCards(self, 'codex', [
            ('api_pause', self.toggle_chatgpt_account), ('chatgpt_check', self.check_chatgpt_account),
            ('chatgpt_remove', self.remove_chatgpt_account), ('chatgpt_reset', self.reset_chatgpt_quota)])
        self.chatgpt_cards_layout = self.chatgpt_cards.body_layout
        layout.addWidget(self.chatgpt_cards)
        layout.addStretch()
        scroll.setWidget(content)
        self.view_stack.addWidget(scroll)
        self.chatgpt_drawn = None
        self.render_chatgpt_accounts()

    def refresh_chatgpt_accounts(self, force=False):
        if self.closed or not self.controller.key or self.chatgpt_busy:
            return
        if not force and time.monotonic() - self.chatgpt_checked < 60:
            return
        self.chatgpt_busy = True
        def load():
            try:
                return ChatGPTAuth(self.controller).accounts_with_quotas(maintain_pool=True), None
            except Exception as error:
                return None, safe_detail(error) if isinstance(error, AccountError) else tr('action_generic_error')
        def done(result):
            self.chatgpt_busy = False
            self.chatgpt_checked = time.monotonic()
            rows, error = result
            if error:
                self.show_notice(error, 'warning')
                return
            self.chatgpt_accounts = rows
            self.account_uptime.update_many('codex', rows)
            for account in rows:
                quota = account.get('quota') or {}
                self.token_capacity.observe_quota('codex', account['name'], quota.get('plan_type') or account.get('plan_type'),
                                                  self.token_capacity.oauth_groups('codex', quota))
            self.check_account_alerts()
            self.render_chatgpt_accounts()
            self.render_token_capacity()
        self.work(load, done)

    def render_chatgpt_accounts(self):
        self.chatgpt_cards.render(self.chatgpt_accounts)

    def chatgpt_profiles_changed(self):
        self.refresh_chatgpt_accounts(force=True)
        self.work(self.integrations.refresh_desktop_model_labels,
                  lambda _: self.show_notice(tr('chatgpt_login_done')))

    def toggle_chatgpt_account(self, account):
        self.work(lambda: self.controller.request('/auth-files/status', 'PATCH',
                  {'name': account['name'], 'disabled': not account.get('disabled')}),
                  lambda _: self.chatgpt_profiles_changed(), mutation=True)

    def remove_chatgpt_account(self, account):
        if QMessageBox.question(self, tr('chatgpt_remove'),
                tr('chatgpt_remove_confirm', name=self.display_name(account)),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.work(lambda: self.controller.request('/auth-files?' + urllib.parse.urlencode({'name': account['name']}), 'DELETE'),
                  lambda _: self.chatgpt_profiles_changed(), mutation=True)

    def check_chatgpt_account(self, account):
        def done(model):
            self.show_notice(tr('chatgpt_check_ok', model=model))
            self.refresh_chatgpt_accounts(force=True)
        self.work(lambda: ChatGPTAuth(self.controller).probe(account), done, mutation=True)

    def reset_chatgpt_quota(self, account):
        if QMessageBox.question(self, tr('chatgpt_reset'),
                tr('chatgpt_reset_confirm', name=self.display_name(account)),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        def done(_):
            self.show_notice(tr('chatgpt_reset_done'))
            self.refresh_chatgpt_accounts(force=True)
        self.work(lambda: ChatGPTAuth(self.controller).use_reset_credit(account), done, mutation=True)

    def import_chatgpt_account(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('chatgpt_import'), '', 'JSON (*.json)')
        if path:
            self.work(lambda: ChatGPTAuth(self.controller).import_file(path),
                      lambda _: self.chatgpt_profiles_changed(), mutation=True)

    def add_chatgpt_account(self):
        if self.chatgpt_login_dialog:
            self.chatgpt_login_dialog.raise_()
            return
        auth = ChatGPTAuth(self.controller)
        def ready(result):
            url, state = result
            try:
                open_authorization_tab(url)
            except AccountError as error:
                self.work(lambda: auth.cancel_login(state), lambda _: None)
                self.show_notice(safe_detail(error), 'warning')
                return
            dialog = QDialog(self)
            dialog.setWindowTitle(tr('chatgpt_add'))
            dialog.setMinimumWidth(450)
            layout = QVBoxLayout(dialog)
            label = QLabel(tr('chatgpt_login_wait'))
            label.setWordWrap(True)
            layout.addWidget(label)
            cancel = QPushButton(tr('chatgpt_cancel'))
            cancel.clicked.connect(dialog.reject)
            layout.addWidget(cancel)
            timer = QTimer(dialog)
            started, pending, completed = time.monotonic(), [False], [False]
            def finish(_):
                timer.stop()
                self.chatgpt_login_dialog = None
                if not completed[0]:
                    self.work(lambda: auth.cancel_login(state), lambda _: None)
            dialog.finished.connect(finish)
            def poll():
                if pending[0]:
                    return
                if time.monotonic() - started > 600:
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
                    if self.chatgpt_login_dialog is not dialog:
                        return
                    status, error = result
                    if error or status.get('status') == 'error':
                        self.show_notice(error or safe_detail(status.get('error')), 'warning')
                        dialog.reject()
                    elif status.get('status') == 'ok':
                        completed[0] = True
                        dialog.accept()
                        self.chatgpt_profiles_changed()
                self.work(load, checked)
            timer.timeout.connect(poll)
            timer.start(1500)
            self.chatgpt_login_dialog = dialog
            self.theme.apply(dialog)
            dialog.show()
        self.work(auth.begin_login, ready, mutation=True)
