"""Reversible, private account-specific routes for a user-started agent team."""
import hashlib
import json
import os
import re
import threading
import time
import urllib.parse
from pathlib import Path

from backend import AccountError, atomic_write, dpapi, storage_root


def read_leases(path=None):
    path = Path(path or storage_root() / 'GeminiAccounts' / 'team-routes.dpapi')
    try:
        value = json.loads(dpapi(path.read_bytes(), decrypt=True))
        return value if isinstance(value, dict) else {}
    except FileNotFoundError:
        return {}


def route_scope(model, path=None):
    if not isinstance(model, str) or '/' not in model:
        return None
    prefix, raw = model.split('/', 1)
    if not prefix.startswith('ga-team-'):
        return None
    entry = read_leases(path).get(prefix)
    if not entry:
        raise AccountError('The agent account route is no longer active.')
    return {**entry, 'model': raw}


def team_active(data_dir=None):
    path = Path(data_dir or storage_root() / 'GeminiAccounts') / 'team-run.lock'
    if not path.exists():
        return False
    with path.open('r+b') as stream:
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return True
    return False


class AccountRoutes:
    def __init__(self, controller):
        self.controller = controller
        self.path = controller.data_dir / 'team-routes.dpapi'
        self.lock = threading.RLock()
        self.routes = {}

    def _save(self, entries):
        atomic_write(self.path, dpapi(json.dumps(entries).encode()))

    def _prefix(self, name):
        if not isinstance(name, str) or Path(name).name != name or not name.endswith('.json'):
            raise AccountError('Invalid agent account file.')
        path = self.controller.proxy_dir / 'auth' / name
        try:
            value = json.loads(path.read_text('utf-8-sig')).get('prefix')
            return value if isinstance(value, str) else ''
        except (OSError, ValueError):
            raise AccountError('The selected account is not stored locally.') from None

    def acquire(self, participant, cancelled=lambda: False):
        name, model = participant['account'], participant['model']
        with self.lock:
            if cancelled():
                raise AccountError('Team stopped.')
            prefix = self.routes.get(name)
            if prefix:
                return prefix + '/' + model
            previous = self._prefix(name)
            # If the process died after assigning the route, the durable lease
            # is the authority for this account. Re-adopt that route while the
            # current team lock is held instead of rejecting the whole run.
            leases = read_leases(self.path)
            owner = next((route for route, entry in leases.items()
                          if isinstance(entry, dict) and entry.get('name') == name), None)
            if owner and previous == owner and re.fullmatch(r'ga-team-[a-f0-9]{24}', owner):
                self.routes[name] = owner
                return owner + '/' + model
            if previous:
                raise AccountError('This account already has a custom model prefix. Choose another account for the team.')
            if self.controller.request('/force-model-prefix').get('force-model-prefix') is True:
                raise AccountError('Agent teams require optional model prefixes; disable forced prefixes in the gateway first.')
            prefix = 'ga-team-' + hashlib.sha256(name.encode()).hexdigest()[:24]
            if prefix in leases:
                raise AccountError('An unfinished team route must be restored before starting.')
            leases[prefix] = {'name': name, 'provider': participant['provider'], 'previous': previous}
            self._save(leases)
            # The lease is durable before the first change, including failures.
            self.controller.request('/auth-files/fields', 'PATCH', {'name': name, 'prefix': prefix})
            self.routes[name] = prefix
            endpoint = '/auth-files/models?' + urllib.parse.urlencode({'name': name})
            for _ in range(25):
                if cancelled():
                    raise AccountError('Team stopped.')
                models = self.controller.request(endpoint).get('models', [])
                if prefix + '/' + model in {m.get('id') for m in models if isinstance(m, dict)}:
                    return prefix + '/' + model
                time.sleep(.2)
            raise AccountError('The gateway has not published the account-specific model route.')

    def restore(self):
        errors = []
        with self.lock:
            leases = read_leases(self.path)
            for prefix, entry in list(leases.items()):
                if not re.fullmatch(r'ga-team-[a-f0-9]{24}', prefix):
                    errors.append('Invalid team route lease.')
                    continue
                try:
                    current = self._prefix(entry['name'])
                    if current == prefix:
                        self.controller.request('/auth-files/fields', 'PATCH',
                            {'name': entry['name'], 'prefix': entry.get('previous', '')})
                    elif current != entry.get('previous', ''):
                        raise AccountError('An account route changed outside this team; it was left intact.')
                    del leases[prefix]
                    self._save(leases)
                except (AccountError, KeyError) as error:
                    errors.append(str(error))
            # A process can die after the native prefix PATCH but before the
            # encrypted lease is written (or after the lease is removed).  Such
            # an orphaned team prefix must not block the next run.  The process
            # wide team lock is held by the caller, so no other local team can
            # own these temporary prefixes while this cleanup runs.
            if self.controller.key is not None:
                try:
                    files = self.controller.request('/auth-files').get('files', [])
                    leased_names = {entry.get('name') for entry in leases.values() if isinstance(entry, dict)}
                    for account in files:
                        name = account.get('name') if isinstance(account, dict) else None
                        current = account.get('prefix', '') if isinstance(account, dict) else ''
                        if not name or name in leased_names or not re.fullmatch(r'ga-team-[a-f0-9]{24}', current or ''):
                            continue
                        self.controller.request('/auth-files/fields', 'PATCH', {'name': name, 'prefix': ''})
                except (AccountError, OSError, ValueError, TypeError) as error:
                    errors.append(str(error))
            self.routes.clear()
        if errors:
            raise AccountError('\n'.join(errors))
