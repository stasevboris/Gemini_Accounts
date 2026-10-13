import copy
import http.client
import json
import tempfile
import time
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import Mock, patch

from auth_browser import open_authorization_tab
from account_status import account_status
from backend import AccountError, Controller
from claude_auth import ClaudeAuth, credential, desktop_model_id, is_desktop_model, quota_windows
from integrations import Integrations
from quota_queue import gateway_aliases, quota_wait
from quota_queue import QueueServer
from tests.test_quota_queue import Mock as MockGateway


class ClaudeAuthTests(unittest.TestCase):
    def test_opus_weekly_limit_does_not_mark_whole_claude_account_exhausted(self):
        account = {'provider': 'claude', 'status': 'active', 'quota': {'windows': [
            {'label': '5h', 'remaining': 80, 'reset_at': 1900000000},
            {'label': 'Opus · 1w', 'remaining': 0, 'reset_at': None}]}}
        self.assertEqual(account_status(account)[0], 'Model quota restricted')
        account['quota']['windows'].append({'label': '1w', 'remaining': 0, 'reset_at': None})
        self.assertEqual(account_status(account)[0], 'Limit exhausted')
    def test_usage_keeps_real_missing_and_per_model_windows_separate(self):
        result = quota_windows({'five_hour': {'utilization': 23.5, 'resets_at': '2030-01-01T01:00:00Z'},
            'seven_day': None, 'seven_day_opus': {'utilization': 100, 'resets_at': None},
            'seven_day_sonnet': {'utilization': 0, 'resets_at': 'invalid'}})
        self.assertEqual([w['label'] for w in result], ['5h', 'Opus · 1w', 'Sonnet · 1w'])
        self.assertEqual([w['remaining'] for w in result], [76.5, 0, 100])
        self.assertIsNone(result[-1]['reset_at'])
        self.assertGreater(result[0]['reset_at'], 0)
        for value in (True, '10', float('nan'), float('inf'), None):
            self.assertEqual(quota_windows({'five_hour': {'utilization': value}}), [])

    def test_usage_pins_auth_and_caches_without_generation_or_paid_settings(self):
        controller = Mock()
        controller._claude_usage_cache = {}
        controller.request.side_effect = [
            {'status_code': 200, 'body': json.dumps({'five_hour': {'utilization': 10, 'resets_at': '2030-01-01T01:00:00Z'}})},
            {'status_code': 200, 'body': {'account': {'has_claude_max': True}}}]
        auth = ClaudeAuth(controller)
        account = {'name': 'claude-one', 'auth_index': 'one'}
        result = auth.quota(account)
        self.assertEqual(result['plan_type'], 'Max')
        self.assertEqual(auth.quota(account), result)
        self.assertEqual(controller.request.call_count, 2)
        for call in controller.request.call_args_list:
            self.assertEqual(call.args[2]['auth_index'], 'one')
            self.assertEqual(call.args[2]['method'], 'GET')
            self.assertEqual(call.args[2]['header']['Authorization'], 'Bearer $TOKEN$')

    def test_usage_error_backoff_does_not_invent_full_quota(self):
        controller = Mock()
        controller._claude_usage_cache = {}
        controller.request.return_value = {'status_code': 429, 'body': 'private provider details'}
        auth = ClaudeAuth(controller)
        quota = auth.quota({'name': 'one', 'auth_index': 'one'})
        self.assertEqual(quota['windows'], [])
        self.assertNotIn('private', quota['error'])
        auth.quota({'name': 'one', 'auth_index': 'one'})
        self.assertEqual(controller.request.call_count, 1)

    def test_signin_uses_claude_endpoint_and_checks_host_and_state(self):
        controller = Mock()
        controller.request.return_value = {'url': 'https://claude.ai/oauth/authorize?state=one', 'state': 'one'}
        auth = ClaudeAuth(controller)
        self.assertEqual(auth.begin_login()[1], 'one')
        controller.request.assert_called_with('/anthropic-auth-url?is_webui=true')
        for url in ('https://claude.ai.evil.example/oauth/authorize?state=one',
                    'https://claude.ai/oauth/authorize?state=other', 'https://claude.ai/login?state=one'):
            controller.request.return_value = {'url': url, 'state': 'one'}
            with self.assertRaises(AccountError):
                auth.begin_login()

    def test_claude_browser_is_normal_firefox_tab_and_does_not_allow_other_hosts(self):
        with patch('auth_browser.find_firefox', return_value=Path('firefox.exe')), patch('auth_browser.subprocess.Popen') as launch:
            open_authorization_tab('https://claude.ai/oauth/authorize?state=one', provider='claude')
            self.assertEqual(launch.call_args.args[0][:2], ['firefox.exe', '-new-tab'])
            for url in ('https://auth.openai.com/login', 'https://claude.ai/login', 'https://claude.ai.evil.example/oauth/authorize'):
                with self.assertRaises(AccountError):
                    open_authorization_tab(url, provider='claude')
            self.assertEqual(launch.call_count, 1)

    def test_manual_callback_validates_state_without_echoing_code(self):
        controller = Mock()
        auth = ClaudeAuth(controller)
        auth.submit_callback('test-code#one', 'one')
        controller.request.assert_called_with('/oauth-callback', 'POST',
                                              {'provider': 'anthropic', 'code': 'test-code', 'state': 'one'})
        auth.submit_callback('http://localhost:54545/callback?code=test-code&state=one', 'one')
        count = controller.request.call_count
        for value in ('test-code#other', 'http://evil.example/callback?code=test-code&state=one',
                      'http://localhost:54545/callback?code=test-code&state=other', ''):
            with self.assertRaises(AccountError) as error:
                auth.submit_callback(value, 'one')
            self.assertNotIn('test-code', str(error.exception))
        self.assertEqual(controller.request.call_count, count)

    def test_credentials_convert_only_explicit_claude_inputs_and_strip_unrelated_secrets(self):
        result = credential({'claudeAiOauth': {'accessToken': 'test-access', 'refreshToken': 'test-refresh',
                                              'expiresAt': 1900000000000}, 'apiKey': 'do-not-import'},
                            {'account': {'email': 'test@example.com', 'uuid': 'account'}, 'organization': {'uuid': 'org'}})
        self.assertEqual(result['type'], 'claude')
        self.assertEqual(result['account_uuid'], 'account')
        self.assertNotIn('apiKey', result)
        self.assertTrue(result['expired'].startswith('2030-'))
        for value in (None, {'type': 'codex', 'access_token': 'test'},
                      {'type': 'claude', 'access_token': 'test', 'refresh_token': ''}):
            with self.assertRaises(AccountError):
                credential(value)

    def test_import_checks_identity_and_uploads_only_selected_file(self):
        controller = Mock()
        auth = ClaudeAuth(controller)
        uploaded = []
        controller.upload_auth_file.side_effect = lambda name, data: uploaded.append((name, json.loads(data)))
        controller.request.return_value = {'status_code': 200,
            'body': {'account': {'email': 'test@example.com', 'uuid': 'account'}, 'organization': {'uuid': 'org'}}}
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'chosen.json'
            path.write_text(json.dumps({'claudeAiOauth': {'accessToken': 'test-access', 'refreshToken': 'test-refresh'}}))
            with patch.object(auth, 'accounts', side_effect=lambda: [{'name': uploaded[-1][0]}]):
                name = auth.import_file(path)
        self.assertTrue(name.startswith('claude-import-'))
        self.assertEqual(uploaded[0][1]['email'], 'test@example.com')
        self.assertEqual(controller.request.call_args.args[2]['url'], 'https://api.anthropic.com/api/oauth/profile')

    def test_pool_metadata_strips_tokens_and_google_is_not_ranked(self):
        controller = Mock()
        now = time.time()
        def account(name, remaining, reset):
            return {'name': name, 'provider': 'claude', 'disabled': False, 'access_token': 'never-ui', 'quota': {
                'windows': [{'label': '5h', 'remaining': remaining, 'reset_at': now + reset},
                            {'label': '1w', 'remaining': 100, 'reset_at': now + 600000}]}}
        accounts = [account('later', 90, 5000), account('empty', 0, 100), account('first', 70, 1000)]
        controller.request.side_effect = lambda path, *args: {'files': accounts + [
            {'name': 'google', 'provider': 'antigravity'}, {'name': 'gpt', 'provider': 'codex'}]} if path == '/auth-files' else {'strategy': 'fill-first'}
        auth = ClaudeAuth(controller)
        self.assertNotIn('access_token', auth.accounts()[0])
        auth.apply_reset_priority(accounts)
        changes = [c.args[2]['name'] for c in controller.request.call_args_list if c.args[0] == '/auth-files/fields']
        self.assertEqual(changes, ['first', 'later', 'empty'])

    def test_probe_is_pinned_and_uses_smallest_available_model(self):
        controller = Mock()
        controller.oauth_model_choices.return_value = ['claude-opus-4-6', 'claude-haiku-4-5']
        controller.request.return_value = {'status_code': 200, 'body': {'content': [{'type': 'text', 'text': 'OK'}]}}
        model = ClaudeAuth(controller).probe({'name': 'one', 'auth_index': 'one', 'provider': 'claude'})
        self.assertEqual(model, 'claude-haiku-4-5')
        payload = controller.request.call_args.args[2]
        self.assertEqual(payload['auth_index'], 'one')
        self.assertEqual(json.loads(payload['data'])['max_tokens'], 16)
        with self.assertRaises(AccountError):
            ClaudeAuth(controller).probe({'disabled': True})

    def test_claude_wait_only_uses_claude_pool_and_matching_model(self):
        route = desktop_model_id('claude-sonnet-4-6')
        aliases = gateway_aliases({'antigravity': [{'alias': 'google-route', 'name': 'claude-sonnet-4-6'}],
            'claude': [{'alias': route, 'name': 'claude-sonnet-4-6'}]})
        block = {'scope': 'credential', 'http_status': 429, 'reason': 'quota', 'retry_at': '2099-01-01T00:00:00Z'}
        files = [{'provider': 'antigravity', 'cooldowns': []}, {'provider': 'codex', 'cooldowns': []},
                 {'provider': 'claude', 'cooldowns': [block]}]
        self.assertIsNotNone(quota_wait(files, route, aliases))
        self.assertIsNone(quota_wait(files, 'google-route', aliases))
        files.append({'provider': 'claude', 'cooldowns': []})
        self.assertIsNone(quota_wait(files, route, aliases))
        files.pop()
        files[-1]['cooldowns'][0] = {**block, 'scope': 'model', 'model_key': 'claude-opus-4-6'}
        self.assertIsNone(quota_wait(files, route, aliases))

    def test_provider_aliases_do_not_overwrite_same_named_google_models(self):
        with tempfile.TemporaryDirectory() as root:
            controller = Controller(proxy_dir=Path(root) / 'proxy', data_dir=Path(root) / 'data')
            controller.key = 'test-management-key'
            controller.chatgpt_model_choices = lambda: []
            controller.claude_subscription_model_choices = lambda: ['claude-sonnet-4-6']
            channels = {'antigravity': [{'alias': 'google', 'name': 'claude-sonnet-4-6'}],
                        'claude': [{'alias': 'custom', 'name': 'claude-haiku-4-5'}]}
            def request(path, method='GET', data=None):
                if method == 'PATCH':
                    channels[data['provider']] = copy.deepcopy(data['aliases'])
                return {'oauth-model-alias': copy.deepcopy(channels)}
            controller.request = request
            client = Integrations(controller, Path(root) / 'home', Path(root) / 'local')
            self.assertTrue(client.configure_desktop_api_routes())
            self.assertEqual(channels['antigravity'], [{'alias': 'google', 'name': 'claude-sonnet-4-6'}])
            self.assertEqual(channels['claude'][0]['alias'], 'custom')
            route = desktop_model_id('claude-sonnet-4-6')
            self.assertEqual(channels['claude'][-1]['alias'], route)
            self.assertTrue(is_desktop_model(route))
            self.assertFalse(client.configure_desktop_api_routes())
            controller.claude_subscription_model_choices = lambda: []
            self.assertTrue(client.configure_desktop_api_routes())
            self.assertEqual(len(channels['claude']), 1)

    def test_catalog_does_not_recursively_import_its_own_aliases(self):
        controller = Controller(proxy_dir=Path('unused'), data_dir=Path('unused'))
        route = desktop_model_id('claude-sonnet-4-6')
        controller.request = lambda path: {'models': [{'id': 'claude-sonnet-4-6'}, {'id': route}]} if '/models?' in path else {
            'files': [{'provider': 'claude', 'name': 'one'}, {'provider': 'claude', 'name': 'disabled', 'disabled': True}]}
        self.assertEqual(controller.claude_subscription_model_choices(), ['claude-sonnet-4-6'])

    def test_inference_preserves_claude_provider_alias_and_conversation_history(self):
        route = desktop_model_id('claude-sonnet-4-6')
        class Gateway(MockGateway):
            def do_GET(self):
                if self.path == '/v0/management/oauth-model-alias':
                    data = json.dumps({'oauth-model-alias': {'claude': [{'alias': route, 'name': 'claude-sonnet-4-6'}]}}).encode()
                    self.send_response(200)
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    super().do_GET()
        backend = ThreadingHTTPServer(('127.0.0.1', 0), Gateway)
        backend.files, backend.calls, backend.status = [{'provider': 'claude', 'name': 'one'}], 0, 200
        backend.json_nonstream = True
        queue = QueueServer(('127.0.0.1', 0), backend.server_address, 'admin', ['client'], {})
        threading.Thread(target=backend.serve_forever, daemon=True).start()
        threading.Thread(target=queue.serve_forever, daemon=True).start()
        request = {'model': route, 'stream': False, 'max_tokens': 30, 'system': 'Keep the previous conversation.',
                   'messages': [{'role': 'user', 'content': 'Remember number 7.'},
                                {'role': 'assistant', 'content': 'I remember 7.'},
                                {'role': 'user', 'content': 'What number did I give you?'}]}
        client = http.client.HTTPConnection(*queue.server_address, timeout=3)
        try:
            client.request('POST', '/v1/messages', json.dumps(request), {'x-api-key': 'client'})
            response = client.getresponse()
            self.assertEqual(response.status, 200)
            self.assertIn(b'OK', response.read())
            self.assertEqual(backend.last_request, request)
            self.assertEqual(backend.calls, 1)
        finally:
            client.close()
            queue.shutdown()
            queue.server_close()
            backend.shutdown()
            backend.server_close()


if __name__ == '__main__':
    unittest.main()
