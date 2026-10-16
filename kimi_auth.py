"""Kimi Code device sign-in and isolated client routes for .com and .ai."""
import hashlib
import re

from grok_auth import GrokAuth


def desktop_model_id(model, provider='kimi'):
    ident = int.from_bytes(hashlib.sha256((provider + '/' + model).encode()).digest()[:12], 'big')
    return f'claude-sonnet-4-5-provider-{ident}'


def is_desktop_model(model):
    return isinstance(model, str) and bool(re.fullmatch(r'claude-sonnet-4-5-provider-\d{1,29}', model))


class KimiAuth(GrokAuth):
    NAME = 'Kimi'
    SAFE_LOGIN_HOSTS = {'kimi.com', 'www.kimi.com', 'auth.kimi.com', 'kimi.ai', 'www.kimi.ai', 'auth.kimi.ai'}

    def __init__(self, controller, domain='kimi.com'):
        super().__init__(controller)
        self.PROVIDER = 'kimi-ai' if domain == 'kimi.ai' else 'kimi'
        self.AUTH_PATH = '/kimi-ai-auth-url' if domain == 'kimi.ai' else '/kimi-auth-url'

    def accounts(self):
        files = self.controller.request('/auth-files').get('files', [])
        return [{key: row[key] for key in self.ACCOUNT_FIELDS if key in row} for row in files
                if isinstance(row, dict) and row.get('provider', row.get('type')) in ('kimi', 'kimi-ai')
                and not row.get('runtime_only') and row.get('source') != 'memory']
