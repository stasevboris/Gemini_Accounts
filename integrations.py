"""Client presets and encrypted, reversible configuration backups."""
import base64
import copy
import json
import os
import re
import shutil
import subprocess
import threading
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
            return {'gemini': [selected['gemini'], 'gemini-3-flash'], 'claude': [selected['claude']]}
        try:
            return self.controller.family_model_choices()
        except (AccountError, OSError, KeyError, ValueError):
            selected = self.controller.selected_family_models()
            return {'gemini': [selected['gemini'], 'gemini-3-flash'], 'claude': [selected['claude']]}

    def configure_desktop_routes(self, models, replace=True, defaults=False):
        payload = self.controller.request('/oauth-model-alias').get('oauth-model-alias') or {}
        entries = [dict(entry) for entry in payload.get('antigravity', [])]
        desired = {self.claude_desktop_route(model): model for model in models
                   if self.claude_desktop_route(model) != model}
        desired['claude-haiku-4-5'] = 'gemini-3-flash'
        if defaults:
            selected = self.controller.selected_family_models()
            desired.update({'claude-sonnet-4-5': selected['gemini'], 'gemini-selected': selected['gemini'],
                            'claude-selected': selected['claude']})
        # Remove legacy global overrides only when publishing the full model menu.
        raw_claude = {model for model in models if model.startswith('claude-')} - {'claude-sonnet-4-5', 'claude-haiku-4-5'}
        updated = [entry for entry in entries if entry.get('alias') not in desired and
                   (not replace or (entry.get('alias') not in raw_claude and '-4-5-ga-' not in entry.get('alias', '')))]
        from model_names import model_name
        updated += [{'alias': alias, 'name': model, 'fork': True, 'force-mapping': True,
                     'display-name': model_name(model, {})} for alias, model in desired.items() if alias != model]
        if updated != entries:
            self.controller.request('/oauth-model-alias', 'PATCH', {'provider': 'antigravity', 'aliases': updated})

    def reconcile_desktop_routes(self):
        """Heal only routes from our previously approved preset; never rewrite clients."""
        if not self.legacy_desktop_preset():
            return False
        preset_path = self.paths()['claude_desktop'][2]
        if str(preset_path.resolve()) not in self.backups():
            return False
        preset = self.read_json(preset_path)
        routes = {entry.get('name') for entry in preset.get('inferenceModels', []) if isinstance(entry, dict)}
        selected = self.controller.selected_family_models()
        catalog = self.read_json(self.controller.proxy_dir / 'cliproxy-models.json')
        models = {entry['id'] for entry in catalog.get('antigravity', [])
                  if isinstance(entry, dict) and isinstance(entry.get('id'), str)
                  and entry['id'].startswith(('gemini-', 'claude-'))}
        models.update([selected['gemini'], selected['claude'], 'gemini-3-flash', 'claude-haiku-4-5'])
        known = {self.claude_desktop_route(model): model for model in models}
        known.update({'claude-sonnet-4-5': selected['gemini'], 'gemini-selected': selected['gemini'],
                      'claude-selected': selected['claude'], 'claude-haiku-4-5': 'gemini-3-flash'})
        owned = {route for route in routes if isinstance(route, str) and
                 (route in known or re.fullmatch(r'claude-(?:sonnet|haiku)-4-5-ga-[a-z0-9-]+', route))}
        if not owned:
            return False
        unknown = owned - known.keys()
        if unknown:
            raise AccountError('Connected Google models are missing from the gateway catalog. Reconnect Claude Desktop.')
        desired = {route: known[route] for route in owned if route != known[route]}
        desired['claude-haiku-4-5'] = 'gemini-3-flash'
        payload = self.controller.request('/oauth-model-alias').get('oauth-model-alias') or {}
        entries = [dict(entry) for entry in payload.get('antigravity', [])]
        live = {entry.get('alias'): entry.get('name') for entry in entries}
        self_routes = {route for route in owned if route == known[route] and route in live}
        if not self_routes and all(live.get(route) == model for route, model in desired.items()):
            return False
        from model_names import model_name
        updated = [entry for entry in entries if entry.get('alias') not in desired and entry.get('alias') not in self_routes]
        updated += [{'alias': route, 'name': model, 'fork': True, 'force-mapping': True,
                     'display-name': model_name(model, {})} for route, model in desired.items()]
        self.controller.request('/oauth-model-alias', 'PATCH', {'provider': 'antigravity', 'aliases': updated})
        return True

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
            'claude_cli': [self.home / '.claude' / 'settings.json'],
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
                    and any(m.get('labelOverride', '').startswith('Gemini') for m in models)):
                return preset_id
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        return None

    def refresh_desktop_model_labels(self):
        """Refresh subscription labels and independent API entries in our preset."""
        if not self.legacy_desktop_preset():
            return False
        path = self.paths()['claude_desktop'][2]
        preset = self.read_json(path)
        aliases = self.controller.model_aliases()
        catalog = self.read_json(self.controller.proxy_dir / 'cliproxy-models.json')
        known = [entry['id'] for entry in catalog.get('antigravity', []) if isinstance(entry, dict)
                 and isinstance(entry.get('id'), str) and entry['id'].startswith(('gemini-', 'claude-'))]
        selected = self.controller.selected_family_models()
        known += [selected['gemini'], selected['claude'], 'gemini-3-flash', 'claude-haiku-4-5']
        aliases = {**{self.claude_desktop_route(model): model for model in known}, **aliases}
        from model_names import model_name
        changed = False
        original = copy.deepcopy(preset.get('inferenceModels', []))
        preset['inferenceModels'] = [entry for entry in preset.get('inferenceModels', []) if not entry['name'].startswith('api/')]
        for entry in preset.get('inferenceModels', []):
            model = aliases.get(entry['name'], entry['name'])
            family = 'Gemini' if model.startswith('gemini-') else 'Claude' if model.startswith('claude-') else ''
            if not family:
                continue
            label = family + ' · ' + model_name(model, {})
            if entry.get('labelOverride') != label:
                entry['labelOverride'] = label
                changed = True
            for flag in ('supports1m', 'prefer1m'):
                if entry.get(flag, False) != extended_context(model):
                    entry[flag] = extended_context(model)
                    changed = True
        preset['inferenceModels'].extend(self.api_model_entries())
        changed = changed or original != preset['inferenceModels']
        if changed:
            with self.lock:
                self.remember([path])
                self.write_json(path, preset)
        return changed

    def api_model_entries(self):
        from api_keys import catalog
        return [{'name': entry['id'], 'labelOverride': entry['label'],
                 'anthropicFamilyTier': 'haiku' if 'haiku' in entry['model'] else 'opus' if 'opus' in entry['model'] else 'sonnet',
                 'isFamilyDefault': False, 'supports1m': False, 'prefer1m': False}
                for entry in catalog(self.controller)]

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
            if 'claude_desktop' in clients and self.controller.key:
                alias_before = (self.controller.request('/oauth-model-alias').get('oauth-model-alias') or {}).get('antigravity', [])
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
                    self.controller.request('/oauth-model-alias', 'PATCH', {'provider': 'antigravity', 'aliases': alias_before})
                raise
        return clients

    def configure_claude_cli(self, key):
        path = self.paths()['claude_cli'][0]
        settings = self.read_json(path)
        families = self.controller.selected_family_models()
        gemini = client_model_id('claude-sonnet-4-5', families['gemini'])
        claude = client_model_id('claude-selected', families['claude'])
        settings.setdefault('env', {}).update({
            'ANTHROPIC_BASE_URL': 'http://127.0.0.1:8317',
            'ANTHROPIC_AUTH_TOKEN': key, 'ANTHROPIC_API_KEY': '',
            'ANTHROPIC_MODEL': gemini,
            'ANTHROPIC_DEFAULT_SONNET_MODEL': gemini,
            'ANTHROPIC_DEFAULT_HAIKU_MODEL': client_model_id('gemini-3-flash', 'gemini-3-flash'),
            'ANTHROPIC_DEFAULT_OPUS_MODEL': claude if self.controller.preferences.get('claude-model') else 'claude-opus-4-6-thinking',
            'CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY': '1',
            'API_TIMEOUT_MS': '604800000', 'CLAUDE_ENABLE_STREAM_WATCHDOG': '0',
        })
        self.write_json(path, settings)

    def provider_toml(self, key):
        return '\n'.join([
            '[model_providers.gemini_accounts]', 'name = "Gemini Accounts"',
            'base_url = "http://127.0.0.1:8317/v1"', 'wire_api = "responses"',
            'experimental_bearer_token = ' + json.dumps(key),
            'stream_idle_timeout_ms = 604800000', 'request_max_retries = 2',
            'supports_websockets = false', '',
        ])

    def configure_codex(self, key):
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
        for model in choices['gemini'] + choices['claude']:
            if model in existing:
                continue
            entry = copy.deepcopy(template)
            family = 'Gemini' if model.startswith('gemini-') else 'Claude'
            window = CONTEXT_WINDOWS.get(model, 200000)
            entry.update(slug=model, display_name=family + ' · ' + model_name(model, {}),
                         description='Google subscription via Gemini Accounts', priority=50,
                         model_messages={}, base_instructions='You are a helpful coding assistant.',
                         context_window=window, max_context_window=window,
                         additional_speed_tiers=[], service_tiers=[], availability_nux=None, upgrade=None)
            effort = reasoning_level(model)
            entry['default_reasoning_level'] = effort
            entry['supported_reasoning_levels'] = [{'effort': effort, 'description': effort.title()}]
            models.append(entry)
            existing.add(model)
        self.write_json(target, catalog)
        return True

    def configure_claude_desktop(self, key):
        desktop, meta_path, preset = self.paths()['claude_desktop']
        family_models = self.controller.selected_family_models()
        from model_names import model_name
        models = [('claude-sonnet-4-5', 'Gemini · ' + model_name(family_models['gemini'], {}), 'sonnet', True),
                  ('claude-selected' if self.controller.preferences.get('claude-model') else 'claude-opus-4-6-thinking',
                   'Claude · ' + model_name(family_models['claude'] if self.controller.preferences.get('claude-model') else 'claude-opus-4-6-thinking', {}), 'opus', True),
                  (self.claude_desktop_route('gemini-3-flash'), 'Gemini · 3 Flash', 'haiku', True)]
        choices = self.google_model_choices()
        all_models = list(dict.fromkeys(choices['gemini'] + choices['claude'] +
            [family_models['gemini'], family_models['claude'], 'gemini-3-flash']))
        seen = {entry[0] for entry in models}
        route_targets = {entry[0]: target for entry, target in zip(models,
            [family_models['gemini'], family_models['claude'], 'gemini-3-flash'])}
        for model in all_models:
            route = self.claude_desktop_route(model)
            if route in seen:
                continue
            family = 'Gemini' if model.startswith('gemini-') else 'Claude'
            tier = 'opus' if 'opus' in model else 'haiku' if any(word in model for word in ('haiku', 'flash', 'lite')) else 'sonnet'
            models.append((route, family + ' · ' + model_name(model, {}), tier, False))
            seen.add(route)
            route_targets[route] = model
        if self.controller.key:
            self.configure_desktop_routes(all_models, defaults=True)
        self.write_json(preset, {
            'deploymentDisplayName': 'Gemini Accounts', 'inferenceCredentialKind': 'static',
            'modelDiscoveryEnabled': False, 'inferenceGatewayAuthScheme': 'bearer',
            'inferenceProvider': 'gateway', 'inferenceGatewayApiKey': key,
            'inferenceGatewayBaseUrl': 'http://127.0.0.1:8317',
            'claudeAiImport': {'bannerBehavior': 'detect', 'exportEnabled': True, 'enabled': True},
            'inferenceModels': [
                {'name': name, 'labelOverride': label, 'anthropicFamilyTier': tier, 'isFamilyDefault': default,
                 'supports1m': extended_context(route_targets[name]),
                 'prefer1m': extended_context(route_targets[name])}
                for name, label, tier, default in models] + self.api_model_entries(),
        })
        meta = self.read_json(meta_path)
        entries = meta.setdefault('entries', [])
        preset_id = preset.stem
        if not any(e.get('id') == preset_id for e in entries):
            entries.append({'id': preset_id, 'name': 'Gemini Accounts'})
        meta['appliedId'] = preset_id
        self.write_json(meta_path, meta)
        settings = self.read_json(desktop)
        settings['deploymentMode'] = '3p'
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
