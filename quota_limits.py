"""Per-account quota reserves; preserve existing native model exclusions.

Adapted from nikitaeight24family/Omni at 1b7c6ac (MIT).
"""
import math
import threading
import urllib.parse

_lock = threading.RLock()
quota_policy_lock = _lock
_owned = 'gemini_accounts_quota_exclusions'
PATTERNS = {'gemini': ['gemini*'], 'claude': ['claude*', 'gpt-oss*'],
            'openai': ['*'], 'claude-opus': ['claude-opus*'], 'claude-sonnet': ['claude-sonnet*']}


def account_priority(preferences, name):
    values = preferences.get('account-priorities', {})
    value = values.get(name, 0) if isinstance(values, dict) else 0
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 999 else 0


def quota_floor(preferences, name, group, window):
    limits = preferences.get('quota-floors', {})
    account = limits.get(name, {}) if isinstance(limits, dict) else {}
    family = account.get(group, {}) if isinstance(account, dict) else {}
    value = family.get(window, 0) if isinstance(family, dict) else 0
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100 else 0


def blocked_families(preferences, name, groups):
    indexed = {g['kind']: {b.get('window'): b for b in g.get('buckets', [])} for g in groups}
    limits = preferences.get('quota-floors', {})
    configured = limits.get(name, {}) if isinstance(limits, dict) else {}
    blocked = set()
    for kind in set(indexed) | (set(configured) if isinstance(configured, dict) else set()):
        for window in ('5h', 'weekly', 'oauth_weekly'):
            floor = quota_floor(preferences, name, kind, window)
            remaining = indexed.get(kind, {}).get(window, {}).get('remaining')
            if floor and (not isinstance(remaining, (int, float)) or isinstance(remaining, bool)
                          or not math.isfinite(remaining) or not 0 <= remaining <= 1
                          or remaining * 100 <= floor + 1e-7):
                blocked.add(kind)
    return blocked


def sync_quota_limits(controller, account, groups, clear=False):
    """Change only reserve-owned exclusions; never disable accounts or log auth."""
    configured = controller.preferences.get('quota-floors', {})
    if not clear and (not isinstance(configured, dict) or account['name'] not in configured):
        return set()
    with _lock:
        blocked = set() if clear else blocked_families(controller.preferences, account['name'], groups)
        desired = sorted({p for kind in blocked for p in PATTERNS.get(kind, [])})
        metadata = controller.request('/auth-files/download?' + urllib.parse.urlencode({'name': account['name']}))
        original = metadata.get('excluded_models', metadata.get('excluded-models', [])) or []
        managed = metadata.get(_owned, []) or []
        if not isinstance(original, list) or not all(isinstance(p, str) for p in original):
            raise ValueError('Invalid native model exclusions')
        managed = managed if isinstance(managed, list) else []
        base = [p for p in original if p not in managed]
        merged = sorted(set(base + desired))
        owned = [p for p in desired if p not in base]
        if merged != sorted(original) or owned != sorted(managed):
            controller.request('/auth-files/fields', 'PATCH', {
                'name': account['name'], 'excluded_models': merged, _owned: owned})
        return blocked


def clear_quota_limits(controller):
    """Clear reserve-owned rules before resetting preferences."""
    configured = controller.preferences.get('quota-floors', {})
    if not isinstance(configured, dict) or not configured:
        return
    for account in controller.request('/auth-files').get('files', []):
        if account.get('name') in configured:
            sync_quota_limits(controller, account, [], clear=True)


def oauth_quota_groups(quota, provider):
    groups = {}
    for w in quota.get('windows', []):
        label = w.get('label')
        kind, window = oauth_window_key(label, provider)
        if window:
            value = w.get('remaining')
            fraction = value / 100 if isinstance(value, (int, float)) and not isinstance(value, bool) else None
            groups.setdefault(kind, []).append({'window': window, 'remaining': fraction,
                                                 'reset': w.get('reset_at')})
    return [{'kind': kind, 'buckets': buckets} for kind, buckets in groups.items()]


def oauth_window_key(label, provider):
    group = 'openai' if provider == 'codex' else 'claude'
    if label in ('Opus · 1w', 'Sonnet · 1w') and provider == 'claude':
        return ('claude-opus' if label.startswith('Opus') else 'claude-sonnet'), 'weekly'
    return group, {'5h': '5h', '1w': 'weekly', 'OAuth · 1w': 'oauth_weekly'}.get(label)
