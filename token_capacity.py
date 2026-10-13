"""Empirical token-capacity estimates from usage and observed quota changes."""
import hashlib
import json
import math
import statistics
import threading
from datetime import datetime

from backend import atomic_write


class TokenCapacity:
    """Store aggregate measurements only; prompts and OAuth credentials are never read."""

    MIN_SAMPLES = 3
    MIN_QUOTA_DROP = 0.02
    MAX_SAMPLES = 40
    MAX_SEEN = 12000

    def __init__(self, path):
        self.path = path
        self._lock = threading.RLock()
        try:
            value = json.loads(path.read_text('utf-8'))
        except (OSError, ValueError, TypeError):
            value = {}
        self.state = value if isinstance(value, dict) else {}
        self.state.setdefault('schema_version', 1)
        self.state.setdefault('seen', [])
        self.state.setdefault('usage', {})
        self.state.setdefault('baselines', {})
        self.state.setdefault('estimates', {})
        if not isinstance(self.state['seen'], list):
            self.state['seen'] = []
        for key in ('usage', 'baselines', 'estimates'):
            if not isinstance(self.state[key], dict):
                self.state[key] = {}

    @staticmethod
    def account_key(provider, name):
        raw = (str(provider) + '\0' + str(name)).encode('utf-8', 'replace')
        return hashlib.sha256(raw).hexdigest()[:24]

    @staticmethod
    def _provider(account):
        value = account.get('provider', account.get('type', ''))
        return str(value or '').lower()

    @staticmethod
    def _window(value):
        value = str(value or '').lower()
        if value in ('1w', 'weekly', 'week', '7d', 'oauth · 1w'):
            return 'weekly'
        if value in ('5h', 'primary_window'):
            return '5h'
        return None

    @classmethod
    def oauth_groups(cls, provider, quota):
        groups = {}
        provider = str(provider or '').lower()
        for window in (quota or {}).get('windows', []):
            raw_label = str(window.get('label') or '')
            label = ('weekly' if raw_label.startswith(('Opus · ', 'Sonnet · ')) else cls._window(raw_label))
            family = 'openai' if provider == 'codex' else 'claude'
            if provider == 'claude' and raw_label.startswith('Opus · '):
                family = 'claude-opus'
            elif provider == 'claude' and raw_label.startswith('Sonnet · '):
                family = 'claude-sonnet'
            elif raw_label == 'OAuth · 1w':
                # This quota is distinct from the regular account-wide week.
                continue
            percent = window.get('remaining')
            remaining = (float(percent) / 100 if isinstance(percent, (int, float)) and
                         not isinstance(percent, bool) and math.isfinite(percent) and 0 <= percent <= 100 else None)
            if label and remaining is not None:
                groups.setdefault(family, []).append({'window': label, 'remaining': remaining,
                    'reset': window.get('reset_at', window.get('reset'))})
        return [{'kind': kind, 'buckets': buckets} for kind, buckets in groups.items()]

    @staticmethod
    def _remaining(value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return None
        if 1 < value <= 100:
            value /= 100
        return max(0.0, min(1.0, float(value))) if 0 <= value <= 1 else None

    @staticmethod
    def _reset(value):
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            return float(value)
        if isinstance(value, str) and value:
            try:
                return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
            except (ValueError, TypeError, OverflowError, OSError):
                return None
        return None

    @staticmethod
    def _model_family(provider, group, model):
        provider, group, model = str(provider).lower(), str(group).lower(), str(model).lower()
        if provider == 'antigravity':
            if group == 'gemini':
                return model.startswith('gemini-') or model == 'claude-sonnet-4-5'
            if group == 'claude':
                return model.startswith(('claude-', 'gpt-', 'o1', 'o3', 'o4'))
            return False
        if provider == 'codex':
            return group == 'openai'
        if provider == 'claude':
            if group == 'claude-opus':
                return model.startswith('claude-opus-')
            if group == 'claude-sonnet':
                return model.startswith('claude-sonnet-')
            return group == 'claude' and model.startswith('claude-')
        return False

    def observe_usage(self, records, accounts, bootstrap=False):
        """Add completed request token counts, deduplicated by execution/request ID."""
        mapping = {}
        for account in accounts or []:
            if not isinstance(account, dict):
                continue
            auth_index = account.get('auth_index')
            name = account.get('name')
            provider = self._provider(account)
            if auth_index and name and provider in ('antigravity', 'codex', 'claude'):
                mapping[str(auth_index)] = (provider, self.account_key(provider, name))
        changed = False
        with self._lock:
            seen = set(self.state['seen'])
            for record in records or []:
                if not isinstance(record, dict):
                    continue
                auth = mapping.get(str(record.get('auth_index') or ''))
                identifier = record.get('execution_id') or record.get('request_id')
                if auth is None or not identifier:
                    continue
                event_key = hashlib.sha256((auth[1] + '\0' + str(identifier)).encode('utf-8', 'replace')).hexdigest()
                if event_key in seen:
                    continue
                seen.add(event_key)
                self.state['seen'].append(event_key)
                token_data = record.get('tokens')
                tokens = token_data.get('total_tokens', 0) if isinstance(token_data, dict) else 0
                if isinstance(tokens, bool) or not isinstance(tokens, (int, float)) or not math.isfinite(tokens) or tokens < 0:
                    changed = True
                    continue
                model = str(record.get('upstream_model') or record.get('model') or record.get('alias') or '').strip()[:200]
                if not model or tokens <= 0:
                    changed = True
                    continue
                provider, identity = auth
                usage = self.state['usage'].get(identity)
                if not isinstance(usage, dict):
                    usage = {'provider': provider, 'models': {}}
                    self.state['usage'][identity] = usage
                if not isinstance(usage.get('models'), dict):
                    usage['models'] = {}
                usage['models'][model] = float(usage['models'].get(model, 0)) + float(tokens)
                changed = True
            if len(self.state['seen']) > self.MAX_SEEN:
                self.state['seen'] = self.state['seen'][-self.MAX_SEEN:]
                changed = True
            if bootstrap and self.state['baselines']:
                # The first snapshot includes requests from before this app
                # session. Pair future quota changes with future usage only.
                self.state['baselines'].clear()
                changed = True
            if changed:
                self._save_locked()
        return changed

    def observe_quota(self, provider, name, plan, groups, now=None):
        """Create a sample only when one model explains a measurable quota drop."""
        provider = str(provider or '').lower()
        if provider not in ('antigravity', 'codex', 'claude') or not name:
            return False
        identity = self.account_key(provider, name)
        plan = str(plan or 'Unknown plan').strip()[:80] or 'Unknown plan'
        now = datetime.now().timestamp() if now is None else float(now)
        changed = False
        with self._lock:
            usage_entry = self.state['usage'].get(identity, {})
            usage = usage_entry.get('models', {}) if isinstance(usage_entry, dict) else {}
            if not isinstance(usage, dict):
                usage = {}
            for group in groups or []:
                if not isinstance(group, dict):
                    continue
                family = str(group.get('kind') or provider).lower()[:60]
                models = {model: float(total) for model, total in usage.items()
                          if self._model_family(provider, family, model)}
                for bucket in group.get('buckets', []):
                    if not isinstance(bucket, dict):
                        continue
                    window = self._window(bucket.get('window'))
                    remaining = self._remaining(bucket.get('remaining'))
                    if window is None or remaining is None:
                        continue
                    reset = self._reset(bucket.get('reset', bucket.get('reset_at')))
                    baseline_id = json.dumps([identity, provider, plan, family, window], ensure_ascii=False)
                    current = {'remaining': remaining, 'reset': reset, 'tokens': models, 'at': now}
                    old = self.state['baselines'].get(baseline_id)
                    if not isinstance(old, dict):
                        old = None
                    if not old:
                        self.state['baselines'][baseline_id] = current
                        changed = True
                        continue
                    old_reset = self._reset(old.get('reset'))
                    if old_reset is None or reset is None:
                        # Without both reset anchors a refill may have occurred
                        # between observations, so do not infer a capacity sample.
                        self.state['baselines'][baseline_id] = current
                        changed = True
                        continue
                    reset_changed = abs(old_reset - reset) > 5
                    quota_refilled = remaining > float(old.get('remaining', remaining)) + 1e-6
                    old_at = float(old.get('at', now))
                    stale_gap = now - old_at > (10 * 3600 if window == '5h' else 15 * 86400)
                    if reset_changed or quota_refilled or stale_gap:
                        self.state['baselines'][baseline_id] = current
                        changed = True
                        continue
                    previous_tokens = old.get('tokens') or {}
                    if not isinstance(previous_tokens, dict):
                        previous_tokens = {}
                    deltas = {model: total - float(previous_tokens.get(model, 0))
                              for model, total in models.items()}
                    if any(delta < -1e-6 for delta in deltas.values()):
                        self.state['baselines'][baseline_id] = current
                        changed = True
                        continue
                    quota_drop = float(old.get('remaining', remaining)) - remaining
                    if quota_drop < self.MIN_QUOTA_DROP:
                        # Keep the older baseline so small rounded changes can accumulate.
                        continue
                    used_models = {model: delta for model, delta in deltas.items() if delta > 0}
                    self.state['baselines'][baseline_id] = current
                    changed = True
                    if len(used_models) != 1:
                        continue
                    model, tokens = next(iter(used_models.items()))
                    capacity = tokens / quota_drop
                    if not math.isfinite(capacity) or capacity <= 0:
                        continue
                    estimate_id = json.dumps([provider, plan, family, model, window], ensure_ascii=False)
                    estimate = self.state['estimates'].get(estimate_id)
                    if not isinstance(estimate, dict):
                        estimate = {'provider': provider, 'plan': plan, 'family': family,
                                    'model': model, 'window': window, 'samples': []}
                        self.state['estimates'][estimate_id] = estimate
                    samples = estimate.setdefault('samples', [])
                    if not isinstance(samples, list):
                        samples = []
                    samples.append({'capacity': capacity, 'tokens': tokens, 'quota_drop': quota_drop,
                                    'account_key': identity, 'seconds': max(0.0, now - old_at), 'at': now})
                    estimate['samples'] = samples[-self.MAX_SAMPLES:]
            if changed:
                self._save_locked()
        return changed

    def forecasts(self, provider, name, plan, groups, floors=None, now=None):
        """Return per-account ETA rows only when this account has 3 clean rate samples."""
        provider = str(provider or '').lower()
        if provider not in ('antigravity', 'codex', 'claude') or not name:
            return []
        identity = self.account_key(provider, name)
        plan = str(plan or 'Unknown plan').strip()[:80] or 'Unknown plan'
        floors = floors if isinstance(floors, dict) else {}
        now = datetime.now().timestamp() if now is None else float(now)
        rows = []
        with self._lock:
            estimates = list(self.state['estimates'].values())
            for group in groups or []:
                if not isinstance(group, dict):
                    continue
                family = str(group.get('kind') or provider).lower()[:60]
                family_floors = floors.get(family, {})
                if not isinstance(family_floors, dict):
                    family_floors = {}
                for bucket in group.get('buckets', []):
                    if not isinstance(bucket, dict):
                        continue
                    window = self._window(bucket.get('window'))
                    remaining = self._remaining(bucket.get('remaining'))
                    if window is None or remaining is None:
                        continue
                    floor = self._remaining(family_floors.get(bucket.get('window'), 0))
                    if floor is None:
                        floor = 0.0
                    reserve_reached = remaining <= floor + 1e-7
                    reset_at = self._reset(bucket.get('reset', bucket.get('reset_at')))
                    matches = [estimate for estimate in estimates if isinstance(estimate, dict)
                               and estimate.get('provider') == provider and estimate.get('plan') == plan
                               and estimate.get('family') == family and estimate.get('window') == window]
                    if reserve_reached and not matches:
                        rows.append({'provider': provider, 'name': name, 'plan': plan,
                            'family': family, 'model': 'Unknown model', 'window': window,
                            'remaining': remaining, 'reserve': floor, 'eta_seconds': 0.0,
                            'reset_at': reset_at, 'samples_count': 0,
                            'rate_fraction_per_hour': 0.0, 'reserve_reached': True})
                    for estimate in matches:
                        samples = [sample for sample in (estimate.get('samples') or [])
                                   if isinstance(sample, dict) and sample.get('account_key') == identity
                                   and isinstance(sample.get('seconds'), (int, float))
                                   and math.isfinite(sample['seconds']) and sample['seconds'] > 0
                                   and isinstance(sample.get('quota_drop'), (int, float))
                                   and math.isfinite(sample['quota_drop']) and sample['quota_drop'] > 0
                                   and isinstance(sample.get('at'), (int, float))
                                   and math.isfinite(sample['at'])
                                   and 0 <= now - sample['at'] <= (10 * 3600 if window == '5h' else 15 * 86400)]
                        drops = sum(float(sample['quota_drop']) for sample in samples)
                        if not reserve_reached and (len(samples) < self.MIN_SAMPLES or drops < self.MIN_QUOTA_DROP):
                            continue
                        rates = [float(sample['quota_drop']) / float(sample['seconds']) for sample in samples]
                        rate = statistics.median(rates) if rates else 0.0
                        eta = 0.0 if reserve_reached else (remaining - floor) / rate if rate > 0 else None
                        if eta is None or not math.isfinite(eta):
                            continue
                        rows.append({'provider': provider, 'name': name, 'plan': plan,
                            'family': family, 'model': estimate.get('model', 'Unknown model'),
                            'window': window, 'remaining': remaining, 'reserve': floor,
                            'eta_seconds': eta, 'reset_at': reset_at,
                            'samples_count': len(samples), 'rate_fraction_per_hour': rate * 3600,
                            'reserve_reached': reserve_reached})
        return sorted(rows, key=lambda row: (row['eta_seconds'], row['window'], row['model']))

    def rows(self):
        with self._lock:
            rows = []
            for estimate in self.state['estimates'].values():
                if not isinstance(estimate, dict):
                    continue
                samples = estimate.get('samples') or []
                if not isinstance(samples, list):
                    continue
                samples = [sample for sample in samples if isinstance(sample, dict)]
                if not samples:
                    continue
                used = sum(float(sample.get('quota_drop', 0)) for sample in samples
                           if isinstance(sample.get('quota_drop', 0), (int, float)) and
                           math.isfinite(sample.get('quota_drop', 0)))
                capacities = [float(sample['capacity']) for sample in samples
                              if isinstance(sample.get('capacity'), (int, float)) and math.isfinite(sample['capacity'])]
                if not capacities:
                    continue
                rows.append({**estimate, 'capacity': int(round(statistics.median(capacities))),
                             'samples_count': len(capacities), 'observed_fraction': used,
                             'min_capacity': int(round(min(capacities))),
                             'max_capacity': int(round(max(capacities))),
                             'ready': len(capacities) >= self.MIN_SAMPLES and used >= self.MIN_QUOTA_DROP})
            return sorted(rows, key=lambda row: (row['provider'], row['plan'], row['model'], row['window']))

    def _save_locked(self):
        atomic_write(self.path, json.dumps(self.state, ensure_ascii=False).encode('utf-8'))
