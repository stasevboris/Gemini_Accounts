import http.client
import json
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from backend import Controller, AccountError
from quota_queue import QueueServer, quota_wait
from tokenharbor import MODEL, HOST, read_key, save_key


class Provider(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.requests.append((self.path, dict(self.headers), body))
        status = getattr(self.server, 'status_by_key', {}).get(self.headers.get('Authorization'), self.server.status)
        if status != 200:
            data = b'{"error":{"type":"permission_error","message":"Enable free model access"}}'
        elif self.path == '/v1/messages/count_tokens':
            data = b'{"input_tokens":7}'
        elif self.path == '/v1/messages':
            data = (b'event: message_start\ndata: {"type":"message_start","message":{"id":"real","model":"claude-haiku-5.5","content":[],"usage":{"input_tokens":12}}}\n\n'
                    b'event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"type":"text_delta","text":"OK"}}\n\n'
                    b'event: message_delta\ndata: {"type":"message_delta","usage":{"output_tokens":3}}\n\n'
                    b'event: message_stop\ndata: {"type":"message_stop"}\n\n') if body.get('stream') else b'{"type":"message","content":[{"type":"text","text":"OK"}],"stop_reason":"end_turn"}'
        elif self.path == '/v1/responses':
            data = b'{"object":"response","output":[{"type":"message","content":[{"type":"output_text","text":"OK"}]}]}'
        else:
            data = b'{"choices":[{"message":{"role":"assistant","content":"OK"}}]}'
        self.send_response(status)
        self.send_header('Content-Type', 'text/event-stream' if body.get('stream') else 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class Native(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.server.requests.append(self.path)
        result = {'oauth-model-alias': {'antigravity': [{'alias': 'claude-selected', 'name': MODEL}]}}
        if self.path == '/v1/models':
            result = {'data': [{'id': 'gemini-pro-agent', 'object': 'model', 'owned_by': 'antigravity'}]}
        data = json.dumps(result).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class TokenHarborTests(unittest.TestCase):
    def setUp(self):
        self.provider = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
        self.provider.requests = []
        self.provider.status = 200
        self.native = ThreadingHTTPServer(('127.0.0.1', 0), Native)
        self.native.requests = []
        self.gate = QueueServer(('127.0.0.1', 0), self.native.server_address, 'admin', ['client'], {'claude-selected': MODEL})
        self.gate.tokenharbor_key = lambda: 'provider-test-key'
        self.servers = (self.provider, self.native, self.gate)
        for server in self.servers:
            threading.Thread(target=server.serve_forever, daemon=True).start()
        self.factory = patch('quota_queue.http.client.HTTPSConnection',
            side_effect=lambda host, **kwargs: http.client.HTTPConnection(*self.provider.server_address, **kwargs))
        self.connection = self.factory.start()
        self.client = http.client.HTTPConnection(*self.gate.server_address, timeout=3)

    def tearDown(self):
        self.client.close()
        self.factory.stop()
        for server in reversed(self.servers):
            server.shutdown()
            server.server_close()

    def post(self, path='/v1/messages', model='claude-selected', stream=False, key='client'):
        payload = {'model': model, 'stream': stream, 'max_tokens': 16,
            'system': [{'type': 'text', 'text': 'Keep this system message.'}],
            'tools': [{'name': 'test', 'input_schema': {'type': 'object'}}],
            'messages': [{'role': 'user', 'content': 'hello'}]}
        self.client.request('POST', path, json.dumps(payload), {
            'X-API-Key': key, 'authorization': 'Bearer ' + key,
            'Content-Type': 'application/json', 'anthropic-version': '2023-06-01', 'Cookie': 'local-cookie'})
        response = self.client.getresponse()
        return response.status, response.read(), payload

    def test_alias_keeps_anthropic_protocol_and_removes_local_secrets(self):
        status, data, original = self.post()
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)['type'], 'message')
        path, headers, body = self.provider.requests[-1]
        self.assertEqual(path, '/v1/messages')
        self.assertEqual(body, dict(original, model=MODEL))
        folded = {key.lower(): value for key, value in headers.items()}
        self.assertEqual(folded['authorization'], 'Bearer provider-test-key')
        self.assertNotIn('x-api-key', folded)
        self.assertNotIn('cookie', folded)
        self.assertEqual(folded['anthropic-version'], '2023-06-01')
        self.connection.assert_called_with(HOST, timeout=60)
        self.assertNotIn('/v0/management/auth-files', self.native.requests)

    def test_stream_keeps_real_anthropic_events(self):
        status, data, _ = self.post(model='claude-selected[1m]', stream=True)
        self.assertEqual(status, 200)
        self.assertIn(b'event: content_block_delta', data)
        self.assertIn(b'"text":"OK"', data)
        self.assertIn(b'event: message_stop', data)
        self.assertEqual(len(self.provider.requests), 1)

    def test_google_credential_cooldown_does_not_block_tokenharbor(self):
        files = [{'provider': 'antigravity', 'name': 'blocked', 'cooldowns': [{
            'scope': 'credential', 'http_status': 429, 'reason': 'quota',
            'retry_at': (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()}]}]
        self.assertIsNone(quota_wait(files, 'claude-selected', {'claude-selected': MODEL}))
        self.assertIsNotNone(quota_wait(files, 'gemini-pro-agent', {}))

    def test_missing_key_returns_an_actionable_error_without_network(self):
        self.gate.tokenharbor_key = lambda: None
        status, data, _ = self.post()
        self.assertEqual(status, 503)
        self.assertIn(b'TokenHarbor API key', data)
        self.assertEqual(self.provider.requests, [])
        deadline = time.monotonic() + 1
        while self.gate.snapshot()['jobs'] and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertEqual(self.gate.snapshot()['jobs'], [])

    def test_permission_error_is_returned_instead_of_google_quota_wait(self):
        self.provider.status = 403
        status, data, _ = self.post()
        self.assertEqual(status, 403)
        self.assertIn(b'Enable free model access', data)
        self.assertEqual(len(self.provider.requests), 1)
        self.assertNotIn('/v0/management/auth-files', self.native.requests)

    def test_openai_and_responses_endpoints_are_preserved(self):
        for path in ('/v1/chat/completions', '/v1/responses'):
            status, _, _ = self.post(path=path)
            self.assertEqual(status, 200)
            self.assertEqual(self.provider.requests[-1][0], path)
            self.assertEqual(self.provider.requests[-1][2]['model'], MODEL)

    def test_token_count_requires_local_auth_and_uses_provider_key(self):
        status, _, _ = self.post(path='/v1/messages/count_tokens', key='wrong')
        self.assertEqual(status, 401)
        self.assertEqual(self.provider.requests, [])
        status, data, _ = self.post(path='/v1/messages/count_tokens')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)['input_tokens'], 7)
        self.assertEqual(self.provider.requests[-1][0], '/v1/messages/count_tokens')

    def test_key_is_encrypted_and_never_written_to_preferences(self):
        with tempfile.TemporaryDirectory() as folder:
            c = Controller(data_dir=folder, proxy_dir=Path(folder)/'proxy')
            save_key(c, 'test-private-provider-key')
            self.assertEqual(read_key(c), 'test-private-provider-key')
            self.assertNotIn(b'test-private-provider-key', (c.data_dir/'tokenharbor-key.dpapi').read_bytes())
            self.assertNotIn('tokenharbor-key', c.preferences)
            with self.assertRaises(AccountError):
                save_key(c, 'key with spaces')
            self.assertEqual(read_key(c), 'test-private-provider-key')
            save_key(c, '')
            self.assertIsNone(read_key(c))

    def test_independent_profiles_keep_credentials_and_usage_separate(self):
        import api_keys
        rows = [{'id': ident, 'label': ident, 'key': 'secret-' + ident, 'kind': 'tokenharbor',
                 'base_url': 'https://tokenharbor.ai', 'models': [MODEL], 'enabled': True} for ident in ('one', 'two')]
        self.gate.api_profiles = lambda: rows
        for row in rows:
            status, data, _ = self.post(model=api_keys.model_id(row, MODEL), stream=True)
            self.assertEqual(status, 200)
            self.assertIn(b'message_stop', data)
            self.assertEqual(self.provider.requests[-1][1]['Authorization'], 'Bearer ' + row['key'])
            self.assertEqual(self.provider.requests[-1][2]['model'], MODEL)
        deadline = time.monotonic() + 1
        while self.gate.snapshot()['jobs'] and time.monotonic() < deadline:
            time.sleep(.01)
        for row in rows:
            stats = self.gate.api_stats.snapshot()[row['id']]
            self.assertEqual((stats['success'], stats['failed'], stats['input_tokens'], stats['output_tokens']), (1, 0, 12, 3))
        rows[1]['enabled'] = False
        self.assertEqual(self.post(model=api_keys.model_id(rows[1], MODEL))[0], 503)
        self.assertEqual(len(self.provider.requests), 2)

    def test_discovery_combines_google_and_api_models_without_secrets(self):
        import api_keys
        row = {'id': 'one', 'label': 'My key', 'key': 'private-provider-secret', 'kind': 'tokenharbor',
               'base_url': 'https://tokenharbor.ai', 'models': [MODEL], 'enabled': True}
        self.gate.api_profiles = lambda: [row]
        self.client.request('GET', '/v1/models', headers={'Authorization': 'Bearer client'})
        response = self.client.getresponse()
        data = response.read()
        self.assertEqual(response.status, 200)
        self.assertEqual({m['id'] for m in json.loads(data)['data']}, {'gemini-pro-agent', api_keys.model_id(row, MODEL)})
        self.assertNotIn(row['key'].encode(), data)
        self.client.request('GET', '/v0/management/api-key-stats', headers={'Authorization': 'Bearer client'})
        response = self.client.getresponse()
        response.read()
        self.assertEqual(response.status, 401)

    def test_anthropic_profile_uses_native_auth_header_and_base_prefix(self):
        import api_keys
        row = {'id': 'anthropic', 'label': 'Native API', 'key': 'native-api-test-key', 'kind': 'anthropic',
               'base_url': 'https://anthropic.example', 'models': [MODEL], 'enabled': True}
        self.gate.api_profiles = lambda: [row]
        self.assertEqual(self.post(model=api_keys.model_id(row, MODEL))[0], 200)
        headers = {k.lower(): v for k, v in self.provider.requests[-1][1].items()}
        self.assertEqual(headers['x-api-key'], row['key'])
        self.assertNotIn('authorization', headers)

    def test_desktop_deepseek_alias_preserves_model_history_and_key(self):
        import api_keys
        raw = 'deepseek-v4.1-flash:free'
        row = {'id': 'deepseek', 'label': 'DeepSeek', 'key': 'deepseek-test-secret',
               'kind': 'tokenharbor', 'base_url': 'https://tokenharbor.ai', 'models': [raw]}
        self.gate.api_profiles = lambda: [row]
        alias = api_keys.desktop_model_id(api_keys.catalog_rows([row])[0])
        status, data, original = self.post(model=alias, stream=True)
        self.assertEqual(status, 200)
        self.assertIn(b'message_stop', data)
        self.assertEqual(self.provider.requests[-1][2], dict(original, model=raw))
        self.assertEqual(self.provider.requests[-1][1]['Authorization'], 'Bearer ' + row['key'])
        self.assertNotIn('/v0/management/auth-files', self.native.requests)

    def test_api_fallback_tries_compatible_keys_once_and_counts_each_attempt(self):
        import api_keys
        rows = [{'id': ident, 'label': ident, 'key': 'secret-' + ident, 'kind': 'tokenharbor',
                 'base_url': 'https://tokenharbor.ai', 'models': [MODEL]} for ident in ('one', 'two')]
        self.gate.api_profiles = lambda: rows
        self.provider.status_by_key = {'Bearer secret-one': 402}
        status, data, original = self.post(model=api_keys.model_id(rows[0], MODEL), stream=True)
        self.assertEqual(status, 200)
        self.assertIn(b'message_stop', data)
        self.assertEqual([r[1]['Authorization'] for r in self.provider.requests], ['Bearer secret-one', 'Bearer secret-two'])
        self.assertTrue(all(r[2] == dict(original, model=MODEL) for r in self.provider.requests))
        deadline = time.monotonic() + 1
        while self.gate.snapshot()['jobs'] and time.monotonic() < deadline: time.sleep(.01)
        stats = self.gate.api_stats.snapshot()
        self.assertEqual(stats['one']['failed'], 1)
        self.assertEqual(stats['two']['success'], 1)

    def test_api_fallback_never_crosses_provider_or_model_or_opt_out(self):
        import api_keys
        row = {'id': 'one', 'label': 'one', 'key': 'secret-one', 'kind': 'tokenharbor',
               'base_url': 'https://tokenharbor.ai', 'models': [MODEL]}
        self.provider.status = 429
        for other in (dict(row, id='two', base_url='https://other.example'),
                      dict(row, id='two', models=['different-model']),
                      dict(row, id='two', enabled=False), dict(row, id='two', rotate=False)):
            self.gate.api_profiles = lambda: [row, other]
            before = len(self.provider.requests)
            self.assertEqual(self.post(model=api_keys.model_id(row, MODEL))[0], 429)
            self.assertEqual(len(self.provider.requests), before + 1)

    def test_api_pool_exhaustion_returns_error_without_duplicate_response(self):
        import api_keys
        rows = [{'id': ident, 'label': ident, 'key': 'secret-' + ident, 'kind': 'tokenharbor',
                 'base_url': 'https://tokenharbor.ai', 'models': [MODEL]} for ident in ('one', 'two')]
        self.gate.api_profiles = lambda: rows
        self.provider.status = 503
        status, data, _ = self.post(model=api_keys.model_id(rows[0], MODEL), stream=True)
        self.assertEqual(status, 503)
        self.assertEqual(len(self.provider.requests), 2)
        self.assertNotIn(b'message_start', data)
