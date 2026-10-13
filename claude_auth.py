"""Separate Claude subscription credentials, usage and native gateway routes."""
import hashlib
import json
import math
import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from backend import AccountError
from chatgpt_auth import ChatGPTAuth


def desktop_model_id(model):
    tier = 'opus' if 'opus' in model else 'haiku' if 'haiku' in model else 'sonnet'
    ident = int.from_bytes(hashlib.sha256(model.encode()).digest()[:12], 'big')
    return f'claude-{tier}-4-5-subscription-{ident}'


def is_desktop_model(model):
    return isinstance(model, str) and bool(re.fullmatch(r'claude-(?:opus|haiku|sonnet)-4-5-subscription-\d{1,29}', model))


def quota_windows(data):
    windows = []
    for key, label in (('five_hour', '5h'), ('seven_day', '1w'),
                       ('seven_day_opus', 'Opus · 1w'), ('seven_day_sonnet', 'Sonnet · 1w'),
                       ('seven_day_oauth_apps', 'OAuth · 1w')):
        value = data.get(key)
        if not isinstance(value, dict):
            continue
        used = value.get('utilization')
        if isinstance(used, bool) or not isinstance(used, (int, float)) or not math.isfinite(used):
            continue
        try:
            reset = datetime.fromisoformat(value['resets_at'].replace('Z', '+00:00'))
            if reset.tzinfo is None:
                raise ValueError()
            reset = reset.timestamp()
        except (KeyError, ValueError, TypeError, AttributeError, OverflowError, OSError):
            reset = None
        windows.append({'label': label, 'remaining': 100 - min(100, max(0, used)), 'reset_at': reset})
    return windows


def credential(raw, profile=None):
    if not isinstance(raw, dict):
        raise AccountError('Choose a Claude OAuth JSON file.')
    tokens = raw if raw.get('type') == 'claude' else raw.get('claudeAiOauth')
    if not isinstance(tokens, dict):
        raise AccountError('This file is not a Claude account sign-in.')
    access = tokens.get('access_token') or tokens.get('accessToken')
    refresh = tokens.get('refresh_token') or tokens.get('refreshToken')
    if any(not isinstance(v, str) or not v.strip() for v in (access, refresh)):
        raise AccountError('The file has no complete Claude OAuth tokens.')
    profile = profile or {}
    account = profile.get('account') or {}
    org = profile.get('organization') or {}
    if not isinstance(account, dict) or not isinstance(org, dict):
        raise AccountError('Claude returned invalid account details.')
    email = raw.get('email') or account.get('email')
    if email is not None and (not isinstance(email, str) or not email.strip()):
        raise AccountError('The Claude account email is invalid.')
    expire = tokens.get('expired') or tokens.get('expiresAt') or ''
    if isinstance(expire, (int, float)) and not isinstance(expire, bool):
        try:
            expire = datetime.fromtimestamp(expire / 1000, timezone.utc).isoformat()
        except (ValueError, OverflowError, OSError):
            expire = ''
    return {'type': 'claude', 'access_token': access, 'refresh_token': refresh,
            'email': email or '', 'account_uuid': raw.get('account_uuid') or account.get('uuid') or '',
            'organization_uuid': raw.get('organization_uuid') or org.get('uuid') or '',
            'expired': expire if isinstance(expire, str) else '',
            'last_refresh': datetime.now(timezone.utc).isoformat()}


class ClaudeAuth(ChatGPTAuth):
    provider = 'claude'

    def apply_reset_priority(self, accounts):
        # An OAuth-app weekly cap applies to the entire subscription pool;
        # Opus/Sonnet-specific windows must not exclude their sibling models.
        ranked = []
        for account in accounts:
            quota = account.get('quota') or {}
            windows = quota.get('windows') or []
            weekly = [w for w in windows if w.get('label') in ('1w', 'OAuth · 1w')]
            selected = [w for w in windows if w.get('label') == '5h']
            if weekly:
                cap = min(weekly, key=lambda w: w['remaining'])
                selected.append({**cap, 'label': '1w'})
            ranked.append({**account, 'quota': {**quota, 'windows': selected}})
        return super().apply_reset_priority(ranked)

    def begin_login(self):
        result = self.controller.request('/anthropic-auth-url?is_webui=true')
        url, state = result.get('url', ''), result.get('state', '')
        parts = urllib.parse.urlsplit(url)
        query = urllib.parse.parse_qs(parts.query)
        if (parts.scheme != 'https' or parts.hostname != 'claude.ai' or parts.path != '/oauth/authorize'
                or parts.username or parts.password or not state or query.get('state') != [state]):
            if state:
                self.cancel_login(state)
            raise AccountError('The gateway did not provide a safe Claude sign-in page.')
        return url, state

    def submit_callback(self, text, state):
        text = text.strip()
        if text.startswith(('http://', 'https://')):
            parts = urllib.parse.urlsplit(text)
            if parts.username or parts.password or parts.hostname not in ('localhost', '127.0.0.1', 'platform.claude.com', 'console.anthropic.com'):
                raise AccountError('Paste the Claude authorization result.')
            query = urllib.parse.parse_qs(parts.query)
            code = query.get('code', [''])[0]
            returned_state = query.get('state', [''])[0]
        else:
            code, separator, returned_state = text.partition('#')
            if not separator:
                returned_state = state
        if not code or returned_state != state:
            raise AccountError('The authorization result does not match this sign-in.')
        return self.controller.request('/oauth-callback', 'POST', {'provider': 'anthropic', 'code': code, 'state': state})

    def accounts_with_quotas(self, maintain_pool=False):
        accounts = self.accounts()
        eligible = [a for a in accounts if not a.get('disabled') and a.get('auth_index')]
        def load(account):
            try:
                quota = self.quota(account)
                self.sync_reserve(account, quota)
                return quota
            except (AccountError, ValueError, TypeError):
                quota = {'windows': [], 'error': 'Claude quota unavailable'}
                self.sync_reserve(account, quota)
                return quota
        if eligible:
            with ThreadPoolExecutor(max_workers=min(2, len(eligible))) as pool:
                for account, quota in zip(eligible, pool.map(load, eligible)):
                    account['quota'] = quota
        if maintain_pool and eligible:
            self.apply_reset_priority(accounts)
        return accounts

    @staticmethod
    def headers():
        return {'Authorization': 'Bearer $TOKEN$', 'anthropic-beta': 'oauth-2025-04-20',
                'anthropic-version': '2023-06-01', 'Content-Type': 'application/json'}

    def api_call(self, account, url, method='GET', data=None):
        payload = {'auth_index': account['auth_index'], 'method': method, 'url': url, 'header': self.headers()}
        if data is not None:
            payload['data'] = json.dumps(data)
        result = self.controller.request('/api-call', 'POST', payload)
        if result.get('status_code') != 200:
            raise AccountError('Claude rejected the request (HTTP ' + str(result.get('status_code') or '?') + ').')
        value = result.get('body')
        value = json.loads(value) if isinstance(value, str) else value
        if not isinstance(value, dict):
            raise AccountError('Claude returned an invalid response.')
        return value

    def quota(self, account):
        # The usage endpoint has its own rate limit; do not poll it every GUI tick.
        cache = getattr(self.controller, '_claude_usage_cache', None)
        if cache is None:
            cache = self.controller._claude_usage_cache = {}
        cached = cache.get(account['name'])
        if cached and time.monotonic() < cached[0]:
            return cached[1]
        try:
            usage = self.api_call(account, 'https://api.anthropic.com/api/oauth/usage')
            windows = quota_windows(usage)
            quota = {'windows': windows}
            if not windows:
                quota['error'] = 'Claude did not return quota data'
            try:
                profile = self.api_call(account, 'https://api.anthropic.com/api/oauth/profile')
                org, identity = profile.get('organization') or {}, profile.get('account') or {}
                if isinstance(org, dict) and isinstance(identity, dict):
                    quota['plan_type'] = 'Max' if identity.get('has_claude_max') else 'Pro' if identity.get('has_claude_pro') else org.get('organization_type')
            except (AccountError, ValueError, TypeError):
                pass
            cache[account['name']] = time.monotonic() + 300, quota
            return quota
        except (AccountError, ValueError, TypeError):
            quota = {'windows': [], 'error': 'Claude quota unavailable'}
            cache[account['name']] = time.monotonic() + 60, quota
            return quota

    def probe(self, account):
        if account.get('disabled'):
            raise AccountError('Enable this Claude account before testing it.')
        models = self.controller.oauth_model_choices('claude', 'claude-', [account])
        if not models:
            raise AccountError('This Claude account has no available text model.')
        model = min(models, key=lambda m: (0 if 'haiku' in m else 1 if 'sonnet' in m else 2, m))
        value = self.api_call(account, 'https://api.anthropic.com/v1/messages', 'POST',
                              {'model': model, 'max_tokens': 16, 'messages': [{'role': 'user', 'content': 'Reply with OK.'}]})
        if not any(b.get('type') == 'text' and str(b.get('text', '')).strip() for b in value.get('content') or [] if isinstance(b, dict)):
            raise AccountError('Claude returned no text in the test response.')
        return model

    def import_file(self, path):
        try:
            raw = json.loads(Path(path).read_text('utf-8-sig'))
        except (OSError, ValueError):
            raise AccountError('Could not read the selected Claude JSON file.') from None
        converted = credential(raw)
        if not converted['email']:
            result = self.controller.request('/api-call', 'POST', {
                'method': 'GET', 'url': 'https://api.anthropic.com/api/oauth/profile',
                'header': {**self.headers(), 'Authorization': 'Bearer ' + converted['access_token']}})
            if result.get('status_code') != 200:
                raise AccountError('Claude could not verify this imported sign-in.')
            profile = result.get('body')
            try:
                converted = credential(raw, json.loads(profile) if isinstance(profile, str) else profile)
            except (ValueError, TypeError):
                raise AccountError('Claude returned invalid account details.') from None
        identity = converted['account_uuid'] or converted['email']
        if not identity:
            raise AccountError('The Claude account identity is missing.')
        identity += ':' + converted['organization_uuid']
        name = 'claude-import-' + hashlib.sha256(identity.encode()).hexdigest()[:16] + '.json'
        self.controller.upload_auth_file(name, json.dumps(converted).encode())
        if not any(a['name'] == name for a in self.accounts()):
            raise AccountError('The gateway did not activate this Claude account.')
        return name
