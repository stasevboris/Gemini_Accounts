import json
import tempfile
import unittest
from pathlib import Path

import api_keys
from backend import Controller, AccountError
from integrations import Integrations
from tokenharbor import save_key, MODEL


class ApiKeyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.c = Controller(data_dir=self.root/'data', proxy_dir=self.root/'proxy')

    def tearDown(self):
        self.temp.cleanup()

    def profile(self, label='My provider', model=MODEL):
        return {'label': label, 'key': 'test-private-key', 'models': [model], 'base_url': 'https://tokenharbor.ai/v1'}

    def test_migration_encrypted_crud_pause_and_removal(self):
        save_key(self.c, 'legacy-private-key')
        legacy = api_keys.profiles(self.c)[0]
        self.assertNotIn('key', legacy)
        ident = api_keys.save_profile(self.c, self.profile())
        self.assertEqual(len(api_keys.profiles(self.c)), 2)
        self.assertNotIn(b'test-private-key', (self.c.data_dir/'api-keys.dpapi').read_bytes())
        row = next(r for r in api_keys.profiles(self.c) if r['id'] == ident)
        self.assertEqual(row['base_url'], 'https://tokenharbor.ai')
        api_keys.save_profile(self.c, dict(row, key='', enabled=False))
        self.assertEqual(next(r for r in api_keys.profiles(self.c, private=True) if r['id'] == ident)['key'], 'test-private-key')
        self.assertEqual(len(api_keys.catalog(self.c)), 1)
        api_keys.remove_profile(self.c, ident)
        api_keys.remove_profile(self.c, legacy['id'])
        self.assertEqual(api_keys.profiles(self.c), [])  # Removed legacy key must not reappear.

    def test_invalid_edits_do_not_destroy_the_existing_key(self):
        ident = api_keys.save_profile(self.c, self.profile())
        for url in ('http://example.com', 'https://user:password@example.com', 'https://example.com/?key=secret'):
            with self.assertRaises(AccountError):
                api_keys.save_profile(self.c, dict(self.profile(), id=ident, base_url=url))
        with self.assertRaises(AccountError):
            api_keys.save_profile(self.c, dict(self.profile(), models=[]))
        self.assertEqual(len(api_keys.profiles(self.c)), 1)

    def test_same_model_on_two_keys_has_distinct_ids(self):
        one = api_keys.save_profile(self.c, self.profile('One'))
        two = api_keys.save_profile(self.c, self.profile('Two'))
        ids = [entry['id'] for entry in api_keys.catalog(self.c)]
        self.assertEqual(len(set(ids)), 2)
        rows = api_keys.profiles(self.c, private=True)
        for ident, model in zip((one, two), ids):
            self.assertEqual(api_keys.resolve(rows, model)[0]['id'], ident)
        self.assertEqual(api_keys.resolve(rows, 'claude-selected'), (None, None))

    def test_claude_preset_keeps_subscription_defaults_and_syncs_api_crud(self):
        self.c.proxy_dir.mkdir()
        (self.c.proxy_dir/'client-key.txt').write_text('local-key')
        self.c.preferences.update({'gemini-model': 'gemini-pro-agent', 'claude-model': 'claude-opus-4-6-thinking'})
        self.c.model_aliases = lambda: {'claude-sonnet-4-5': 'gemini-pro-agent', 'claude-selected': 'claude-opus-4-6-thinking'}
        api_keys.save_profile(self.c, self.profile())
        client = Integrations(self.c, self.root/'home', self.root/'local')
        client.apply(['claude_desktop'])
        path = client.paths()['claude_desktop'][2]
        before = client.read_json(path)
        models = before['inferenceModels']
        self.assertEqual(sum(api_keys.is_desktop_model(m['name']) for m in models), 1)
        opus = next(m for m in models if m['name'] == 'claude-opus-4-6-thinking')
        self.assertIn('Opus', opus['labelOverride'])
        self.assertTrue(opus['isFamilyDefault'])
        self.assertFalse(any(m['name'] == 'claude-selected' for m in models))
        self.assertFalse(models[-1]['isFamilyDefault'])
        self.assertTrue(api_keys.is_desktop_model(models[-1]['name']))
        api_keys.save_profile(self.c, self.profile('Gemini API', 'gemini-3-flash'))
        self.assertTrue(client.refresh_desktop_model_labels())
        after = client.read_json(path)
        self.assertEqual(after['inferenceModels'][:2], models[:2])
        self.assertEqual(after['inferenceGatewayApiKey'], before['inferenceGatewayApiKey'])
        self.assertEqual(sum(api_keys.is_desktop_model(m['name']) for m in after['inferenceModels']), 2)
        self.assertFalse(client.refresh_desktop_model_labels())
        for row in api_keys.profiles(self.c):
            api_keys.remove_profile(self.c, row['id'])
        client.refresh_desktop_model_labels()
        self.assertEqual(client.read_json(path)['inferenceModels'], [m for m in models if not api_keys.is_desktop_model(m['name'])])

    def test_usage_handles_fragmented_sse_and_persists_only_metrics(self):
        usage = api_keys.Usage()
        stream = b'data: {"type":"message_start","message":{"usage":{"input_tokens":12,"cache_read_input_tokens":20}}}\n\ndata: {"type":"message_delta","usage":{"output_tokens":3}}\n\n'
        for part in (stream[:7], stream[7:73], stream[73:]):
            usage.feed(part)
        self.assertEqual((usage.input, usage.output), (32, 3))
        path = self.root/'stats.json'
        stats = api_keys.Stats(path)
        stats.record('one', MODEL, 200, usage, 2)
        stats.record('two', 'gemini-3-flash', 403, api_keys.Usage(), 1)
        data = api_keys.Stats(path).snapshot()
        self.assertEqual((data['one']['success'], data['one']['input_tokens'], data['one']['output_tokens']), (1, 32, 3))
        self.assertEqual(data['two']['failed'], 1)
        self.assertNotIn('messages', json.loads(path.read_text()))
