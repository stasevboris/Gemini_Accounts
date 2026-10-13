import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from token_capacity import TokenCapacity


class TokenCapacityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'token-capacity.json'
        self.tracker = TokenCapacity(self.path)
        self.accounts = [{'name': 'private@example.com', 'auth_index': 'idx-1', 'provider': 'antigravity'}]
        self.groups = [{'kind': 'gemini', 'buckets': [
            {'window': '5h', 'remaining': 1.0, 'reset': '2026-10-12T18:00:00Z'}]}]

    def tearDown(self):
        self.temp.cleanup()

    def usage(self, identifier, tokens=1000, model='gemini-3.1-pro'):
        return {'execution_id': identifier, 'auth_index': 'idx-1', 'upstream_model': model,
                'tokens': {'total_tokens': tokens}}

    def test_estimate_requires_three_single_model_samples_and_persists_without_names(self):
        self.tracker.observe_quota('antigravity', 'private@example.com', 'AI Pro', self.groups, now=1000)
        for index, remaining in enumerate((.98, .96, .94), start=1):
            self.tracker.observe_usage([self.usage('request-' + str(index))], self.accounts)
            self.tracker.observe_quota('antigravity', 'private@example.com', 'AI Pro',
                [{'kind': 'gemini', 'buckets': [{'window': '5h', 'remaining': remaining,
                    'reset': '2026-10-12T18:00:00Z'}]}], now=1000 + index * 60)
        rows = self.tracker.rows()
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]['ready'])
        self.assertEqual(rows[0]['samples_count'], 3)
        self.assertEqual(rows[0]['capacity'], 50000)
        self.assertEqual(rows[0]['window'], '5h')
        self.assertNotIn('private@example.com', self.path.read_text('utf-8'))
        restarted = TokenCapacity(self.path)
        self.assertEqual(restarted.rows(), rows)

    def test_mixed_models_and_quota_reset_do_not_create_false_samples(self):
        self.tracker.observe_quota('antigravity', 'private@example.com', 'AI Pro', self.groups, now=1000)
        self.tracker.observe_usage([self.usage('one', model='gemini-3.1-pro'),
                                    self.usage('two', model='gemini-3-flash')], self.accounts)
        self.tracker.observe_quota('antigravity', 'private@example.com', 'AI Pro',
            [{'kind': 'gemini', 'buckets': [{'window': '5h', 'remaining': .96,
                'reset': '2026-10-12T18:00:00Z'}]}], now=1060)
        self.assertEqual(self.tracker.rows(), [])
        # A new reset anchor rebases the baseline instead of treating refill as usage.
        self.tracker.observe_usage([self.usage('three')], self.accounts)
        self.tracker.observe_quota('antigravity', 'private@example.com', 'AI Pro',
            [{'kind': 'gemini', 'buckets': [{'window': '5h', 'remaining': 1.0,
                'reset': '2026-10-12T23:00:00Z'}]}], now=1120)
        self.assertEqual(self.tracker.rows(), [])

    def test_unavailable_quota_is_not_interpreted_as_zero(self):
        self.tracker.observe_quota('antigravity', 'private@example.com', 'AI Pro',
            [{'kind': 'gemini', 'buckets': [{'window': '5h', 'remaining': None}]}], now=1000)
        self.tracker.observe_usage([self.usage('one')], self.accounts)
        self.assertEqual(self.tracker.rows(), [])

    def test_startup_backfill_is_not_charged_to_a_new_quota_interval(self):
        self.tracker.observe_quota('antigravity', 'private@example.com', 'AI Pro', self.groups, now=1000)
        self.tracker.observe_usage([self.usage('historical', tokens=1000000)], self.accounts, bootstrap=True)
        self.tracker.observe_quota('antigravity', 'private@example.com', 'AI Pro', self.groups, now=1060)
        for index, remaining in enumerate((.98, .96, .94), start=1):
            self.tracker.observe_usage([self.usage('new-' + str(index))], self.accounts)
            self.tracker.observe_quota('antigravity', 'private@example.com', 'AI Pro',
                [{'kind': 'gemini', 'buckets': [{'window': '5h', 'remaining': remaining,
                    'reset': '2026-10-12T18:00:00Z'}]}], now=1060 + index * 60)
        self.assertEqual(self.tracker.rows()[0]['capacity'], 50000)
        self.assertEqual(self.tracker.rows()[0]['samples_count'], 3)

    def test_forecast_ignores_invalid_or_future_measurement_times(self):
        identity = self.tracker.account_key('antigravity', 'private@example.com')
        self.tracker.state['estimates']['test'] = {'provider': 'antigravity', 'plan': 'AI Pro',
            'family': 'gemini', 'model': 'gemini-3.1-pro', 'window': '5h',
            'samples': [{'account_key': identity, 'seconds': 60, 'quota_drop': .02, 'at': at}
                        for at in ('bad', None, float('nan'), 2000)]}
        self.assertEqual(self.tracker.forecasts('antigravity', 'private@example.com', 'AI Pro',
            self.groups, now=1000), [])

    def test_forecast_uses_recent_quota_drop_rate_and_account_reserve(self):
        self.tracker.observe_quota('antigravity', 'private@example.com', 'AI Pro',
            [{'kind': 'gemini', 'buckets': [{'window': '5h', 'remaining': 1.0, 'reset': 36000}]}], now=1000)
        for index, remaining in enumerate((.98, .96, .94), start=1):
            self.tracker.observe_usage([self.usage('forecast-' + str(index))], self.accounts)
            self.tracker.observe_quota('antigravity', 'private@example.com', 'AI Pro',
                [{'kind': 'gemini', 'buckets': [{'window': '5h', 'remaining': remaining,
                    'reset': 36000}]}], now=1000 + index * 3600)
        forecast = self.tracker.forecasts('antigravity', 'private@example.com', 'AI Pro',
            [{'kind': 'gemini', 'buckets': [{'window': '5h', 'remaining': .94, 'reset': 36000}]}],
            floors={'gemini': {'5h': .2}}, now=11800)
        self.assertEqual(len(forecast), 1)
        self.assertEqual(forecast[0]['samples_count'], 3)
        self.assertAlmostEqual(forecast[0]['eta_seconds'], .74 / (.02 / 3600))
        self.assertFalse(forecast[0]['reserve_reached'])
        self.assertEqual(forecast[0]['reset_at'], 36000)

    def test_reserve_reached_forecast_is_immediate_without_rate_samples(self):
        forecast = self.tracker.forecasts('antigravity', 'private@example.com', 'AI Pro',
            [{'kind': 'gemini', 'buckets': [{'window': '5h', 'remaining': .1, 'reset': 36000}]}],
            floors={'gemini': {'5h': .1}}, now=1000)
        self.assertEqual(len(forecast), 1)
        self.assertEqual(forecast[0]['eta_seconds'], 0)
        self.assertTrue(forecast[0]['reserve_reached'])

    def test_native_provider_windows_are_normalized_from_percentages(self):
        groups = TokenCapacity.oauth_groups('codex', {'windows': [
            {'label': '5h', 'remaining': 1, 'reset_at': 10000}]})
        self.assertEqual(groups[0]['buckets'][0]['remaining'], .01)
        self.tracker.observe_quota('codex', 'chatgpt-account', 'Plus',
            TokenCapacity.oauth_groups('codex', {'windows': [
                {'label': '5h', 'remaining': 100, 'reset_at': 10000}]}), now=1000)
        self.tracker.observe_usage([{'execution_id': 'codex-1', 'auth_index': 'codex-idx',
            'upstream_model': 'gpt-test', 'tokens': {'total_tokens': 2000}}],
            [{'name': 'chatgpt-account', 'auth_index': 'codex-idx', 'provider': 'codex'}])
        rows = self.tracker.rows()
        self.assertEqual(rows, [])  # One observation is only a baseline, not an estimate.


if __name__ == '__main__':
    unittest.main()
