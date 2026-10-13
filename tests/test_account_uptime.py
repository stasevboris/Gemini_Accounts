import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from account_uptime import AccountUptime


class AccountUptimeTests(unittest.TestCase):
    def test_transient_failures_and_manual_pause_do_not_stop_credential_uptime(self):
        with tempfile.TemporaryDirectory() as directory:
            tracker = AccountUptime(Path(directory) / 'uptime.json')
            account = {'name': 'person@example.com', 'provider': 'antigravity',
                       'created_at': '1970-01-01T00:16:40Z', 'status': 'active'}
            tracker.update('antigravity', account, now=1000)
            tracker.update('antigravity', {**account, 'status': 'error',
                           'status_message': '{"error":{"code":503,"message":"timeout"}}'}, now=1600)
            tracker.update('antigravity', {**account, 'disabled': True}, now=1900)
            value = tracker.display('antigravity', account['name'], now=2800)
            self.assertEqual(value['text'], '0h 30m')
            self.assertTrue(value['running'])
            self.assertFalse(value['confirmed_auth_loss'])

    def test_only_confirmed_auth_loss_freezes_and_reauthentication_resumes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'uptime.json'
            tracker = AccountUptime(path)
            account = {'name': 'grok-account', 'created_at': '1970-01-01T00:16:40Z', 'status': 'active'}
            tracker.update('xai', account, now=1000)
            tracker.update('xai', {**account, 'access_issue': 'login', 'status': 'error'}, now=4600)
            frozen = tracker.display('xai', account['name'], now=8200)
            self.assertEqual(frozen['text'], '1h 00m')
            self.assertFalse(frozen['running'])
            self.assertTrue(frozen['confirmed_auth_loss'])
            restarted = AccountUptime(path)
            restarted.update('xai', {**account, 'status': 'active'}, now=10000)
            resumed = restarted.display('xai', account['name'], now=11800)
            self.assertEqual(resumed['text'], '1h 30m')
            self.assertTrue(resumed['running'])
            self.assertFalse(resumed['confirmed_auth_loss'])

    def test_unknown_initial_state_does_not_claim_confirmed_uptime(self):
        with tempfile.TemporaryDirectory() as directory:
            tracker = AccountUptime(Path(directory) / 'uptime.json')
            account = {'name': 'one', 'created_at': '1970-01-01T00:16:40Z', 'status': 'pending'}
            tracker.update('claude', account, now=1000)
            value = tracker.display('claude', 'one', now=2000)
            self.assertFalse(value['running'])
            self.assertEqual(value['text'], '0h 00m')
            self.assertFalse(value['confirmed_auth_loss'])

    def test_rate_limit_does_not_mark_auth_lost(self):
        with tempfile.TemporaryDirectory() as directory:
            tracker = AccountUptime(Path(directory) / 'uptime.json')
            account = {'name': 'one', 'status': 'active'}
            tracker.update('codex', account, now=100)
            tracker.update('codex', {**account, 'cooldowns': [{'http_status': 429,
                           'remaining_seconds': 60}]}, now=200)
            value = tracker.display('codex', 'one', now=300)
            self.assertTrue(value['running'])
            self.assertFalse(value['confirmed_auth_loss'])


if __name__ == '__main__':
    unittest.main()
