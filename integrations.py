"""Client presets and encrypted, reversible configuration backups."""
import base64
import copy
import json
import os
import re
import shutil
import subprocess
import threading
import sys
import tomllib
from pathlib import Path

from backend import atomic_write, dpapi, AccountError, storage_root
from model_context import extended_context, client_model_id, CONTEXT_WINDOWS

PRESET_ID = '228c90e2-d605-4ba1-b695-12a49c93a766'
BEGIN = '# BEGIN Gemini Accounts managed provider'
END = '# END Gemini Accounts managed provider'


class Integrations:
    def __init__(self, controller, home=None, local=None):
        self.controller = controller
        self.home = Path(home or Path.home())
        self.local = Path(local or os.environ.get('LOCALAPPDATA', storage_root()))
        self.windows_desktop = os.name == 'nt' or local is not None
        self.backup_path = controller.data_dir / 'client-config-backups.dpapi'
        self.lock = threading.RLock()

    @staticmethod
    def _desktop_gemini_visible(model):
        """Limit the Google picker to actual Claude models and Flash 3.8 tiers."""
        if not isinstance(model, str) or re.search(r'-(?:ga|oauth|subscription|key)-', model):
            return False
        if not model.startswith('gemini-'):
            return model.startswith(('claude-opus-', 'claude-sonnet-')) and model != 'claude-sonnet-4-5'
        return model in ('gemini-3.8-flash-high', 'gemini-3.8-flash-medium', 'gemini-3.8-flash-low')

    def google_client_models(self):
        choices = self.google_model_choices()
        models = {m for m in choices['gemini'] + choices['claude'] if self._desktop_gemini_visible(m)}
        tiers = {'high': 0, 'medium': 1, 'low': 2}
        return sorted(models, key=lambda m: (0 if m.startswith('claude-opus-') else
            1 if m.startswith('claude-sonnet-') else 2, tiers.get(m.rsplit('-', 1)[-1], 0), m))

    def google_client_model_entries(self):
        from model_names import model_name
        entries, defaults = [], set()
        for model in self.google_client_models():
            family = 'Gemini' if model.startswith('gemini-') else 'Claude'
            tier = 'opus' if model.startswith('claude-opus-') else 'sonnet' if model.startswith('claude-sonnet-') else 'haiku'
            entries.append({'name': self.claude_desktop_route(model),
                'labelOverride': family + ' · ' + model_name(model, {}), 'anthropicFamilyTier': tier,
                'isFamilyDefault': tier not in defaults,
                'supports1m': extended_context(model), 'prefer1m': extended_context(model)})
            defaults.add(tier)
        return entries

    @staticmethod
    def claude_desktop_route(model):
        if model == 'claude-haiku-4-5':
            return 'claude-haiku-4-5-ga-haiku-4-5'
        if model.startswith('claude-'):
            return model
        if not model.startswith('gemini-'):
            raise ValueError('Expected a Google subscription model')
        tier = 'haiku' if 'flash' in model or 'lite' in model else 'sonnet'
        return 'claude-' + tier + '-4-5-ga-' + model.removeprefix('gemini-').replace('.', '-')

    def google_model_choices(self):
        if not self.controller.key:
            selected = self.controller.selected_family_models()
            return {'gemini': [selected['gemini'], 'gemini-3.8-flash-low'], 'claude': [selected['claude']]}
        try:
            return self.controller.family_model_choices()
        except (AccountError, OSError, KeyError, ValueError):
            selected = self.controller.selected_family_models()
            return {'gemini': [selected['gemini'], 'gemini-3.8-flash-low'], 'claude': [selected['claude']]}

    def configure_desktop_routes(self, models, replace=True, defaults=False):
        payload = self.controller.request('/oauth-model-alias').get('oauth-model-alias') or {}
        entries = [dict(entry) for entry in payload.get('antigravity', [])]
        desired = {self.claude_desktop_route(model): model for model in models
                   if self.claude_desktop_route(model) != model}
        desired['claude-haiku-4-5'] = 'gemini-3.8-flash-low'
        if defaults:
            selected = self.controller.selected_family_models()
            desired.update({'claude-sonnet-4-5': selected['gemini'], 'gemini-selected': selected['gemini'],
                            'claude-selected': selected['claude']})
        # Remove legacy global overrides only when publishing the full model menu.
        raw_claude = {model for model in models if model.startswith('claude-')} - {'claude-sonnet-4-5', 'claude-haiku-4-5'}
        updated = [entry for entry in entries if entry.get('alias') not in desired and
                   entry.get('alias') not in raw_claude and
                   (not replace or '-4-5-ga-' not in entry.get('alias', ''))]
        from model_names import model_name
        updated += [{'alias': alias, 'name': model, 'fork': True, 'force-mapping': True,
                     'display-name': model_name(model, {})} for alias, model in desired.items() if alias != model]
        if sorted(updated, key=lambda e: e.get('alias', '')) != sorted(entries, key=lambda e: e.get('alias', '')):
            self.controller.request('/oauth-model-alias', 'PATCH', {'provider': 'antigravity', 'aliases': updated})
            return True
        return False

    def reconcile_desktop_routes(self):
        """Heal our approved routes and migrate an absent Desktop web policy."""
        if not self.legacy_desktop_preset():
            return False
        preset_path = self.paths()['claude_desktop'][2]
        if str(preset_path.resolve()) not in self.backups():
            return False
        api_changed = self.configure_desktop_api_routes()
        web_changed = self.enable_desktop_web_access()
        picker_changed = self.refresh_desktop_model_labels()
        preset = self.read_json(preset_path)
        routes = {entry.get('name') for entry in preset.get('inferenceModels', []) if isinstance(entry, dict)}
        selected = self.controller.selected_family_models()
        catalog = self.read_json(self.controller.proxy_dir / 'cliproxy-models.json')
        models = {entry['id'] for entry in catalog.get('antigravity', [])
                  if isinstance(entry, dict) and isinstance(entry.get('id'), str)
                  and entry['id'].startswith(('gemini-', 'claude-'))}
        models.update([selected['gemini'], selected['claude'], 'gemini-3.8-flash-low', 'claude-haiku-4-5'])
        known = {self.claude_desktop_route(model): model for model in models}
        known.update({'claude-sonnet-4-5': selected['gemini'], 'gemini-selected': selected['gemini'],
                      'claude-selected': selected['claude'], 'claude-haiku-4-5': 'gemini-3.8-flash-low'})
        owned = {route for route in routes if isinstance(route, str) and
                 (route in known or re.fullmatch(r'claude-(?:sonnet|haiku)-4-5-ga-[a-z0-9-]+', route))}
        if not owned:
            return api_changed or web_changed or picker_changed
        unknown = owned - known.keys()
        if unknown:
            raise AccountError('Connected Google models are missing from the gateway catalog. Reconnect Claude Desktop.')
        desired = {route: known[route] for route in owned if route != known[route]}
        desired['claude-haiku-4-5'] = 'gemini-3.8-flash-low'
        payload = self.controller.request('/oauth-model-alias').get('oauth-model-alias') or {}
        entries = [dict(entry) for entry in payload.get('antigravity', [])]
        live = {entry.get('alias'): entry.get('name') for entry in entries}
        self_routes = {route for route in owned if route == known[route] and route in live}
        if not self_routes and all(live.get(route) == model for route, model in desired.items()):
            return api_changed or web_changed or picker_changed
        from model_names import model_name
        updated = [entry for entry in entries if entry.get('alias') not in desired and entry.get('alias') not in self_routes]
        updated += [{'alias': route, 'name': model, 'fork': True, 'force-mapping': True,
                     'display-name': model_name(model, {})} for route, model in desired.items()]
        self.controller.request('/oauth-model-alias', 'PATCH', {'provider': 'antigravity', 'aliases': updated})
        return True

    def configure_desktop_api_routes(self):
        """Publish separate API and subscription routes, preserving custom aliases."""
        if not self.controller.key:
            return False
        from api_keys import catalog, desktop_model_id, is_desktop_model
        from chatgpt_auth import desktop_model_id as oauth_id, is_desktop_model as is_oauth
        from claude_auth import desktop_model_id as claude_id, is_desktop_model as is_claude
        from grok_auth import is_desktop_model as is_grok
        from kimi_auth import is_desktop_model as is_kimi
        with self.lock:
            payload = self.controller.request('/oauth-model-alias').get('oauth-model-alias') or {}
            entries = [dict(entry) for entry in payload.get('antigravity', [])]
            updated = [entry for entry in entries if not (is_desktop_model(entry.get('alias')) or is_oauth(entry.get('alias')) or is_grok(entry.get('alias')) or is_kimi(entry.get('alias')))]
            updated += [{'alias': desktop_model_id(entry), 'name': entry['id'], 'fork': True,
                         'force-mapping': True, 'display-name': entry['label']}
                        for entry in catalog(self.controller)]
            updated += [{'alias': oauth_id(model), 'name': model, 'fork': True, 'force-mapping': True,
                         'display-name': 'ChatGPT · ' + model} for model in self.chatgpt_model_choices()]
            changed = False
            if sorted(updated, key=lambda e: e.get('alias', '')) != sorted(entries, key=lambda e: e.get('alias', '')):
                self.controller.request('/oauth-model-alias', 'PATCH', {'provider': 'antigravity', 'aliases': updated})
                changed = True
            entries = [dict(entry) for entry in payload.get('claude', [])]
            updated = [entry for entry in entries if not is_claude(entry.get('alias'))]
            updated += [{'alias': claude_id(model), 'name': model, 'fork': True,
                         'display-name': 'Claude subscription · ' + model}
                        for model in self.claude_subscription_model_choices()]
            if sorted(updated, key=lambda e: e.get('alias', '')) != sorted(entries, key=lambda e: e.get('alias', '')):
                self.controller.request('/oauth-model-alias', 'PATCH', {'provider': 'claude', 'aliases': updated})
                changed = True
            # Remove legacy Grok/Kimi routes from the published desktop catalog.
            for provider in ('xai', 'kimi', 'kimi-ai'):
                legacy = payload.get(provider, [])
                updated = [e for e in legacy if not (is_grok(e.get('alias')) or is_kimi(e.get('alias')))]
                if legacy != updated:
                    self.controller.request('/oauth-model-alias', 'PATCH', {'provider': provider, 'aliases': updated})
                    changed = True
            return changed

    def detected(self):
        return {
            'claude_desktop': self.windows_desktop and any((self.local / p).exists() for p in ('AnthropicClaude', 'Claude-3p', 'Claude')),
            'claude_cli': bool(shutil.which('claude') or (self.home / '.claude').exists()),
            'codex': bool(shutil.which('codex') or (self.home / '.codex').exists()),
        }

    def paths(self):
        library = self.local / 'Claude-3p' / 'configLibrary'
        preset_id = self.legacy_desktop_preset() or PRESET_ID
        return {
            'claude_cli': [self.home / '.claude' / 'settings.json', self.home / '.claude.json'],
            'codex': [self.home / '.codex' / 'config.toml', self.home / '.codex' / 'gemini-accounts.config.toml',
                      self.home / '.codex' / 'gemini-accounts-models.json'],
            'claude_desktop': [self.local / 'Claude-3p' / 'claude_desktop_config.json',
                               library / '_meta.json', library / (preset_id + '.json')],
        }

    def legacy_desktop_preset(self):
        """Recognize our original localhost preset without adopting unrelated gateways."""
        library = self.local / 'Claude-3p' / 'configLibrary'
        try:
            preset_id = self.read_json(library / '_meta.json').get('appliedId', '')
            if not re.fullmatch(r'[a-fA-F0-9-]{36}', preset_id):
                return None
            preset = self.read_json(library / (preset_id + '.json'))
            models = preset.get('inferenceModels', [])
            if (preset.get('inferenceGatewayBaseUrl', '').rstrip('/') == 'http://127.0.0.1:8317'
                    and (preset.get('deploymentDisplayName') == 'Gemini Accounts'
                         or any(m.get('labelOverride', '').startswith('Gemini') for m in models))):
                return preset_id
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        return None

    def refresh_desktop_model_labels(self):
        """Replace only our picker entries; retain custom rows and host settings."""
        if not self.legacy_desktop_preset():
            return self.configure_desktop_api_routes()
        path = self.paths()['claude_desktop'][2]
        preset = self.read_json(path)
        original = copy.deepcopy(preset.get('inferenceModels', []))
        changed = self.default_desktop_web_access(preset)
        from api_keys import is_model
        from chatgpt_auth import is_desktop_model as is_oauth
        from claude_auth import is_desktop_model as is_claude
        from grok_auth import is_desktop_model as is_grok
        from kimi_auth import is_desktop_model as is_kimi
        catalog = self.read_json(self.controller.proxy_dir / 'cliproxy-models.json')
        google_names = {m['id'] for m in catalog.get('antigravity', [])
                        if isinstance(m, dict) and isinstance(m.get('id'), str)}
        google_names.update(('claude-sonnet-4-5', 'claude-haiku-4-5', 'claude-selected', 'gemini-selected'))
        google = self.google_client_model_entries()
        google_names.update(e['name'] for e in google)
        def managed(entry):
            name = entry.get('name', '')
            label = entry.get('labelOverride', '')
            from team_service import TEAM_MODEL
            return (name == TEAM_MODEL or is_model(name) or is_oauth(name) or is_claude(name) or is_grok(name) or is_kimi(name) or
                    '-4-5-ga-' in name or name in google_names and label.startswith(('Gemini', 'Claude')) or
                    name.startswith(('grok-', 'kimi-')) and label.startswith(('Grok · ', 'Kimi · ', 'Kimi.ai · ')))
        custom = [e for e in original if isinstance(e, dict) and not managed(e)]
        preset['inferenceModels'] = custom + [self.team_model_entry()] + google + self.api_model_entries() + self.chatgpt_model_entries() + self.claude_subscription_model_entries()
        routes_changed = False
        if self.controller.key:
            routes_changed = self.configure_desktop_routes(self.google_client_models(), replace=False)
        api_changed = self.configure_desktop_api_routes()
        changed = changed or original != preset['inferenceModels']
        if changed:
            with self.lock:
                self.remember([path])
                self.write_json(path, preset)
        return changed or routes_changed or api_changed

    def api_model_entries(self):
        from api_keys import catalog, desktop_model_id
        return [{'name': desktop_model_id(entry), 'labelOverride': entry['label'],
                 'anthropicFamilyTier': 'haiku' if 'haiku' in entry['model'] else 'opus' if 'opus' in entry['model'] else 'sonnet',
                 'isFamilyDefault': False, 'supports1m': False, 'prefer1m': False}
                for entry in catalog(self.controller)]

    def team_model_entry(self):
        from team_service import TEAM_MODEL
        return {'name': TEAM_MODEL, 'labelOverride': 'Команда агентов' if self.controller.preferences.get('language') == 'ru' else 'Agent team',
                'anthropicFamilyTier': 'sonnet', 'isFamilyDefault': False, 'supports1m': False, 'prefer1m': False}

    def team_mcp_entry(self):
        from runtime import VERSION
        candidates = [self.controller.data_dir / 'team-mcp' / VERSION / 'GeminiTeamMCP.exe',
                      self.local / 'GeminiAccounts' / 'team-mcp' / VERSION / 'GeminiTeamMCP.exe',
                      self.controller.data_dir / 'GeminiTeamMCP.exe']
        executable = next((p for p in candidates if p.is_file()), candidates[0])
        if executable.is_file():
            command, args = str(executable), []
        elif not getattr(sys, 'frozen', False):
            command, args = sys.executable, [str(Path(__file__).with_name('team_mcp.py'))]
        else:
            raise AccountError('Install the current Gemini Accounts build with GeminiTeamMCP.exe first.')
        return {'type': 'stdio', 'command': command, 'args': args,
                'env': {'GEMINI_TEAM_DATA_DIR': str(self.controller.data_dir), 'GEMINI_TEAM_PROXY_DIR': str(self.controller.proxy_dir)}}

    def connect_team_clients(self):
        """Add team entries only to already connected clients; keep their model/env."""
        changed = []
        with self.lock:
            entry = self.team_mcp_entry()
            if self.legacy_desktop_preset():
                desktop = self.paths()['claude_desktop'][0]
                self.remember([desktop])
                settings = self.read_json(desktop)
                settings.setdefault('mcpServers', {})['gemini-accounts-team'] = entry
                self.write_json(desktop, settings)
                self.refresh_desktop_model_labels()
                changed.append('claude_desktop')
            settings_path, mcp_path = self.paths()['claude_cli']
            settings = self.read_json(settings_path)
            if settings.get('env', {}).get('ANTHROPIC_BASE_URL', '').rstrip('/') == 'http://127.0.0.1:8317':
                self.remember([settings_path, mcp_path])
                options = settings.setdefault('modelPicker', {}).setdefault('options', [])
                from grok_auth import is_desktop_model as is_grok
                from kimi_auth import is_desktop_model as is_kimi
                options[:] = [o for o in options if not (is_grok(o.get('model')) or is_kimi(o.get('model'))
                    or str(o.get('label', '')).startswith(('Grok · ', 'Kimi · ', 'Kimi.ai · ')))]
                model = self.team_model_entry()
                options[:] = [o for o in options if o.get('model') != model['name']]
                options.append({'model': model['name'], 'label': model['labelOverride']})
                mcp = self.read_json(mcp_path)
                mcp.setdefault('mcpServers', {})['gemini-accounts-team'] = entry
                self.write_json(settings_path, settings)
                self.write_json(mcp_path, mcp)
                changed.append('claude_cli')
        if not changed:
            raise AccountError('Connect Claude Desktop or Claude Code under Connections first.')
        return changed

    def chatgpt_model_choices(self):
        if not self.controller.key:
            return []
        try:
            return self.controller.chatgpt_model_choices()
        except (AccountError, OSError, ValueError, KeyError):
            return []

    def chatgpt_model_entries(self):
        from chatgpt_auth import desktop_model_id
        return [{'name': desktop_model_id(model), 'labelOverride': 'ChatGPT · ' + model,
                 'anthropicFamilyTier': 'sonnet', 'isFamilyDefault': False,
                 'supports1m': False, 'prefer1m': False} for model in self.chatgpt_model_choices()]

    def claude_subscription_model_choices(self):
        if not self.controller.key:
            return []
        try:
            return self.controller.claude_subscription_model_choices()
        except (AccountError, OSError, ValueError, KeyError):
            return []

    def claude_subscription_model_entries(self):
        from claude_auth import desktop_model_id
        from model_names import model_name
        return [{'name': desktop_model_id(model), 'labelOverride': 'Claude subscription · ' + model_name(model, {}),
                 'anthropicFamilyTier': 'haiku' if 'haiku' in model else 'opus' if 'opus' in model else 'sonnet',
                 'isFamilyDefault': False, 'supports1m': False, 'prefer1m': False}
                for model in self.claude_subscription_model_choices()]

    def backups(self):
        if not self.backup_path.exists():
            return {}
        try:
            return json.loads(dpapi(self.backup_path.read_bytes(), decrypt=True))
        except (OSError, ValueError) as error:
            raise AccountError('Could not unlock the configuration backup.') from error

    def remember(self, paths):
        saved = self.backups()
        for path in paths:
            key = str(path.resolve())
            if key not in saved:
                saved[key] = base64.b64encode(path.read_bytes()).decode() if path.exists() else None
        atomic_write(self.backup_path, dpapi(json.dumps(saved).encode()))

    @staticmethod
    def read_json(path):
        return json.loads(path.read_text('utf-8-sig')) if path.exists() else {}

    @staticmethod
    def write_json(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode())

    @staticmethod
    def default_desktop_web_access(preset):
        """Allow links in our Desktop preset without replacing explicit host rules."""
        if 'coworkEgressAllowedHosts' in preset:
            return False
        preset['coworkEgressAllowedHosts'] = ['*']
        return True

    def enable_desktop_web_access(self):
        """Migrate only our existing preset, retaining models and credentials."""
        if not self.legacy_desktop_preset():
            return False
        with self.lock:
            path = self.paths()['claude_desktop'][2]
            preset = self.read_json(path)
            if not self.default_desktop_web_access(preset):
                return False
            self.remember([path])
            self.write_json(path, preset)
            return True

    def apply(self, clients):
        clients = list(dict.fromkeys(clients))
        if not clients or any(client not in self.paths() for client in clients):
            raise AccountError('Choose applications to connect.')
        if 'claude_desktop' in clients and not self.windows_desktop:
            raise AccountError('Automatic Claude Desktop setup is available on Windows. Use Claude Code CLI on this platform.')
        key = (self.controller.proxy_dir / 'client-key.txt').read_text('utf-8-sig').strip()
        if not key:
            raise AccountError('Local connection key not found.')
        # Validate existing documents before making any changes.
        paths = [p for client in clients for p in self.paths()[client]]
        for path in paths:
            if path.exists():
                if path.suffix == '.json':
                    self.read_json(path)
                else:
                    tomllib.loads(path.read_text('utf-8-sig'))
        with self.lock:
            before = {p: p.read_bytes() if p.exists() else None for p in paths}
            self.remember(paths)
            alias_before = None
            if self.controller.key:
                alias_before = self.controller.request('/oauth-model-alias').get('oauth-model-alias') or {}
            try:
                for client in clients:
                    getattr(self, 'configure_' + client)(key)
            except Exception:
                for path, data in before.items():
                    if data is None:
                        path.unlink(missing_ok=True)
                    else:
                        atomic_write(path, data)
                if alias_before is not None:
                    live = self.controller.request('/oauth-model-alias').get('oauth-model-alias') or {}
                    for provider in ('antigravity', 'claude', 'xai', 'kimi', 'kimi-ai'):
                        if live.get(provider) != alias_before.get(provider):
                            self.controller.request('/oauth-model-alias', 'PATCH', {'provider': provider, 'aliases': alias_before.get(provider, [])})
                raise
        return clients

    def configure_claude_cli(self, key):
        if self.controller.key:
            self.configure_desktop_routes(self.google_client_models(), replace=False)
        self.configure_desktop_api_routes()
        path = self.paths()['claude_cli'][0]
        settings = self.read_json(path)
        families = self.controller.selected_family_models()
        visible = self.google_client_models()
        preferred = families['gemini'] if families['gemini'] in visible else next(
            (m for m in visible if m.startswith('gemini-')), 'gemini-3.8-flash-low')
        gemini = client_model_id(self.claude_desktop_route(preferred), preferred)
        sonnet = next((m for m in visible if m.startswith('claude-sonnet-')), 'claude-sonnet-4-6')
        opus = next((m for m in visible if m.startswith('claude-opus-')), 'claude-opus-4-6-thinking')
        settings.setdefault('env', {}).update({
            'ANTHROPIC_BASE_URL': 'http://127.0.0.1:8317',
            'ANTHROPIC_AUTH_TOKEN': key, 'ANTHROPIC_API_KEY': '',
            'ANTHROPIC_MODEL': gemini,
            'ANTHROPIC_DEFAULT_SONNET_MODEL': sonnet,
            'ANTHROPIC_DEFAULT_HAIKU_MODEL': client_model_id(self.claude_desktop_route('gemini-3.8-flash-low'), 'gemini-3.8-flash-low'),
            'ANTHROPIC_DEFAULT_OPUS_MODEL': opus,
            'CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY': '1',
            'API_TIMEOUT_MS': '604800000', 'CLAUDE_ENABLE_STREAM_WATCHDOG': '0',
        })
        entries = ([self.team_model_entry()] + self.google_client_model_entries() + self.api_model_entries() +
                   self.chatgpt_model_entries() + self.claude_subscription_model_entries())
        settings['modelPicker'] = {'replaceBuiltInOptions': True,
            'options': [{'model': e['name'] + ('[1m]' if e.get('supports1m') else ''),
                         'label': e['labelOverride']} for e in entries]}
        for entry in settings['modelPicker']['options']:
            if entry['model'] == 'claude-opus-4-6-thinking':
                entry['behavesAs'] = 'claude-opus-4-6'
        self.write_json(path, settings)
        mcp_path = self.paths()['claude_cli'][1]
        mcp = self.read_json(mcp_path)
        mcp.setdefault('mcpServers', {})['gemini-accounts-team'] = self.team_mcp_entry()
        self.write_json(mcp_path, mcp)

    def provider_toml(self, key):
        return '\n'.join([
            '[model_providers.gemini_accounts]', 'name = "Gemini Accounts"',
            'base_url = "http://127.0.0.1:8317/v1"', 'wire_api = "responses"',
            'experimental_bearer_token = ' + json.dumps(key),
            'stream_idle_timeout_ms = 604800000', 'request_max_retries = 2',
            'supports_websockets = false', '',
        ])

    def configure_codex(self, key):
        self.configure_desktop_api_routes()
        path, profile, catalog_path = self.paths()['codex']
        text = path.read_text('utf-8-sig') if path.exists() else ''
        text = re.sub(re.escape(BEGIN) + r'.*?' + re.escape(END) + r'\s*', '', text, flags=re.S)
        config = tomllib.loads(text)
        if 'gemini_accounts' in config.get('model_providers', {}):
            raise AccountError('The gemini_accounts provider name is already used by another configuration.')
        split = re.search(r'^\s*\[', text, re.M)
        root, tables = (text[:split.start()], text[split.start():]) if split else (text, '')
        previous_catalog = config.get('model_catalog_json')
        root = re.sub(r'^\s*(model|model_provider|model_catalog_json)\s*=.*\n?', '', root, flags=re.M)
        model = 'gemini-selected' if self.controller.preferences.get('gemini-model') else self.controller.preferences.get('pro-model') or self.controller.model_aliases().get('claude-sonnet-4-5', 'gemini-3.1-pro-low')
        defaults = 'model = ' + json.dumps(model) + '\nmodel_provider = "gemini_accounts"\n'
        if self.write_codex_catalog(catalog_path, previous_catalog):
            defaults += 'model_catalog_json = ' + json.dumps(str(catalog_path.resolve())) + '\n'
        updated = defaults + root + '\n' + tables.rstrip() + '\n\n' + BEGIN + '\n' + self.provider_toml(key) + END + '\n'
        tomllib.loads(updated)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, updated.encode())
        atomic_write(profile, (defaults + '\n' + self.provider_toml(key)).encode())

    def write_codex_catalog(self, target, previous_catalog=None):
        source = Path(previous_catalog).expanduser() if previous_catalog and Path(previous_catalog) != target else self.home / '.codex' / 'models_cache.json'
        if not source.exists() and target.exists():
            source = target
        if not source.exists():
            return False
        catalog = self.read_json(source)
        models = catalog.get('models')
        if not isinstance(models, list) or not models:
            return False
        from model_names import model_name, reasoning_level
        choices = self.google_model_choices()
        existing = {entry.get('slug') for entry in models}
        template = next((entry for entry in models if isinstance(entry, dict)), None)
        if template is None:
            return False
        from claude_auth import desktop_model_id
        subscription = {desktop_model_id(model): model for model in self.claude_subscription_model_choices()}
        for model in choices['gemini'] + choices['claude'] + self.chatgpt_model_choices() + list(subscription):
            if model in existing:
                continue
            entry = copy.deepcopy(template)
            family = ('Gemini' if model.startswith('gemini-')
                      else 'ChatGPT' if model.startswith('gpt-') else 'Claude')
            window = CONTEXT_WINDOWS.get(model, 200000)
            display = ('Claude subscription · ' + model_name(subscription[model], {})) if model in subscription else family + ' · ' + model_name(model, {})
            description = ('Claude subscription' if model in subscription else 'ChatGPT' if model.startswith('gpt-')
                           else 'Google subscription') + ' via Gemini Accounts'
            entry.update(slug=model, display_name=display, description=description, priority=50,
                         model_messages={}, base_instructions='You are a helpful coding assistant.',
                         context_window=window, max_context_window=window,
                         additional_speed_tiers=[], service_tiers=[], availability_nux=None, upgrade=None)
            effort = (template.get('default_reasoning_level', 'medium') if model.startswith('gpt-') else
                      reasoning_level(model))
            entry['default_reasoning_level'] = effort
            entry['supported_reasoning_levels'] = copy.deepcopy(template.get('supported_reasoning_levels', [])) if model.startswith('gpt-') else [{'effort': effort, 'description': effort.title()}]
            models.append(entry)
            existing.add(model)
        self.write_json(target, catalog)
        return True

    def configure_claude_desktop(self, key):
        desktop, meta_path, preset = self.paths()['claude_desktop']
        if self.controller.key:
            # Hidden legacy routes remain valid for existing conversations.
            self.configure_desktop_routes(self.google_client_models(), replace=False, defaults=True)
            self.configure_desktop_api_routes()
        preset_data = self.read_json(preset)
        preset_data.update({
            'deploymentDisplayName': 'Gemini Accounts', 'inferenceCredentialKind': 'static',
            'modelDiscoveryEnabled': False, 'inferenceGatewayAuthScheme': 'bearer',
            'inferenceProvider': 'gateway', 'inferenceGatewayApiKey': key,
            'inferenceGatewayBaseUrl': 'http://127.0.0.1:8317',
            'claudeAiImport': {'bannerBehavior': 'detect', 'exportEnabled': True, 'enabled': True},
            'inferenceModels': ([self.team_model_entry()] + self.google_client_model_entries() + self.api_model_entries() +
                self.chatgpt_model_entries() + self.claude_subscription_model_entries()),
        })
        self.default_desktop_web_access(preset_data)
        self.write_json(preset, preset_data)
        meta = self.read_json(meta_path)
        entries = meta.setdefault('entries', [])
        preset_id = preset.stem
        if not any(e.get('id') == preset_id for e in entries):
            entries.append({'id': preset_id, 'name': 'Gemini Accounts'})
        meta['appliedId'] = preset_id
        self.write_json(meta_path, meta)
        settings = self.read_json(desktop)
        settings['deploymentMode'] = '3p'
        settings.setdefault('mcpServers', {})['gemini-accounts-team'] = self.team_mcp_entry()
        self.write_json(desktop, settings)

    def restore(self):
        with self.lock:
            saved = self.backups()
            allowed = {str(p.resolve()) for group in self.paths().values() for p in group}
            if any(path not in allowed for path in saved):
                raise AccountError('The backup contains an unexpected path. Restoration cancelled.')
            for name, data in saved.items():
                path = Path(name)
                if data is None:
                    path.unlink(missing_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    atomic_write(path, base64.b64decode(data))
            self.backup_path.unlink(missing_ok=True)
            return len(saved)

    @staticmethod
    def restart_desktop(clients):
        """Called only after separate, explicit consent to interrupt running clients."""
        if os.name != 'nt':
            raise AccountError('Restart desktop clients manually on this platform.')
        env = os.environ.copy()
        env['GEMINI_ACCOUNTS_RESTART_CLIENTS'] = json.dumps(clients)
        script = r'''
$targets = ConvertFrom-Json $env:GEMINI_ACCOUNTS_RESTART_CLIENTS
$processes = Get-CimInstance Win32_Process
if ('claude_desktop' -in $targets) {
    $matches = @($processes | Where-Object {$_.Name -eq 'claude.exe' -and $_.ExecutablePath -like '*\AnthropicClaude\*'})
    $exe = $matches | Select-Object -First 1 -ExpandProperty ExecutablePath
    $matches | ForEach-Object {Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue}
    if ($exe) {Start-Sleep -Milliseconds 500; Start-Process -FilePath $exe}
}
if ('codex' -in $targets) {
    $matches = @($processes | Where-Object {$_.Name -in @('ChatGPT.exe','Codex.exe') -and ($_.ExecutablePath -like '*\OpenAI.Codex_*\app\*' -or $_.ExecutablePath -like '*\OpenAI\Codex\app\*')})
    if ($matches.Count) {
        $exe = $matches | Select-Object -First 1 -ExpandProperty ExecutablePath
        $matches | ForEach-Object {Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue}
        Start-Sleep -Milliseconds 500
        $app = Get-StartApps | Where-Object {$_.AppID -like 'OpenAI.Codex*'} | Select-Object -First 1
        if ($app) {Start-Process explorer.exe -ArgumentList ('shell:AppsFolder\' + $app.AppID)} else {Start-Process -FilePath $exe}
    }
}
'''
        subprocess.run(['powershell.exe', '-NoProfile', '-Command', script], env=env,
                       creationflags=subprocess.CREATE_NO_WINDOW, check=True, timeout=30)
