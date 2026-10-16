import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import api_keys
from backend import Controller, AccountError


class ApiFrontendTests(unittest.TestCase):
    def test_probe_and_catalog_identify_app_to_api_frontends(self):
        opener = MagicMock()
        response = opener.open.return_value.__enter__.return_value
        response.status = 200
        response.read1.side_effect = [b'{"type":"message","content":[{"type":"text","text":"OK"}],"stop_reason":"end_turn"}', b'']
        with patch('api_keys.urllib.request.build_opener', return_value=opener):
            api_keys._probe_message('https://api.example/v1/messages', 'opus', {'x-api-key': 'test-key'}, 'API')
        req = opener.open.call_args.args[0]
        self.assertTrue(req.get_header('User-agent').startswith('GeminiAccounts/'))
        self.assertEqual(req.get_header('X-api-key'), 'test-key')
        opener.open.return_value.__enter__.return_value = io.BytesIO(json.dumps({'data': [{'id': 'opus'}]}).encode())
        with patch('api_keys.urllib.request.build_opener', return_value=opener):
            self.assertEqual(api_keys.fetch_models({'base_url': 'https://api.example', 'key': 'test-key', 'kind': 'anthropic'}), ['opus'])
        self.assertTrue(opener.open.call_args.args[0].get_header('User-agent').startswith('GeminiAccounts/'))

    def test_saved_key_cannot_follow_an_edit_to_another_api_origin(self):
        with tempfile.TemporaryDirectory() as folder:
            c = Controller(data_dir=folder, proxy_dir=Path(folder) / 'proxy')
            ident = api_keys.save_profile(c, {'key': 'saved-test-key', 'base_url': 'https://original.example', 'models': ['opus']})
            row = api_keys.profiles(c)[0]
            self.assertEqual(api_keys.validated_profile(c, dict(row, base_url='https://original.example/v1'))['key'], 'saved-test-key')
            for url in ('https://other.example', 'https://original.example:8443'):
                with self.assertRaises(AccountError):
                    api_keys.validated_profile(c, dict(row, base_url=url))
            self.assertEqual(api_keys.validated_profile(c, dict(row, key='new-provider-key', base_url='https://other.example'))['key'], 'new-provider-key')
            self.assertEqual(api_keys.profiles(c, private=True)[0]['id'], ident)
