"""Independent API profiles, encrypted credentials and metadata-only usage."""
import json
import copy
import hashlib
import re
import secrets
import threading
import urllib.parse
import urllib.request
import urllib.error
import time
from contextlib import contextmanager

_PROFILE_LOCK = threading.RLock()
from datetime import datetime, timezone


def request_headers():
    from runtime import VERSION
    # Some API frontends reject urllib's default User-Agent before authentication.
    return {'User-Agent': 'GeminiAccounts/' + VERSION, 'Accept': 'application/json'}


def profile_key(controller, row):
    """Reuse a saved credential only for the same API origin."""
    from backend import AccountError
    if row.get('key'):
        return row['key']
    old = next((r for r in profiles(controller, private=True) if r['id'] == row.get('id')), {})
    if old.get('key'):
        def origin(value):
            url = urllib.parse.urlsplit(value)
            return url.scheme.lower(), (url.hostname or '').lower(), url.port or 443
        if origin(old.get('base_url', '')) != origin(row.get('base_url', '').strip()):
            raise AccountError('Enter the API key again when changing the API server.')
    return old.get('key')


def model_id(profile, model):
    return 'api/' + profile['id'] + '/' + model


def desktop_model_id(entry):
    """Opaque client route; the display label and upstream model stay explicit."""
    tier = 'haiku' if 'haiku' in entry['model'] else 'opus' if 'opus' in entry['model'] else 'sonnet'
    # Decimal digits cannot accidentally match Claude Desktop's provider blacklist.
    ident = int.from_bytes(hashlib.sha256(entry['id'].encode()).digest()[:12], 'big')
    return f'claude-{tier}-4-5-key-{ident}'


def is_desktop_model(model):
    return isinstance(model, str) and bool(re.fullmatch(r'claude-(?:haiku|opus|sonnet)-4-5-key-\d{1,29}', model))


def is_model(model):
    return isinstance(model, str) and (model.startswith('api/') or is_desktop_model(model) or model == 'claude-haiku-5.5:free')


def profiles(controller, private=False):
    from backend import dpapi, AccountError
    path = controller.data_dir / 'api-keys.dpapi'
    try:
        rows = json.loads(dpapi(path.read_bytes(), decrypt=True)).get('profiles', [])
    except FileNotFoundError:
        from tokenharbor import read_key, MODEL
        key = read_key(controller)
        rows = [{'id': 'tokenharbor', 'label': 'TokenHarbor', 'kind': 'tokenharbor',
            'base_url': 'https://tokenharbor.ai', 'key': key, 'models': [MODEL], 'enabled': True}] if key else []
    except (OSError, ValueError, AccountError):
        rows = []
    return [dict(row) if private else {k: v for k, v in row.items() if k != 'key'}
            for row in rows if private or not row.get('id', '').startswith('test-')]


def validated_profile(controller, row):
    from backend import AccountError
    row = dict(row)
    rows = profiles(controller, private=True)
    old = next((r for r in rows if r['id'] == row.get('id')), {})
    row['id'] = old.get('id') or secrets.token_hex(6)
    row['key'] = profile_key(controller, row)
    url = urllib.parse.urlsplit(row.get('base_url', '').strip().rstrip('/'))
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise AccountError('API base URL must be an HTTPS address without credentials or query parameters.')
    if not row['key'] or any(c.isspace() for c in row['key']):
        raise AccountError('Enter an API key without spaces or line breaks.')
    row['base_url'] = urllib.parse.urlunsplit(url).removesuffix('/v1')
    row['label'] = row.get('label', '').strip() or url.hostname
    row['models'] = list(dict.fromkeys(m.strip() for m in row.get('models', []) if m.strip()))
    if not row['models']:
        raise AccountError('Choose at least one API model.')
    row.setdefault('enabled', True)
    row.setdefault('kind', 'tokenharbor')
    if row['kind'] not in ('tokenharbor', 'anthropic'):
        raise AccountError('Unsupported API protocol.')
    return row


def _write_profiles(controller, rows):
    from backend import atomic_write, dpapi
    atomic_write(controller.data_dir / 'api-keys.dpapi', dpapi(json.dumps({'profiles': rows}).encode()))


def save_profile(controller, row):
    with _PROFILE_LOCK:
        row = validated_profile(controller, row)
        rows = [r for r in profiles(controller, private=True) if r['id'] != row['id']] + [row]
        _write_profiles(controller, rows)
    return row['id']


def remove_profile(controller, ident):
    with _PROFILE_LOCK:
        rows = [r for r in profiles(controller, private=True) if r['id'] != ident]
        _write_profiles(controller, rows)


@contextmanager
def temporary_profile(controller, row):
    """A unique test route leaves existing profiles and in-flight requests intact."""
    from backend import atomic_write
    path = controller.data_dir / 'api-keys.dpapi'
    with _PROFILE_LOCK:
        before = path.read_bytes() if path.exists() else None
        temporary = dict(row, id='test-' + secrets.token_hex(8), enabled=True, rotate=False)
        staged = profiles(controller, private=True) + [temporary]
        _write_profiles(controller, staged)
    try:
        yield temporary
    finally:
        with _PROFILE_LOCK:
            current = profiles(controller, private=True)
            if current == staged:
                if before is None:
                    path.unlink(missing_ok=True)
                else:
                    atomic_write(path, before)
            else:
                _write_profiles(controller, [p for p in current if p['id'] != temporary['id']])


def _probe_message(url, model, headers, stage):
    from backend import AccountError
    from response_guard import usable_message
    request = urllib.request.Request(url, data=json.dumps({'model': model, 'max_tokens': 16,
        'stream': False, 'messages': [{'role': 'user', 'content': 'Reply only OK.'}]}).encode(),
        headers={**request_headers(), **headers, 'Content-Type': 'application/json', 'anthropic-version': '2023-06-01'})
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=20) as response:
            chunks, deadline, size = [], time.monotonic() + 20, 0
            while True:
                if time.monotonic() > deadline:
                    raise TimeoutError()
                chunk = response.read1(65536)
                if not chunk:
                    break
                size += len(chunk)
                if size > 1024 * 1024:
                    raise ValueError('Test response too large')
                chunks.append(chunk)
            value = json.loads(b''.join(chunks))
            if response.status != 200 or not isinstance(value, dict) or value.get('type') != 'message' or not usable_message(value):
                raise AccountError(stage + ' returned no usable response.')
    except urllib.error.HTTPError as error:
        raise AccountError(stage + ' rejected the test (HTTP ' + str(error.code) + ').') from None
    except (OSError, ValueError):
        raise AccountError(stage + ' could not complete the connection test.') from None


def verify_profile(controller, row):
    """Check the draft at the provider and gateway without saving the user's edits."""
    from backend import AccountError
    row = validated_profile(controller, row)
    headers = {'x-api-key': row['key']} if row['kind'] == 'anthropic' else {'Authorization': 'Bearer ' + row['key']}
    _probe_message(row['base_url'] + '/v1/messages', row['models'][0], headers, 'API provider')
    try:
        local_key = (controller.proxy_dir / 'client-key.txt').read_text('utf-8-sig').strip()
    except OSError:
        raise AccountError('The local gateway is not installed.') from None
    with temporary_profile(controller, row) as temporary:
        _probe_message('http://127.0.0.1:8317/v1/messages', model_id(temporary, row['models'][0]),
                       {'Authorization': 'Bearer ' + local_key}, 'Local gateway')
    return {'provider': True, 'gateway': True, 'model': row['models'][0]}


def resolve(rows, model):
    for row in rows:
        if not row.get('enabled', True):
            continue
        for raw in row.get('models', []):
            ident = model_id(row, raw)
            if model in (ident, desktop_model_id({'id': ident, 'model': raw})) or (model == 'claude-haiku-5.5:free' and raw == model):
                return row, raw
    return None, None


def catalog(controller):
    return catalog_rows(profiles(controller))


def credential_tag(row):
    """Invalidate stale cooldowns after a credential or endpoint is edited."""
    return hashlib.sha256(json.dumps([row.get('key'), row.get('base_url'), row.get('kind')]).encode()).hexdigest()[:24]


def failure_state(status, body=b''):
    """Do not confuse request concurrency/rate limits with depleted credits."""
    from provider_errors import unpack_error
    error = unpack_error(body)
    detail = str(error.get('message', '')).lower()
    code = str(error.get('code') or error.get('type') or '').lower()
    if status == 402 or any(word in code + ' ' + detail for word in (
            'insufficient_quota', 'insufficient_balance', 'credit balance is too low',
            'insufficient credits', 'quota exhausted', 'quota_exhausted', 'tokens exhausted',
            'billing_hard_limit', 'out of credits', 'balance exhausted')):
        return 'exhausted'
    if status == 429:
        return 'rate_limited'
    if status in (401, 403):
        return 'rejected'
    if status in (500, 502, 503, 504):
        return 'unavailable'
    return ''


def candidates(rows, model, excluded=(), health=None, now=None):
    """Fallback only to enabled keys for the exact same model and API endpoint."""
    selected, raw = resolve(rows, model)
    if selected is None:
        return []
    compatible = [selected]
    if selected.get('rotate', True) and not selected['id'].startswith('test-'):
        compatible += [row for row in rows if row['id'] != selected['id'] and row.get('enabled', True)
                       and not row['id'].startswith('test-') and row.get('rotate', True)
                       and row.get('base_url') == selected.get('base_url')
                       and row.get('kind', 'tokenharbor') == selected.get('kind', 'tokenharbor')
                       and raw in row.get('models', [])]
    result = [(row, raw) for row in compatible if row['id'] not in excluded and row.get('key')]
    if health is not None:
        now = time.time() if now is None else now
        result = [(row, raw) for row, raw in result if row['id'].startswith('test-') or not any(
            block.get('credential_tag') == credential_tag(row) and block.get('retry_at', 0) > now
            for block in health.get(row['id'], {}).get('cooldowns', {}).values()
            if block.get('scope') == 'credential' or block.get('model') == raw)]
    return result


def catalog_rows(rows):
    from model_names import model_name
    return [{'id': model_id(row, raw), 'model': raw, 'profile_id': row['id'],
        'label': 'API · ' + row['label'] + ' · ' + model_name(raw, {})}
        for row in rows if row.get('enabled', True) and not row['id'].startswith('test-') for raw in row['models']]


def fetch_models(row):
    headers = {**request_headers(), 'anthropic-version': '2023-06-01'}
    headers['x-api-key' if row.get('kind') == 'anthropic' else 'Authorization'] = row['key'] if row.get('kind') == 'anthropic' else 'Bearer ' + row['key']
    request = urllib.request.Request(row['base_url'].rstrip('/').removesuffix('/v1') + '/v1/models', headers=headers)
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=15) as response:
        data = json.load(response)
    return sorted({m['id'] for m in data.get('data', []) if isinstance(m.get('id'), str)})


class Usage:
    def __init__(self):
        self.input = self.output = 0
        self.buffer = b''
        self.failed = False
        self.failure = ''

    def json(self, value):
        if not isinstance(value, dict):
            return
        self.failed = self.failed or value.get('type') == 'error' or bool(value.get('error'))
        if value.get('type') == 'error' or value.get('error'):
            self.failure = failure_state(400, value) or self.failure
        for item in (value, value.get('message', {}), value.get('response', {})):
            if not isinstance(item, dict):
                continue
            usage = item.get('usage') or {}
            if isinstance(usage, dict):
                def count(key, fallback=None):
                    value = usage.get(key, usage.get(fallback, 0))
                    return value if isinstance(value, int) and value >= 0 else 0
                self.input = max(self.input, count('input_tokens', 'prompt_tokens') + count('cache_creation_input_tokens') + count('cache_read_input_tokens'))
                self.output = max(self.output, count('output_tokens', 'completion_tokens'))

    def feed(self, data):
        self.buffer += data
        while b'\n' in self.buffer:
            line, self.buffer = self.buffer.split(b'\n', 1)
            if line.startswith(b'data:'):
                try:
                    self.json(json.loads(line[5:]))
                except ValueError:
                    pass
        if len(self.buffer) > 1000000:
            self.buffer = b''


class Stats:
    def __init__(self, path=None):
        self.path = path
        self.lock = threading.Lock()
        try:
            self.rows = json.loads(path.read_text('utf-8')) if path else {}
        except (OSError, ValueError):
            self.rows = {}

    def record(self, ident, model, status, usage, latency, *, failure='', retry_after=None, profile=None):
        from backend import atomic_write
        with self.lock:
            row = self.rows.setdefault(ident, {'success': 0, 'failed': 0, 'input_tokens': 0, 'output_tokens': 0, 'latency_ms': 0})
            row['success' if status == 200 else 'failed'] += 1
            row['input_tokens'] += usage.input
            row['output_tokens'] += usage.output
            row['latency_ms'] += round(latency * 1000)
            row.update(last_at=datetime.now(timezone.utc).isoformat(), last_model=model, last_status=status)
            failure = failure or failure_state(status)
            row.update(exhausted=failure == 'exhausted', unavailable=failure in ('unavailable', 'rejected'),
                       failure=failure)
            if profile:
                blocks = row.setdefault('cooldowns', {})
                if status == 200:
                    blocks.pop(model, None)
                    blocks.pop('*', None)
                elif failure:
                    scope = 'credential' if failure in ('exhausted', 'rejected') else 'model'
                    seconds = {'exhausted': 300, 'rejected': 300, 'rate_limited': 60, 'unavailable': 15}[failure]
                    if isinstance(retry_after, (int, float)) and 0 < retry_after <= 86400:
                        seconds = max(seconds, retry_after)
                    block = {'model': model, 'scope': scope, 'state': failure,
                             'retry_at': time.time() + seconds, 'credential_tag': credential_tag(profile)}
                    blocks['*' if scope == 'credential' else model] = block
            if self.path:
                try:
                    atomic_write(self.path, json.dumps(self.rows).encode())
                except OSError:
                    pass

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.rows)
