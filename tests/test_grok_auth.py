import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import AccountError
from grok_auth import GrokAuth


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


if __name__ == '__main__':
    unittest.main()
