"""In-memory transition detection for non-repeating tray alerts."""
import math

from account_status import account_status
from quota_limits import quota_floor


def account_alert_conditions(account, groups, preferences):
    """Return only explicit sign-in loss and measured reserve crossings."""
    name = account.get('name')
    if not name:
        return False, []
    needs_sign_in = account_status(account)[0] == 'Sign in again'
    reached = []
    for group in groups or []:
        if not isinstance(group, dict):
            continue
        kind = group.get('kind')
        if not kind:
            continue
        for bucket in group.get('buckets', []):
            if not isinstance(bucket, dict):
                continue
            window, remaining = bucket.get('window'), bucket.get('remaining')
            if (not window or isinstance(remaining, bool) or not isinstance(remaining, (int, float))
                    or not math.isfinite(remaining) or not 0 <= remaining <= 1):
                continue
            floor = quota_floor(preferences, name, kind, window) / 100
            if remaining <= floor + 1e-7:
                reached.append((kind, window, floor * 100))
    return needs_sign_in, reached


class AlertTracker:
    def __init__(self):
        self._active = set()

    def transition(self, key, active):
        """Return True only when a condition changes from clear to active."""
        if active:
            first = key not in self._active
            self._active.add(key)
            return first
        self._active.discard(key)
        return False

    def clear(self, prefix=None):
        if prefix is None:
            self._active.clear()
        else:
            self._active = {key for key in self._active if not key.startswith(prefix)}
