import copy
import re
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import AccountError, Controller
from grok_auth import GrokAuth, desktop_model_id, is_desktop_model
from integrations import Integrations
from quota_queue import gateway_aliases, quota_wait


class GrokAuthTests(unittest.TestCase):
    def test_accounts_filter_only_persistent_xai_credentials(self):
        controller = Mock()
        controller.request.return_value = {'files': [
            {'name': 'grok-a', 'provider': 'xai', 'auth_index': 'one'},
            {'name': 'grok-runtime', 'provider': 'xai', 'auth_index': 'two', 'runtime_only': True},
            {'name': 'grok-memory', 'provider': 'xai', 'auth_index': 'three', 'source': 'memory'},
            {'name': 'google', 'provider': 'antigravity', 'auth_index': 'four'},
        ]}
        rows = GrokAuth(controller).accounts()
        self.assertEqual([row['name'] for row in rows], ['grok-a'])
        self.assertNotIn('access_token', rows[0])

    def test_device_authorization_validates_url_and_state(self):
        controller = Mock()
        controller.request.return_value = {'url': 'https://accounts.x.ai/oauth/authorize?state=s1',
            'state': 's1', 'user_code': 'ABCD-EFGH', 'expires_in': 900}
        result = GrokAuth(controller).begin_login()
        self.assertEqual(result['state'], 's1')
        self.assertEqual(result['user_code'], 'ABCD-EFGH')
        self.assertEqual(result['expires_in'], 900)
        self.assertEqual(parse_qs(urlsplit(result['url']).query)['state'], ['s1'])

    def test_device_authorization_rejects_external_or_mismatched_urls(self):
        controller = Mock()
        controller.request.return_value = {'url': 'https://evil.example/login?state=s1', 'state': 's1'}
        with self.assertRaises(AccountError):
            GrokAuth(controller).begin_login()
        controller.request.return_value = {'url': 'https://auth.x.ai/login?state=other', 'state': 's1'}
        with self.assertRaises(AccountError):
            GrokAuth(controller).begin_login()
        self.assertGreaterEqual(controller.request.call_count, 2)

    def test_unsupported_gateway_reports_grok_oauth_requirement(self):
        controller = Mock()
        controller.request.side_effect = AccountError('The local connection returned error 404.')
        with self.assertRaisesRegex(AccountError, 'does not support Grok sign-in'):
            GrokAuth(controller).begin_login()

    def test_no_unreported_grok_quota_is_presented_as_zero(self):
        quota = GrokAuth.quota({'plan_type': 'SuperGrok'})
        self.assertEqual(quota['windows'], [])
        self.assertEqual(quota['plan_type'], 'SuperGrok')

    def test_models_are_filtered_and_sorted(self):
        controller = Mock()
        controller.request.return_value = {'models': [
            {'id': 'grok-beta'}, {'id': 'grok-4'}, {'name': 'not-an-id'}, {'id': 5}]}
        self.assertEqual(GrokAuth(controller).models({'name': 'xai.json'}), ['grok-4', 'grok-beta'])

    def test_client_routes_are_stable_distinct_and_accepted_as_anthropic_names(self):
        models = ['grok-4.7', 'grok-4.7-build-fast', 'grok-imagine-image']
        routes = [desktop_model_id(model) for model in models]
        self.assertEqual(len(set(routes)), len(models))
        for model, route in zip(models, routes):
            self.assertEqual(route, desktop_model_id(model))
            self.assertTrue(is_desktop_model(route))
            self.assertTrue(route.startswith('claude-sonnet-4-5-'))
            self.assertFalse(re.search(r'grok|gpt|gemini|deepseek|codex', route, re.I))
        self.assertFalse(is_desktop_model('grok-4.7'))
        self.assertFalse(is_desktop_model(None))

    def test_desktop_migration_removes_xai_routes_and_preserves_custom_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            controller = Controller(proxy_dir=root / 'proxy', data_dir=root / 'data')
            controller.key = 'test-key'
            controller.grok_model_choices = lambda: ['grok-4.7', 'grok-4.7-build-fast']
            controller.chatgpt_model_choices = lambda: []
            controller.claude_subscription_model_choices = lambda: []
            controller.oauth_model_choices = lambda *args: []
            controller.family_model_choices = lambda: {'gemini': ['gemini-3.8-flash-high'], 'claude': []}
            custom_alias = {'alias': 'custom-xai', 'name': 'grok-4.7'}
            channels = {'antigravity': [], 'claude': [], 'xai': [custom_alias,
                {'alias': desktop_model_id('grok-4.7'), 'name': 'grok-4.7'}]}
            def request(path, method='GET', data=None):
                self.assertEqual(path, '/oauth-model-alias')
                if method == 'PATCH':
                    channels[data['provider']] = copy.deepcopy(data['aliases'])
                return {'oauth-model-alias': copy.deepcopy(channels)}
            controller.request = request
            client = Integrations(controller, root / 'home', root / 'local')
            path = client.paths()['claude_desktop'][2]
            client.write_json(path.parent / '_meta.json', {'appliedId': path.stem})
            custom = {'name': 'claude-custom', 'labelOverride': 'My custom model'}
            original = {'deploymentDisplayName': 'Gemini Accounts',
                        'inferenceGatewayBaseUrl': 'http://127.0.0.1:8317',
                        'inferenceGatewayApiKey': 'keep-key', 'coworkEgressAllowedHosts': ['example.com'],
                        'customSetting': {'keep': True},
                        'inferenceModels': [custom, {'name': 'grok-4.7', 'labelOverride': 'Grok · grok-4.7'}]}
            client.write_json(path, original)
            self.assertTrue(client.refresh_desktop_model_labels())
            preset = client.read_json(path)
            grok = [entry for entry in preset['inferenceModels'] if entry.get('labelOverride', '').startswith('Grok · ')]
            self.assertEqual(grok, [])
            self.assertEqual(preset['inferenceModels'][0], custom)
            for field in ('inferenceGatewayApiKey', 'coworkEgressAllowedHosts', 'customSetting'):
                self.assertEqual(preset[field], original[field])
            self.assertEqual(channels['xai'], [custom_alias])
            aliases = gateway_aliases(channels)
            self.assertNotIn(desktop_model_id('grok-4.7'), aliases)
            self.assertFalse(any(is_desktop_model(e['alias']) for e in channels['antigravity']))
            self.assertFalse(client.refresh_desktop_model_labels())
            controller.grok_model_choices = lambda: []
            self.assertFalse(client.refresh_desktop_model_labels())
            self.assertEqual(channels['xai'], [custom_alias])
            self.assertFalse(any(is_desktop_model(e['name']) for e in client.read_json(path)['inferenceModels']))


if __name__ == '__main__':
    unittest.main()
