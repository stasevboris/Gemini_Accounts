"""Persistent credential-availability uptime, without changing account routing state."""
import hashlib
import json
import math
import threading
import time
from datetime import datetime

from account_status import account_status
from backend import atomic_write


_AUTH_LOSS = {'Account blocked', 'Sign in again'}
_RESUMABLE = {'Available', 'Paused', 'Limit exhausted', 'Rate limited',
              'Waiting to retry', 'Model quota restricted'}


class AccountUptime:
    """Track how long OAuth credentials remain valid; never pause accounts."""

    def __init__(self, path):
        self.path = path
        self._lock = threading.RLock()
        try:
            value = json.loads(path.read_text('utf-8'))
            self.state = value if isinstance(value, dict) and isinstance(value.get('accounts'), dict) else {}
        except (OSError, ValueError, TypeError):
            self.state = {}
        if not isinstance(self.state.get('accounts'), dict):
            self.state = {'schema_version': 1, 'accounts': {}}
        self.state.setdefault('schema_version', 1)

    @staticmethod
    def _key(provider, name):
        raw = (str(provider) + '\0' + str(name)).encode('utf-8', 'replace')
        return hashlib.sha256(raw).hexdigest()[:24]

    @staticmethod
    def _created_at(value, now):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return min(now, float(value))
        if isinstance(value, str) and value:
            try:
                return min(now, datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp())
            except (ValueError, TypeError, OverflowError, OSError):
                pass
        return now

    @staticmethod
    def _duration(seconds):
        minutes = max(0, int(seconds // 60))
        days, hours, minutes = minutes // 1440, minutes // 60 % 24, minutes % 60
        return f'{days}d {hours}h' if days else f'{hours}h {minutes:02}m'

    def update(self, provider, account, now=None):
        """Refresh one account's state; transient failures do not stop the timer."""
        now = time.time() if now is None else float(now)
        name = account.get('name')
        if not name:
            return None
        label, _, _ = account_status(account, now)
        auth_lost = label in _AUTH_LOSS
        key = self._key(provider, name)
        changed = False
        with self._lock:
            entry = self.state['accounts'].get(key)
            if not isinstance(entry, dict):
                entry = None
            if entry is None:
                running_since = (self._created_at(account.get('created_at'), now)
                                 if label in _RESUMABLE else None)
                entry = {'provider': str(provider), 'seconds': 0.0,
                         'running_since': running_since, 'last_state': label}
                self.state['accounts'][key] = entry
                changed = True
            else:
                running_since = entry.get('running_since')
                if auth_lost and running_since is not None:
                    entry['seconds'] = max(0.0, float(entry.get('seconds', 0)) + now - float(running_since))
                    entry['running_since'] = None
                    changed = True
                elif not auth_lost and running_since is None and label in _RESUMABLE:
                    # A confirmed healthy or quota-limited status resumes the
                    # credential timer. Network errors and unknown states do not.
                    entry['running_since'] = now
                    changed = True
                if entry.get('last_state') != label:
                    entry['last_state'] = label
                    changed = True
            if changed:
                self._save_locked()
            return self._display_entry(entry, now)

    def update_many(self, provider, accounts, now=None):
        now = time.time() if now is None else float(now)
        return {account['name']: self.update(provider, account, now)
                for account in accounts if isinstance(account, dict) and account.get('name')}

    def display(self, provider, name, now=None):
        now = time.time() if now is None else float(now)
        key = self._key(provider, name)
        with self._lock:
            entry = self.state['accounts'].get(key)
            return self._display_entry(entry, now) if entry else None

    @classmethod
    def _display_entry(cls, entry, now):
        if not entry:
            return None
        try:
            seconds = float(entry.get('seconds', 0) or 0)
        except (TypeError, ValueError, OverflowError):
            seconds = 0.0
        if not math.isfinite(seconds) or seconds < 0:
            seconds = 0.0
        running_since = entry.get('running_since')
        try:
            running_since = float(running_since) if running_since is not None else None
        except (TypeError, ValueError, OverflowError):
            running_since = None
        running = running_since is not None and math.isfinite(running_since)
        if running:
            seconds += max(0.0, now - running_since)
        return {'text': cls._duration(seconds), 'seconds': seconds, 'running': running,
                'confirmed_auth_loss': not running and entry.get('last_state') in _AUTH_LOSS,
                'state': entry.get('last_state', 'Unknown')}

    def _save_locked(self):
        atomic_write(self.path, json.dumps(self.state, ensure_ascii=False).encode('utf-8'))
