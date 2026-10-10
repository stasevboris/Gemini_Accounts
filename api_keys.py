"""Independent API profiles, encrypted credentials and metadata-only usage."""
import json
import secrets
import threading
import urllib.parse
import urllib.request
from datetime import datetime, timezone


def model_id(profile, model):
    return 'api/' + profile['id'] + '/' + model


def is_model(model):
    return isinstance(model, str) and (model.startswith('api/') or model == 'claude-haiku-5.5:free')


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
    return [dict(row) if private else {k: v for k, v in row.items() if k != 'key'} for row in rows]


def save_profile(controller, row):
    from backend import atomic_write, dpapi, AccountError
    row = dict(row)
    rows = profiles(controller, private=True)
    old = next((r for r in rows if r['id'] == row.get('id')), {})
    row['id'] = old.get('id') or secrets.token_hex(6)
    row['key'] = row.get('key') or old.get('key')
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
    rows = [r for r in rows if r['id'] != row['id']] + [row]
    atomic_write(controller.data_dir / 'api-keys.dpapi', dpapi(json.dumps({'profiles': rows}).encode()))
    return row['id']


def remove_profile(controller, ident):
    from backend import atomic_write, dpapi
    rows = [r for r in profiles(controller, private=True) if r['id'] != ident]
    atomic_write(controller.data_dir / 'api-keys.dpapi', dpapi(json.dumps({'profiles': rows}).encode()))


def resolve(rows, model):
    for row in rows:
        if not row.get('enabled', True):
            continue
        for raw in row.get('models', []):
            if model == model_id(row, raw) or (model == 'claude-haiku-5.5:free' and raw == model):
                return row, raw
    return None, None


def catalog(controller):
    return catalog_rows(profiles(controller))


def catalog_rows(rows):
    from model_names import model_name
    return [{'id': model_id(row, raw), 'model': raw, 'profile_id': row['id'],
        'label': 'API · ' + row['label'] + ' · ' + model_name(raw, {})}
        for row in rows if row.get('enabled', True) for raw in row['models']]


def fetch_models(row):
    headers = {'Accept': 'application/json', 'anthropic-version': '2023-06-01'}
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

    def json(self, value):
        if not isinstance(value, dict):
            return
        self.failed = self.failed or value.get('type') == 'error' or bool(value.get('error'))
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

    def record(self, ident, model, status, usage, latency):
        from backend import atomic_write
        with self.lock:
            row = self.rows.setdefault(ident, {'success': 0, 'failed': 0, 'input_tokens': 0, 'output_tokens': 0, 'latency_ms': 0})
            row['success' if status == 200 else 'failed'] += 1
            row['input_tokens'] += usage.input
            row['output_tokens'] += usage.output
            row['latency_ms'] += round(latency * 1000)
            row.update(last_at=datetime.now(timezone.utc).isoformat(), last_model=model, last_status=status)
            if self.path:
                try:
                    atomic_write(self.path, json.dumps(self.rows).encode())
                except OSError:
                    pass

    def snapshot(self):
        with self.lock:
            return {key: dict(value) for key, value in self.rows.items()}
