import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from datetime import datetime, timezone, timedelta
from quota_limits import blocked_families, quota_floor, sync_quota_limits, clear_quota_limits, oauth_quota_groups, account_priority
from routing import rank_accounts, quota_entry
from chatgpt_auth import ChatGPTAuth
from claude_auth import ClaudeAuth
from backend import Controller, AccountError


class QuotaPolicyTests(unittest.TestCase):
    def setUp(self):
        self.prefs = {'quota-floors': {'one': {'gemini': {'5h': 20}, 'claude': {'weekly': 30}}}}

    def test_independent_windows_and_families(self):
        groups = [{'kind': 'gemini', 'buckets': [{'window': '5h', 'remaining': .2}]},
                  {'kind': 'claude', 'buckets': [{'window': 'weekly', 'remaining': .8}]}]
        self.assertEqual(blocked_families(self.prefs, 'one', groups), {'gemini'})
        groups[0]['buckets'][0]['remaining'] = .201
        self.assertEqual(blocked_families(self.prefs, 'one', groups), set())
        self.prefs['quota-floors']['one']['gemini']['5h'] = 0
        self.assertEqual(blocked_families(self.prefs, 'one', groups), set())
        self.assertEqual(quota_floor(self.prefs, 'other', 'gemini', '5h'), 0)

    def test_unknown_quota_is_held_only_when_configured(self):
        self.assertEqual(blocked_families(self.prefs, 'one', []), {'gemini', 'claude'})
        self.assertEqual(blocked_families(self.prefs, 'other', []), set())
        for value in (True, float('nan'), float('inf'), '80', -1, 2):
            self.assertIn('gemini', blocked_families(self.prefs, 'one', [{'kind': 'gemini', 'buckets': [{'window': '5h', 'remaining': value}]}]))
        self.prefs['quota-floors']['one']['gemini']['5h'] = 100
        self.assertIn('gemini', blocked_families(self.prefs, 'one', [{'kind': 'gemini', 'buckets': [{'window': '5h', 'remaining': 1}]}]))

    def test_preserves_user_exclusions_and_restores_only_owned_patterns(self):
        state = {'excluded_models': ['custom-model', 'claude*']}
        def request(path, method='GET', payload=None):
            if method == 'PATCH': state.update(payload)
            return dict(state)
        c = SimpleNamespace(preferences=self.prefs, request=Mock(side_effect=request))
        groups = [{'kind': 'gemini', 'buckets': [{'window': '5h', 'remaining': .2}]},
                  {'kind': 'claude', 'buckets': [{'window': 'weekly', 'remaining': .3}]}]
        sync_quota_limits(c, {'name': 'one'}, groups)
        self.assertEqual(state['excluded_models'], ['claude*', 'custom-model', 'gemini*', 'gpt-oss*'])
        self.assertEqual(state['gemini_accounts_quota_exclusions'], ['gemini*', 'gpt-oss*'])
        c.request.reset_mock(); sync_quota_limits(c, {'name': 'one'}, groups)
        self.assertEqual(c.request.call_count, 1)
        sync_quota_limits(c, {'name': 'one'}, [], clear=True)
        self.assertEqual(state['excluded_models'], ['claude*', 'custom-model'])
        self.assertEqual(state['gemini_accounts_quota_exclusions'], [])

    def test_unconfigured_accounts_do_not_read_credentials(self):
        c = SimpleNamespace(preferences={}, request=Mock())
        self.assertEqual(sync_quota_limits(c, {'name': 'one'}, []), set())
        clear_quota_limits(c)
        c.request.assert_not_called()

    def test_provider_failure_holds_configured_reserves_without_inventing_quota(self):
        c = SimpleNamespace(preferences=self.prefs, request=Mock(return_value={}),
                            _provider_quotas=Mock(side_effect=AccountError('Provider unavailable')))
        with self.assertRaisesRegex(AccountError, 'Provider unavailable'):
            Controller.quotas(c, {'name': 'one'})
        self.assertEqual(c.request.call_args.args[2]['excluded_models'], ['claude*', 'gemini*', 'gpt-oss*'])

    def test_google_priority_only_reorders_available_accounts(self):
        now = datetime.now(timezone.utc)
        accounts = [{'name': n} for n in ('a', 'b', 'empty', 'unknown')]
        caches = {n: {'at': now, 'data': {'groups': [{'kind': 'gemini', 'buckets': [
            {'window': '5h', 'remaining': 0 if n == 'empty' else .5, 'reset': (now + timedelta(hours=h)).isoformat()},
            {'window': 'weekly', 'remaining': .5, 'reset': (now + timedelta(days=3)).isoformat()}]}]}}
            for n, h in [('a', 1), ('b', 4), ('empty', .5)]}
        priorities = {'b': 5, 'empty': 999, 'unknown': 998}
        self.assertEqual([r['name'] for r in rank_accounts(accounts, caches, 'gemini', now, priorities=priorities)], ['b', 'a', 'unknown', 'empty'])
        self.assertEqual(rank_accounts(accounts, caches, 'gemini', now, priorities={'b': True})[0]['name'], 'a')
        reserve = {'quota-floors': {'b': {'gemini': {'5h': 60}}}}
        self.assertEqual(rank_accounts(accounts, caches, 'gemini', now, priorities=priorities, preferences=reserve)[0]['name'], 'a')

    def test_reserve_changes_usable_pool_and_reset_forecast(self):
        account = {'name': 'one'}
        five = {'window': '5h', 'remaining': .2, 'reset': '2030-01-01T05:00:00Z'}
        week = {'window': 'weekly', 'remaining': .8, 'reset': '2030-01-04T00:00:00Z'}
        entry = quota_entry(account, five, week, 'gemini', preferences=self.prefs)
        self.assertEqual(entry['remaining'], 0)
        self.assertEqual(entry['weekly_remaining'], .8)
        self.prefs['quota-floors']['one']['gemini']['weekly'] = 90
        self.assertEqual(quota_entry(account, five, week, 'gemini', preferences=self.prefs)['weekly_remaining'], 0)

    def test_subscription_reserves_keep_native_claude_models_separate(self):
        quota = {'windows': [{'label': '5h', 'remaining': 80}, {'label': 'Opus · 1w', 'remaining': 20},
                             {'label': 'Sonnet · 1w', 'remaining': 70}, {'label': 'OAuth · 1w', 'remaining': 80}]}
        groups = oauth_quota_groups(quota, 'claude')
        prefs = {'quota-floors': {'one': {'claude-opus': {'weekly': 20}}}}
        self.assertEqual(blocked_families(prefs, 'one', groups), {'claude-opus'})
        c = SimpleNamespace(preferences=prefs, request=Mock(return_value={}))
        sync_quota_limits(c, {'name': 'one'}, groups)
        self.assertEqual(c.request.call_args.args[2]['excluded_models'], ['claude-opus*'])

    def test_openai_timer_probe_respects_reserve(self):
        c = SimpleNamespace(preferences={'quota-floors': {'one': {'openai': {'weekly': 80}}}})
        self.assertIsNone(ChatGPTAuth(c).start_full_quota_window({'name': 'one'}, {'windows': [
            {'label': '5h', 'remaining': 100}, {'label': '1w', 'remaining': 80}]}))

    def test_native_subscription_priority_survives_refresh(self):
        for auth_type, provider in ((ChatGPTAuth, 'codex'), (ClaudeAuth, 'claude')):
            rows = [{'name': name, 'provider': provider, 'quota': {'windows': [
                {'label': '5h', 'remaining': 50, 'reset_at': 2000000000},
                {'label': '1w', 'remaining': 70, 'reset_at': 2100000000}]}} for name in ('one', 'two')]
            def request(path, method='GET', payload=None):
                if path == '/auth-files': return {'files': rows}
                if path == '/routing/strategy': return {'strategy': 'fill-first'}
                return {}
            c = SimpleNamespace(preferences={'account-priorities': {'two': 10}}, request=Mock(side_effect=request))
            auth_type(c).apply_reset_priority(rows)
            updates = [call.args[2] for call in c.request.call_args_list if len(call.args) > 2 and call.args[1] == 'PATCH']
            self.assertEqual(updates[0]['name'], 'two')
            self.assertEqual(updates[0]['priority'], 2)
            self.assertEqual(account_priority(c.preferences, 'two'), 10)
