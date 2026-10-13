import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, Mock
from backend import Controller, AccountError
from integrations import Integrations
from routing import quota_entry, quota_projection, weekly_threshold, weekly_depleted
from quota_queue import Handler
from model_names import model_name, reasoning_level
import api_keys


class QuotaAvailabilityTests(unittest.TestCase):
    def test_full_five_hour_quota_waits_for_the_weekly_reset(self):
        now = datetime(2026, 10, 11, tzinfo=timezone.utc)
        week = (now + timedelta(days=3)).isoformat()
        entry = {'remaining': 1, 'reset': (now + timedelta(hours=2)).isoformat(),
                 'weekly_remaining': 0, 'weekly_reset': week}
        self.assertEqual(quota_projection([entry], now), [{'remaining': 1, 'reset': week}])

    def test_provider_block_is_scoped_and_expires(self):
        now = datetime(2026, 10, 11, tzinfo=timezone.utc)
        account = {'cooldowns': [{'scope': 'model', 'model_key': 'claude-opus-4-6-thinking',
                    'reason': 'quota', 'retry_at': (now + timedelta(days=3)).isoformat()}]}
        bucket, weekly = {'remaining': 1}, {'remaining': .003}
        self.assertEqual(quota_entry(account, bucket, weekly, 'gemini', now)['remaining'], 1)
        self.assertEqual(quota_entry(account, bucket, weekly, 'claude', now)['remaining'], 0)
        self.assertEqual(quota_entry(account, bucket, weekly, 'claude', now + timedelta(days=4))['remaining'], 1)

    def test_display_threshold_does_not_change_eligibility(self):
        self.assertTrue(weekly_depleted(.009, weekly_threshold({})))
        self.assertFalse(weekly_depleted(.01, weekly_threshold({})))
        self.assertFalse(weekly_depleted(.009, weekly_threshold({'low-weekly-percent': 0})))
        self.assertTrue(weekly_depleted(0, weekly_threshold({'low-weekly-percent': 0})))
        for value in (None, True, float('nan'), -1, 101):
            self.assertEqual(weekly_threshold({'low-weekly-percent': value}), .01)
        self.assertEqual(quota_entry({}, {'remaining': 1}, {'remaining': .009}, 'gemini')['remaining'], 1)


class ClientCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.c = Controller(proxy_dir=self.root / 'proxy', data_dir=self.root / 'data')
        self.c.proxy_dir.mkdir()
        (self.c.proxy_dir / 'client-key.txt').write_text('client-test-key')
        self.c.preferences.update({'gemini-model': 'gemini-pro-agent', 'claude-model': 'claude-opus-4-6-thinking'})
        self.c.key = 'management-test-key'
        self.choices = {'gemini': ['gemini-pro-agent', 'gemini-3-flash', 'gemini-3.5-flash-low',
                                 'gemini-3.8-flash-high', 'gemini-3.8-flash-medium', 'gemini-3.8-flash-low'],
                        'claude': ['claude-opus-4-6-thinking', 'claude-sonnet-4-6', 'claude-haiku-4-5']}
        self.c.family_model_choices = lambda: copy.deepcopy(self.choices)
        self.entries = [{'alias': 'custom', 'name': 'gemini-3-flash'},
                        {'alias': 'claude-sonnet-4-6', 'name': 'claude-opus-4-6-thinking'}]
        self.calls = []
        self.claude_entries = []
        def request(path, method='GET', payload=None):
            self.calls.append((path, method))
            if method == 'PATCH':
                if payload['provider'] == 'claude':
                    self.claude_entries = copy.deepcopy(payload['aliases'])
                else:
                    self.entries = copy.deepcopy(payload['aliases'])
            return {'oauth-model-alias': {'antigravity': copy.deepcopy(self.entries), 'claude': copy.deepcopy(self.claude_entries)}}
        self.c.request = request
        self.client = Integrations(self.c, self.root / 'home', self.root / 'local')
        (self.c.proxy_dir / 'cliproxy-models.json').write_text(json.dumps({'antigravity':
            [{'id': m} for m in self.choices['gemini'] + self.choices['claude']]}))

    def tearDown(self):
        self.temp.cleanup()

    def test_full_menu_preserves_keys_and_separates_real_haiku_from_probe(self):
        api_keys.save_profile(self.c, {'key': 'private-api-test-key', 'base_url': 'https://example.com',
            'models': ['claude-haiku-5.5:free'], 'label': 'Independent key'})
        before = (self.c.data_dir / 'api-keys.dpapi').read_bytes()
        self.client.apply(['claude_desktop'])
        models = {entry['name']: entry for entry in self.client.read_json(self.client.paths()['claude_desktop'][2])['inferenceModels']}
        for model in self.choices['gemini'] + self.choices['claude']:
            self.assertEqual(self.client.claude_desktop_route(model) in models,
                             self.client._desktop_gemini_visible(model))
        routes = {entry['alias']: entry['name'] for entry in self.entries}
        self.assertEqual(routes['claude-haiku-4-5'], 'gemini-3.8-flash-low')
        self.assertNotIn(self.client.claude_desktop_route('claude-haiku-4-5'), models)
        self.assertNotIn('claude-sonnet-4-6', routes)
        self.assertEqual(routes['custom'], 'gemini-3-flash')
        self.assertEqual(sum(api_keys.is_desktop_model(name) for name in models), 1)
        self.assertEqual((self.c.data_dir / 'api-keys.dpapi').read_bytes(), before)

    def test_healing_is_idempotent_and_never_rewrites_clients(self):
        self.client.apply(['claude_desktop'])
        path = self.client.paths()['claude_desktop'][2]
        before, backup = path.read_bytes(), self.client.backup_path.read_bytes()
        self.entries = [{'alias': 'custom', 'name': 'gemini-3-flash'}]
        self.assertTrue(self.client.reconcile_desktop_routes())
        self.assertFalse(self.client.reconcile_desktop_routes())
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.client.backup_path.read_bytes(), backup)

    def test_compact_picker_has_three_flash_tiers_without_duplicates_or_alias_rows(self):
        self.choices['gemini'] += ['gemini-3.8-flash-high', 'gemini-4-argon', 'gemini-3.1-flash-lite']
        self.choices['claude'] += ['claude-selected', 'claude-sonnet-4-5-ga-3-5-flash-low']
        legacy = self.client.claude_desktop_route('gemini-3.5-flash-low')
        self.entries.append({'alias': legacy, 'name': 'gemini-3.5-flash-low', 'fork': True})
        self.client.apply(['claude_desktop'])
        models = self.client.read_json(self.client.paths()['claude_desktop'][2])['inferenceModels']
        self.assertEqual(len(models), 5)
        self.assertEqual(len({e['name'] for e in models}), 5)
        self.assertEqual([e['labelOverride'] for e in models if e['labelOverride'].startswith('Gemini')],
                         ['Gemini · 3.8 Flash High', 'Gemini · 3.8 Flash Medium', 'Gemini · 3.8 Flash Low'])
        self.assertEqual(sum(e['isFamilyDefault'] for e in models), 3)
        self.assertIn(legacy, {e['alias'] for e in self.entries})

    def test_code_picker_keeps_gpt_keys_and_other_settings(self):
        self.c.chatgpt_model_choices = lambda: ['gpt-6-luna', 'gpt-image-2']
        api_keys.save_profile(self.c, {'key': 'fake-key', 'base_url': 'https://example.com',
            'models': ['claude-haiku-5.5:free'], 'label': 'Independent key'})
        path = self.client.paths()['claude_cli'][0]
        self.client.write_json(path, {'env': {'OTHER': 'keep'}, 'permissions': {'allow': ['Read']}})
        self.client.apply(['claude_cli'])
        settings = self.client.read_json(path)
        self.assertEqual(settings['env']['OTHER'], 'keep')
        self.assertEqual(settings['permissions'], {'allow': ['Read']})
        self.assertTrue(settings['modelPicker']['replaceBuiltInOptions'])
        options = settings['modelPicker']['options']
        self.assertEqual(len(options), 8)
        self.assertIn(settings['env']['ANTHROPIC_MODEL'], {e['model'] for e in options})
        self.assertEqual({e['label'] for e in options if e['label'].startswith('ChatGPT')},
                         {'ChatGPT · gpt-6-luna', 'ChatGPT · gpt-image-2'})
        self.assertEqual(next(e for e in options if e['model'] == 'claude-opus-4-6-thinking')['behavesAs'],
                         'claude-opus-4-6')
        self.assertTrue(any(e['label'].startswith('API · Independent key') for e in options))

    def test_menu_migration_preserves_credentials_host_rules_custom_rows_and_old_routes(self):
        self.client.apply(['claude_desktop'])
        path = self.client.paths()['claude_desktop'][2]
        preset = self.client.read_json(path)
        preset['coworkEgressAllowedHosts'] = ['example.com']
        preset['inferenceModels'] += [
            {'name': 'claude-sonnet-4-5', 'labelOverride': 'Gemini · 3.8 Flash High'},
            {'name': self.client.claude_desktop_route('gemini-3-flash'), 'labelOverride': 'Gemini · 3 Flash'},
            {'name': 'custom-model', 'labelOverride': 'My custom model'}]
        self.client.write_json(path, preset)
        self.assertTrue(self.client.reconcile_desktop_routes())
        updated = self.client.read_json(path)
        self.assertEqual(updated['inferenceGatewayApiKey'], preset['inferenceGatewayApiKey'])
        self.assertEqual(updated['coworkEgressAllowedHosts'], ['example.com'])
        self.assertEqual(len(updated['inferenceModels']), 6)
        self.assertTrue(any(e['name'] == 'custom-model' for e in updated['inferenceModels']))
        before = path.read_bytes()
        self.assertFalse(self.client.reconcile_desktop_routes())
        self.assertEqual(path.read_bytes(), before)

    def test_unapproved_preset_is_never_healed(self):
        self.client.write_json(self.client.paths()['claude_desktop'][2], {
            'inferenceGatewayBaseUrl': 'http://127.0.0.1:8317',
            'inferenceModels': [{'name': 'claude-sonnet-4-5', 'labelOverride': 'Gemini Pro'}]})
        self.assertFalse(self.client.reconcile_desktop_routes())
        self.assertEqual(self.calls, [])

    def test_setup_failure_rolls_back_native_routes(self):
        before = copy.deepcopy(self.entries)
        with patch.object(self.client, 'write_json', side_effect=OSError('simulated storage failure')):
            with self.assertRaises(OSError):
                self.client.apply(['claude_desktop'])
        self.assertEqual(self.entries, before)
        self.assertFalse(self.client.paths()['claude_desktop'][2].exists())

    def test_codex_catalog_preserves_existing_models_and_restores(self):
        cache = self.client.home / '.codex' / 'models_cache.json'
        original = {'models': [{'slug': 'existing-user-model', 'base_instructions': 'keep me'}]}
        self.client.write_json(cache, original)
        self.client.apply(['codex'])
        path, _, catalog_path = self.client.paths()['codex']
        catalog = self.client.read_json(catalog_path)
        self.assertEqual(catalog['models'][0], original['models'][0])
        self.assertTrue(any(m['slug'] == 'gemini-3.5-flash-low' for m in catalog['models']))
        import tomllib
        self.assertEqual(tomllib.loads(path.read_text())['model_catalog_json'], str(catalog_path.resolve()))
        self.assertEqual(self.client.read_json(cache), original)
        self.client.restore()
        self.assertFalse(catalog_path.exists())

    def test_external_client_routes_are_stable_distinct_and_healed(self):
        for label in ('DeepSeek A', 'DeepSeek B'):
            api_keys.save_profile(self.c, {'key': 'fake-' + label.replace(' ', '-'), 'base_url': 'https://example.com',
                'models': ['deepseek-v4.1-flash:free'], 'label': label})
        self.c.chatgpt_model_choices = lambda: ['gpt-6-sol']
        self.client.apply(['claude_desktop'])
        path = self.client.paths()['claude_desktop'][2]
        models = self.client.read_json(path)['inferenceModels']
        keys = [m for m in models if api_keys.is_desktop_model(m['name'])]
        self.assertEqual(len(keys), 2)
        self.assertNotEqual(keys[0]['name'], keys[1]['name'])
        from chatgpt_auth import is_desktop_model, desktop_model_id
        oauth = [m for m in models if is_desktop_model(m['name'])]
        self.assertEqual(oauth[0]['labelOverride'], 'ChatGPT · gpt-6-sol')
        self.assertEqual(oauth[0]['name'], desktop_model_id('gpt-6-sol'))
        routes = {e['alias']: e['name'] for e in self.entries}
        for entry in api_keys.catalog(self.c):
            self.assertEqual(routes[api_keys.desktop_model_id(entry)], entry['id'])
        self.assertEqual(routes[oauth[0]['name']], 'gpt-6-sol')
        before = path.read_bytes()
        self.assertFalse(self.client.reconcile_desktop_routes())
        self.assertFalse(self.client.refresh_desktop_model_labels())
        self.assertEqual(before, path.read_bytes())
        self.entries = [e for e in self.entries if not api_keys.is_desktop_model(e['alias'])]
        self.assertTrue(self.client.reconcile_desktop_routes())
        self.assertFalse(self.client.reconcile_desktop_routes())
        self.assertEqual(before, path.read_bytes())
        rows = api_keys.profiles(self.c)
        api_keys.save_profile(self.c, dict(rows[0], enabled=False))
        self.client.refresh_desktop_model_labels()
        self.assertEqual(sum(api_keys.is_desktop_model(e['alias']) for e in self.entries), 1)
        self.assertIn('custom', {e['alias'] for e in self.entries})

    def test_client_aliases_cannot_match_non_anthropic_provider_blacklist(self):
        import re
        blocked = re.compile(r'deepseek|gemini|gpt|qwen|mistral|abab|openai|codex|kimi|nova', re.I)
        for i in range(1000):
            entry = {'id': f'api/key-{i}/deepseek-v4.1-flash:free', 'model': 'deepseek-v4.1-flash:free'}
            name = api_keys.desktop_model_id(entry)
            self.assertTrue(api_keys.is_desktop_model(name))
            self.assertIn('claude', name)
            self.assertFalse(blocked.search(name))


class ApiConnectionChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.c = Controller(proxy_dir=root / 'proxy', data_dir=root / 'data')
        self.c.proxy_dir.mkdir()
        (self.c.proxy_dir / 'client-key.txt').write_text('local-secret-test')
        self.row = {'label': 'Check', 'key': 'private-secret-test', 'base_url': 'https://example.com',
                    'models': ['haiku-test'], 'kind': 'anthropic'}

    def tearDown(self):
        self.temp.cleanup()

    def test_both_routes_are_checked_without_saving_draft(self):
        calls = []
        def probe(url, model, headers, stage):
            calls.append((url, model, headers, stage))
            if stage == 'Local gateway':
                profile, raw = api_keys.resolve(api_keys.profiles(self.c, private=True), model)
                self.assertEqual((profile['key'], raw), ('private-secret-test', 'haiku-test'))
                self.assertEqual(api_keys.catalog(self.c), [])
        with patch('api_keys._probe_message', side_effect=probe):
            result = api_keys.verify_profile(self.c, self.row)
        self.assertTrue(result['provider'] and result['gateway'])
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][2], {'x-api-key': 'private-secret-test'})
        self.assertNotIn('private-secret-test', str(calls[1][2]))
        self.assertFalse((self.c.data_dir / 'api-keys.dpapi').exists())

    def test_failed_gateway_restores_keys_exactly(self):
        ident = api_keys.save_profile(self.c, self.row)
        before = (self.c.data_dir / 'api-keys.dpapi').read_bytes()
        with patch('api_keys._probe_message', side_effect=[None, AccountError('gateway rejected')]):
            with self.assertRaises(AccountError):
                api_keys.verify_profile(self.c, dict(self.row, id=ident, key='changed-draft-key'))
        self.assertEqual((self.c.data_dir / 'api-keys.dpapi').read_bytes(), before)

    def test_probe_cleanup_keeps_concurrent_edits(self):
        with api_keys.temporary_profile(self.c, api_keys.validated_profile(self.c, self.row)):
            ident = api_keys.save_profile(self.c, dict(self.row, label='Keep this edit'))
        self.assertEqual([p['id'] for p in api_keys.profiles(self.c)], [ident])

    def test_invalid_urls_never_receive_credentials(self):
        for url in ('http://example.com', 'https://user:pass@example.com', 'https://example.com?key=secret'):
            with patch('api_keys._probe_message') as probe:
                with self.assertRaises(AccountError):
                    api_keys.verify_profile(self.c, dict(self.row, base_url=url))
                probe.assert_not_called()

    def test_empty_reply_and_endless_quota_wait_fail(self):
        response = io.BytesIO(b'{"type":"message","content":[]}')
        response.status = 200
        opener = Mock()
        opener.open.return_value = response
        with patch('api_keys.urllib.request.build_opener', return_value=opener):
            with self.assertRaises(AccountError):
                api_keys._probe_message('https://example.com', 'test', {}, 'API provider')
        response = io.BytesIO(b' ' * 100)
        response.status = 200
        opener.open.return_value = response
        with patch('api_keys.urllib.request.build_opener', return_value=opener), patch('api_keys.time.monotonic', side_effect=[0, 21]):
            with self.assertRaises(AccountError):
                api_keys._probe_message('https://example.com', 'test', {}, 'Local gateway')

    def test_probe_does_not_pollute_key_statistics(self):
        handler = object.__new__(Handler)
        handler.api_profile = 'test-123'
        handler.server = Mock()
        handler.record_api_attempt()
        handler.server.api_stats.record.assert_not_called()
        self.assertIsNone(handler.api_profile)


class BundledCatalogTests(unittest.TestCase):
    def test_flash_variants_are_distinct_and_named(self):
        models = json.loads((Path(__file__).resolve().parents[1] / 'assets/cliproxy-models.json').read_text('utf-8'))['antigravity']
        ids = [entry['id'] for entry in models]
        self.assertEqual(len(ids), len(set(ids)))
        for model, effort in [('gemini-3-flash-agent', 'high'), ('gemini-3.5-flash-low', 'medium'), ('gemini-3.5-flash-extra-low', 'low')]:
            self.assertIn(model, ids)
            self.assertEqual(reasoning_level(model), effort)
            self.assertIn(effort.title(), model_name(model, {}))
