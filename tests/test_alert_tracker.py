import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alert_tracker import AlertTracker, account_alert_conditions


class AlertTrackerTests(unittest.TestCase):
    def test_only_notifies_on_clear_to_active_transition(self):
        tracker = AlertTracker()
        key = 'quota:antigravity:account:gemini:5h'
        self.assertTrue(tracker.transition(key, True))
        self.assertFalse(tracker.transition(key, True))
        self.assertFalse(tracker.transition(key, False))
        self.assertTrue(tracker.transition(key, True))

    def test_clear_prefix_allows_reenabled_alerts_to_notify_again(self):
        tracker = AlertTracker()
        tracker.transition('auth:one', True)
        tracker.transition('quota:one', True)
        tracker.clear('auth:')
        self.assertTrue(tracker.transition('auth:one', True))
        self.assertFalse(tracker.transition('quota:one', True))

    def test_only_reauthentication_and_measured_reserve_crossing_trigger(self):
        preferences = {'quota-floors': {'one': {'gemini': {'5h': 20}}}}
        account = {'name': 'one', 'status': 'error',
                   'status_message': '{"error":{"code":429,"message":"rate limited"}}'}
        groups = [{'kind': 'gemini', 'buckets': [{'window': '5h', 'remaining': .19},
                                                 {'window': 'weekly', 'remaining': None}]}]
        auth_lost, reached = account_alert_conditions(account, groups, preferences)
        self.assertFalse(auth_lost)
        self.assertEqual(reached, [('gemini', '5h', 20)])
        account['access_issue'] = 'login'
        self.assertTrue(account_alert_conditions(account, groups, preferences)[0])

    def test_unknown_quota_never_triggers_reserve_notification(self):
        auth_lost, reached = account_alert_conditions({'name': 'one', 'status': 'active'},
            [{'kind': 'gemini', 'buckets': [{'window': '5h', 'remaining': None}]}],
            {'quota-floors': {'one': {'gemini': {'5h': 20}}}})
        self.assertFalse(auth_lost)
        self.assertEqual(reached, [])


if __name__ == '__main__':
    unittest.main()
