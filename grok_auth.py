"""Grok/xAI OAuth account access through the local CLIProxyAPI management API."""
import urllib.parse

from backend import AccountError


class GrokAuth:
    PROVIDER = 'xai'
    SAFE_LOGIN_HOSTS = {'accounts.x.ai', 'auth.x.ai'}
    ACCOUNT_FIELDS = ('name', 'auth_index', 'provider', 'type', 'email', 'disabled',
                      'status', 'status_message', 'unavailable', 'cooldowns', 'created_at', 'priority',
                      'plan_type', 'source', 'runtime_only')

    def __init__(self, controller):
        self.controller = controller

    def accounts(self):
        files = self.controller.request('/auth-files').get('files', [])
        if not isinstance(files, list):
            return []
        result = []
        for account in files:
            if not isinstance(account, dict):
                continue
            if account.get('provider', account.get('type')) != self.PROVIDER:
                continue
            if account.get('runtime_only') or account.get('source') == 'memory':
                continue
            result.append({key: account.get(key) for key in self.ACCOUNT_FIELDS if key in account})
        return result

    def models(self, account):
        if not account.get('name'):
            return []
        path = '/auth-files/models?' + urllib.parse.urlencode({'name': account['name']})
        entries = self.controller.request(path).get('models', [])
        if not isinstance(entries, list):
            return []
        return sorted({entry['id'] for entry in entries
                       if isinstance(entry, dict) and isinstance(entry.get('id'), str)})

    def begin_login(self):
        try:
            result = self.controller.request('/xai-auth-url?is_webui=true')
        except AccountError as error:
            if '404' in str(error):
                raise AccountError('This local gateway does not support Grok sign-in. Update the app and retry.') from None
            raise
        url = result.get('url', '')
        state = result.get('state', '')
        if not isinstance(url, str) or len(url) > 4096 or not isinstance(state, str) or not state or len(state) > 1024:
            raise AccountError('The gateway did not provide a safe Grok sign-in page.')
        parts = urllib.parse.urlsplit(url)
        url_states = urllib.parse.parse_qs(parts.query, keep_blank_values=True).get('state')
        if (parts.scheme != 'https' or parts.hostname not in self.SAFE_LOGIN_HOSTS
                or parts.username or parts.password or parts.fragment
                or (url_states is not None and url_states != [state])):
            if state:
                try:
                    self.cancel_login(state)
                except AccountError:
                    pass
            raise AccountError('The gateway did not provide a safe Grok sign-in page.')
        user_code = result.get('user_code') or result.get('code') or ''
        if not isinstance(user_code, str):
            user_code = ''
        try:
            lifetime = min(1800, max(60, int(result.get('expires_in') or 900)))
        except (TypeError, ValueError, OverflowError):
            lifetime = 900
        return {'url': url, 'state': state, 'user_code': user_code[:80], 'expires_in': lifetime}

    def login_status(self, state):
        return self.controller.request('/get-auth-status?' + urllib.parse.urlencode({'state': state}))

    def cancel_login(self, state):
        return self.controller.request('/oauth-session?' + urllib.parse.urlencode({'state': state}), 'DELETE')

    @staticmethod
    def quota(account):
        """xAI does not publish a 5h/weekly meter through this gateway API."""
        return {'windows': [], 'plan_type': account.get('plan_type') or 'Plan unknown'}
