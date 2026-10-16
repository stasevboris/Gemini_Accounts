import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from backend import AccountError, Controller
from integrations import Integrations
from kimi_auth import KimiAuth, desktop_model_id, is_desktop_model
from quota_queue import gateway_aliases, quota_wait


class NewIntegrationTests(unittest.TestCase):
    def test_kimi_device_login_uses_selected_domain_and_filters_other_providers(self):
        controller = Mock()
        controller.request.return_value = {'url': 'https://www.kimi.ai/code/oauth?user_code=ABCD', 'state': 'test', 'user_code': 'ABCD'}
        login = KimiAuth(controller, 'kimi.ai').begin_login()
        self.assertEqual(login['state'], 'test')
        self.assertEqual(controller.request.call_args.args[0], '/kimi-ai-auth-url?is_webui=true')
        controller.request.return_value = {'files': [
            {'name': 'com', 'provider': 'kimi'}, {'name': 'ai', 'provider': 'kimi-ai'},
            {'name': 'google', 'provider': 'antigravity'}, {'name': 'memory', 'provider': 'kimi', 'source': 'memory'}]}
        self.assertEqual([a['name'] for a in KimiAuth(controller).accounts()], ['com', 'ai'])

    def test_kimi_routes_distinguish_domains_and_do_not_use_google_cooldowns(self):
        com = desktop_model_id('kimi-k3', 'kimi')
        ai = desktop_model_id('kimi-k3', 'kimi-ai')
        self.assertNotEqual(com, ai)
        self.assertTrue(is_desktop_model(com))
        self.assertFalse(re.search(r'grok|gpt|gemini|kimi|codex', com))
        aliases = gateway_aliases({'kimi': [{'alias': com, 'name': 'kimi-k3'}], 'kimi-ai': [{'alias': ai, 'name': 'kimi-k3'}]})
        blocked = {'provider': 'kimi', 'cooldowns': [{'scope': 'credential', 'http_status': 429,
                   'reason': 'quota', 'retry_at': '2099-01-01T00:00:00Z'}]}
        self.assertIsNotNone(quota_wait([blocked, {'provider': 'kimi-ai'}], com, aliases))
        self.assertIsNone(quota_wait([blocked, {'provider': 'kimi-ai'}], ai, aliases))

    def test_opencode_is_not_an_available_client(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            controller = Controller(proxy_dir=root / 'proxy', data_dir=root / 'data')
            client = Integrations(controller, root / 'home', root / 'local')
            self.assertNotIn('opencode', client.detected())
            self.assertNotIn('opencode', client.paths())
            with self.assertRaises(AccountError):
                client.apply(['opencode'])


if __name__ == '__main__':
    unittest.main()
