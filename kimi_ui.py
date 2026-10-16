"""Kimi account pool using the shared device-login account panel."""
from PySide6.QtWidgets import QInputDialog
from grok_ui import GrokAccountsPanel
from kimi_auth import KimiAuth


class KimiAccountsPanel(GrokAccountsPanel):
    AUTH = KimiAuth
    KIND = 'kimi'
    TITLE = 'tab_kimi_accounts'

    def __init__(self, host):
        self.domain = 'kimi.com'
        super().__init__(host)

    def auth(self):
        return KimiAuth(self.host.controller, self.domain)

    def add_account(self):
        if self.busy or self.pending_login or self.host.busy:
            return
        domain, accepted = QInputDialog.getItem(self, 'Kimi Code', 'Domain', ['kimi.com', 'kimi.ai'], 0, False)
        if accepted:
            self.domain = domain
            super().add_account()
