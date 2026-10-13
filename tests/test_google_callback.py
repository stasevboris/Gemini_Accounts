import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import AccountError, Controller


class GoogleCallbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.controller = Controller(data_dir=self.temp.name)
        self.controller.base = 'http://127.0.0.1:8318'

    def tearDown(self):
        self.temp.cleanup()

    def test_begin_login_returns_exact_callback_uri_and_preserves_cli_shape(self):
        auth_url = ('https://accounts.google.com/o/oauth2/auth?state=state-1&redirect_uri='
                    'http%3A%2F%2Flocalhost%3A51121%2Foauth-callback')
        self.controller.accounts = lambda: []
        self.controller.request = lambda *args: {'url': auth_url, 'state': 'state-1'}
        url, state, redirect = self.controller.begin_login_details()
        self.assertEqual(state, 'state-1')
        self.assertEqual(redirect, 'http://localhost:51121/oauth-callback')
        self.assertEqual(parse_qs(urlsplit(url).query)['prompt'], ['select_account consent'])
        self.assertEqual(self.controller.begin_login(), (url, state))

    def test_begin_login_rejects_state_or_redirect_mismatch(self):
        self.controller.accounts = lambda: []
        self.controller.request = lambda *args: {'url': 'https://accounts.google.com/o/oauth2/auth?state=other&redirect_uri=http%3A%2F%2Flocalhost%3A1234%2Foauth-callback',
                                                'state': 'expected'}
        with self.assertRaises(AccountError):
            self.controller.begin_login_details()
        self.controller.request = lambda *args: {'url': 'https://accounts.google.com/o/oauth2/auth?state=s&redirect_uri=http%3A%2F%2Fevil.example%2Foauth-callback',
                                                'state': 's'}
        with self.assertRaises(AccountError):
            self.controller.begin_login_details()

    def test_valid_blocked_url_is_forwarded_only_to_loopback_callback(self):
        connection = Mock()
        response = Mock(status=302)
        response.read.return_value = b''
        connection.getresponse.return_value = response
        redirect = 'http://localhost:51121/oauth-callback'
        pasted = 'Blocked URL: ' + redirect + '?code=short-code&state=right-state'
        with patch('backend.http.client.HTTPConnection', return_value=connection) as factory:
            result = self.controller.submit_google_callback(pasted, redirect, 'right-state')
        self.assertEqual(result['status'], 'forwarded')
        factory.assert_called_once_with('127.0.0.1', 8318, timeout=8)
        args, kwargs = connection.request.call_args
        method, path = args
        self.assertEqual(method, 'GET')
        self.assertEqual(urlsplit(path).path, '/antigravity/callback')
        self.assertEqual(parse_qs(urlsplit(path).query), {'state': ['right-state'], 'code': ['short-code']})
        self.assertEqual(kwargs['headers']['Cache-Control'], 'no-store')
        connection.close.assert_called_once()

    def test_untrusted_hosts_paths_duplicate_parameters_and_wrong_state_are_rejected(self):
        redirect = 'http://localhost:51121/oauth-callback'
        invalid_urls = [
            'http://evil.example:51121/oauth-callback?code=x&state=s',
            'http://localhost:51121/other?code=x&state=s',
            'http://localhost:51122/oauth-callback?code=x&state=s',
            'http://localhost:51121/oauth-callback?code=x&code=y&state=s',
            'http://localhost:51121/oauth-callback?code=x&state=wrong',
            'http://localhost:51121/oauth-callback?code=x&state=%D1%87%D1%83%D0%B6%D0%BE%D0%B9',
        ]
        with patch('backend.http.client.HTTPConnection') as connection:
            for value in invalid_urls:
                with self.subTest(value=value), self.assertRaises(AccountError):
                    self.controller.submit_google_callback(value, redirect, 's')
        connection.assert_not_called()

    def test_callback_error_and_failed_local_forward_do_not_expose_code(self):
        redirect = 'http://localhost:51121/oauth-callback'
        with self.assertRaises(AccountError) as error:
            self.controller.submit_google_callback(redirect + '?error=access_denied&state=s', redirect, 's')
        self.assertNotIn('access_denied', str(error.exception))
        connection = Mock()
        connection.getresponse.return_value = Mock(status=500, read=Mock(return_value=b''))
        with patch('backend.http.client.HTTPConnection', return_value=connection):
            with self.assertRaises(AccountError) as error:
                self.controller.submit_google_callback(redirect + '?code=private-code&state=s', redirect, 's')
        self.assertNotIn('private-code', str(error.exception))


if __name__ == '__main__':
    unittest.main()
