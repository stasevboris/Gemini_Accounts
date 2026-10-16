import json
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import Controller, AccountError
from integrations import Integrations
from installer import install


class IntegrationTests(unittest.TestCase):
    def test_team_connection_keeps_current_models_other_mcp_servers_and_exact_backups(self):
        from team_service import TEAM_MODEL
        self.client.apply(['claude_cli', 'claude_desktop'])
        cli, mcp_path = self.client.paths()['claude_cli']
        desktop = self.client.paths()['claude_desktop'][0]
        settings = self.client.read_json(cli)
        settings['model'] = 'current-user-model'
        settings['env']['ANTHROPIC_MODEL'] = 'current-user-model'
        self.client.write_json(cli, settings)
        self.client.write_json(mcp_path, {'projects': {'test': {'keep': True}}, 'mcpServers': {'other': {'command': 'other-server'}}})
        settings = self.client.read_json(desktop)
        settings.setdefault('mcpServers', {})['other'] = {'command': 'keep-server'}
        self.client.write_json(desktop, settings)
        self.client.connect_team_clients()
        self.client.connect_team_clients()
        settings = self.client.read_json(cli)
        self.assertEqual(settings['env']['ANTHROPIC_MODEL'], 'current-user-model')
        self.assertEqual(settings['model'], 'current-user-model')
        self.assertEqual(sum(o['model'] == TEAM_MODEL for o in settings['modelPicker']['options']), 1)
        mcp = self.client.read_json(mcp_path)
        self.assertTrue(mcp['projects']['test']['keep'])
        self.assertEqual(mcp['mcpServers']['other']['command'], 'other-server')
        self.assertNotIn('local-test-key', json.dumps(mcp['mcpServers']['gemini-accounts-team']))
        desktop_data = self.client.read_json(desktop)
        self.assertEqual(desktop_data['mcpServers']['other']['command'], 'keep-server')
        picker = self.client.read_json(self.client.paths()['claude_desktop'][2])['inferenceModels']
        self.assertEqual(sum(o['name'] == TEAM_MODEL for o in picker), 1)
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.controller = Controller(proxy_dir=self.root / 'proxy', data_dir=self.root / 'data')
        self.controller.proxy_dir.mkdir()
        (self.controller.proxy_dir / 'client-key.txt').write_text('local-test-key')
        self.client = Integrations(self.controller, self.root / 'home', self.root / 'local')

    def tearDown(self):
        self.temp.cleanup()

    def test_apply_preserves_other_settings_and_restores_exact_original_bytes(self):
        paths = self.client.paths()
        cli = paths['claude_cli'][0]
        cli.parent.mkdir(parents=True)
        original = b'{"env":{"OTHER":"keep"},"permissions":{"allow":["Read"]}}\r\n'
        cli.write_bytes(original)
        codex = paths['codex'][0]
        codex.parent.mkdir(parents=True)
        codex_original = b'model = "original"\n[features]\nexample = true\n'
        codex.write_bytes(codex_original)
        self.client.apply(['claude_cli', 'codex', 'claude_desktop'])
        self.client.apply(['claude_cli', 'codex', 'claude_desktop'])
        self.assertEqual(json.loads(cli.read_text())['env']['OTHER'], 'keep')
        self.assertEqual(json.loads(cli.read_text())['permissions']['allow'], ['Read'])
        config = tomllib.loads(codex.read_text())
        self.assertEqual(config['model_provider'], 'gemini_accounts')
        self.assertTrue(config['features']['example'])
        self.assertEqual(config['model_providers']['gemini_accounts']['wire_api'], 'responses')
        self.assertEqual(tomllib.loads(paths['codex'][1].read_text())['model_provider'], 'gemini_accounts')
        self.assertNotIn(b'local-test-key', self.client.backup_path.read_bytes())
        self.client.restore()
        self.assertEqual(cli.read_bytes(), original)
        self.assertEqual(codex.read_bytes(), codex_original)
        self.assertFalse(paths['codex'][1].exists())
        self.assertTrue(all(not p.exists() for p in paths['claude_desktop']))

    def test_invalid_existing_config_is_not_overwritten(self):
        path = self.client.paths()['codex'][0]
        path.parent.mkdir(parents=True)
        path.write_text('not valid TOML')
        with self.assertRaises(tomllib.TOMLDecodeError):
            self.client.apply(['codex'])
        self.assertEqual(path.read_text(), 'not valid TOML')

    def test_legacy_model_labels_follow_aliases_and_restore_exactly(self):
        library = self.client.local / 'Claude-3p' / 'configLibrary'
        legacy = '5010c5ea-93a5-425b-aba1-6b85f3a14292'
        library.mkdir(parents=True)
        self.client.write_json(library / '_meta.json', {'appliedId': legacy})
        path = library / (legacy + '.json')
        self.client.write_json(path, {
            'inferenceGatewayBaseUrl': 'http://127.0.0.1:8317',
            'inferenceGatewayApiKey': 'keep-key',
            'inferenceModels': [{'name': 'claude-sonnet-4-5', 'labelOverride': 'Gemini Pro', 'isFamilyDefault': True}]})
        original = path.read_bytes()
        self.controller.model_aliases = lambda: {'claude-sonnet-4-5': 'gemini-pro-agent'}
        self.assertEqual(self.client.paths()['claude_desktop'][2], path)
        self.assertTrue(self.client.refresh_desktop_model_labels())
        preset = self.client.read_json(path)
        flash = next(e for e in preset['inferenceModels'] if e['labelOverride'] == 'Gemini · 3.8 Flash Low')
        self.assertEqual(flash['name'], self.client.claude_desktop_route('gemini-3.8-flash-low'))
        self.assertFalse(any(e['name'] == 'claude-sonnet-4-5' for e in preset['inferenceModels']))
        self.assertEqual(preset['inferenceGatewayApiKey'], 'keep-key')
        self.assertTrue(flash['supports1m'])
        self.assertTrue(flash['prefer1m'])
        self.assertFalse(self.client.refresh_desktop_model_labels())
        self.client.restore()
        self.assertEqual(path.read_bytes(), original)

    def test_context_setup_keeps_claude_and_gemini_separate(self):
        self.controller.preferences.update({'gemini-model': 'gemini-pro-agent', 'claude-model': 'claude-sonnet-4-6'})
        self.client.apply(['claude_cli', 'claude_desktop'])
        env = self.client.read_json(self.client.paths()['claude_cli'][0])['env']
        self.assertEqual(env['ANTHROPIC_MODEL'], self.client.claude_desktop_route('gemini-3.8-flash-low') + '[1m]')
        self.assertEqual(env['ANTHROPIC_DEFAULT_OPUS_MODEL'], 'claude-opus-4-6-thinking')
        self.assertEqual(env['ANTHROPIC_DEFAULT_SONNET_MODEL'], 'claude-sonnet-4-6')
        models = self.client.read_json(self.client.paths()['claude_desktop'][2])['inferenceModels']
        flash = next(e for e in models if e['labelOverride'].startswith('Gemini'))
        sonnet = next(e for e in models if e['name'] == 'claude-sonnet-4-6')
        self.assertTrue(flash['supports1m'])
        self.assertTrue(flash['prefer1m'])
        self.assertFalse(sonnet['supports1m'])
        self.assertFalse(sonnet['prefer1m'])

    def test_unrelated_gateway_is_not_adopted(self):
        library = self.client.local / 'Claude-3p' / 'configLibrary'
        legacy = '5010c5ea-93a5-425b-aba1-6b85f3a14292'
        self.client.write_json(library / '_meta.json', {'appliedId': legacy})
        self.client.write_json(library / (legacy + '.json'), {'inferenceGatewayBaseUrl': 'https://example.com',
            'inferenceModels': [{'name': 'other', 'labelOverride': 'Gemini Pro'}]})
        self.assertIsNone(self.client.legacy_desktop_preset())
        self.assertFalse(self.client.refresh_desktop_model_labels())
        self.assertFalse(self.client.enable_desktop_web_access())

    def test_desktop_sites_enabled_and_explicit_host_policy_survives_reconfiguration(self):
        self.client.apply(['claude_desktop'])
        path = self.client.paths()['claude_desktop'][2]
        preset = self.client.read_json(path)
        self.assertEqual(preset['coworkEgressAllowedHosts'], ['*'])
        preset.update(coworkEgressAllowedHosts=['github.com', '*.example.org'],
                      disabledBuiltinTools=['Bash'], customSetting={'keep': True})
        self.client.write_json(path, preset)
        self.client.apply(['claude_desktop'])
        self.client.refresh_desktop_model_labels()
        after = self.client.read_json(path)
        self.assertEqual(after['coworkEgressAllowedHosts'], ['github.com', '*.example.org'])
        self.assertEqual(after['disabledBuiltinTools'], ['Bash'])
        self.assertEqual(after['customSetting'], {'keep': True})
        self.assertFalse(self.client.enable_desktop_web_access())

    def test_web_migration_changes_only_policy_and_restores_original_bytes(self):
        self.client.apply(['claude_desktop'])
        path = self.client.paths()['claude_desktop'][2]
        preset = self.client.read_json(path)
        del preset['coworkEgressAllowedHosts']
        self.client.write_json(path, preset)
        self.client.backup_path.unlink()
        original = path.read_bytes()
        self.assertTrue(self.client.enable_desktop_web_access())
        after = self.client.read_json(path)
        self.assertEqual(after, {**preset, 'coworkEgressAllowedHosts': ['*']})
        self.assertFalse(self.client.enable_desktop_web_access())
        self.assertNotIn(b'local-test-key', self.client.backup_path.read_bytes())
        self.client.restore()
        self.assertEqual(path.read_bytes(), original)

    def test_empty_host_policy_remains_explicitly_disabled(self):
        self.client.apply(['claude_desktop'])
        path = self.client.paths()['claude_desktop'][2]
        preset = self.client.read_json(path)
        preset['coworkEgressAllowedHosts'] = []
        self.client.write_json(path, preset)
        self.client.apply(['claude_desktop'])
        self.client.refresh_desktop_model_labels()
        self.assertEqual(self.client.read_json(path)['coworkEgressAllowedHosts'], [])

    def test_removed_grok_provider_is_not_published(self):
        self.controller.key = 'local-key'
        self.assertFalse(hasattr(self.client, 'grok_model_choices'))
        self.assertFalse(hasattr(self.client, 'grok_model_entries'))

    def test_installer_creates_fresh_keys_and_retains_config_on_update(self):
        payload = self.root / 'payload'
        payload.mkdir()
        for name in ('GeminiAccounts.exe', 'GeminiQuotaQueue.exe', 'cli-proxy-api.exe', 'start-proxy.ps1', 'CLIProxyAPI-LICENSE.txt'):
            (payload / name).write_bytes(b'test payload')
        target = self.root / 'installed'
        install(payload, target, shortcuts=False)
        key = (target / 'ClaudeGemini' / 'client-key.txt').read_bytes()
        config = (target / 'ClaudeGemini' / 'config.yaml').read_bytes()
        install(payload, target, shortcuts=False)
        self.assertEqual(config, (target / 'ClaudeGemini' / 'config.yaml').read_bytes())
        self.assertEqual(key, (target / 'ClaudeGemini' / 'client-key.txt').read_bytes())
        other = self.root / 'other'
        install(payload, other, shortcuts=False)
        self.assertNotEqual(key, (other / 'ClaudeGemini' / 'client-key.txt').read_bytes())


if __name__ == '__main__': unittest.main()
