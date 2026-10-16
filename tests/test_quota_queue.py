import http.client
import json
import sys
import threading
import time
import unittest
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from quota_queue import QueueServer, quota_wait, PING


def account(model='gemini', seconds=20, code=429):
    return {'provider': 'antigravity', 'name': 'a', 'cooldowns': [{
        'scope': 'model', 'model_key': model, 'reason': 'quota' if code == 429 else 'error',
        'http_status': code, 'retry_at': (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()}]}


class Mock(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        value = {'files': self.server.files}
        if self.path == '/v1/models':
            value = {'data': [{'id': model} for model in getattr(self.server, 'catalog', [])]}
        if self.path == '/v0/management/oauth-model-alias' and hasattr(self.server, 'model_aliases'):
            value = {'oauth-model-alias': {'antigravity': self.server.model_aliases}}
        data = json.dumps(value).encode()
        self.send_response(200); self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_POST(self):
        self.server.last_request = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
        self.server.calls += 1
        time.sleep(getattr(self.server, 'header_delay', 0))
        data = (b'event: message_start\ndata: {"type":"message_start","message":{"id":"real"}}\n\n'
                b'event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"type":"text_delta","text":"OK"}}\n\n'
                b'event: message_stop\ndata: {"type":"message_stop"}\n\n') if self.server.status == 200 else b'{"error":{"type":"authentication_error","message":"Denied"}}'
        if getattr(self.server, 'json_nonstream', False) and not self.server.last_request.get('stream'):
            data = b'{"type":"message","content":[{"type":"text","text":"OK"}],"stop_reason":"end_turn"}'
        if (any(t.get('type', '').startswith('web_search_') for t in self.server.last_request.get('tools', []))
                and self.server.last_request.get('model') not in getattr(self.server, 'search_without_results', set())):
            use = {'type': 'server_tool_use', 'id': 'search1', 'name': 'web_search', 'input': {'query': 'Docs'}}
            result = {'type': 'web_search_tool_result', 'tool_use_id': 'search1',
                      'content': [{'type': 'web_search_result', 'url': 'https://docs.python.org/', 'title': 'Docs'}]}
            if self.server.last_request.get('stream'):
                data = (b'event: message_start\ndata: {"type":"message_start","message":{"id":"search"}}\n\n'
                        + b'data: ' + json.dumps({'type': 'content_block_start', 'index': 0, 'content_block': use}).encode() + b'\n\n'
                        + b'data: ' + json.dumps({'type': 'content_block_start', 'index': 1, 'content_block': result}).encode() + b'\n\n'
                        + b'data: {"type":"message_stop"}\n\n')
            else:
                data = json.dumps({'type': 'message', 'content': [use, result], 'stop_reason': 'end_turn'}).encode()
        if self.path == '/v1/responses' and self.server.status == 200:
            data = b'event: response.completed\ndata: {"type":"response.completed","response":{"status":"completed"}}\n\n'
        if self.server.calls <= getattr(self.server, 'empty_attempts', 0):
            data = (b'event: message_start\ndata: {"type":"message_start","message":{"id":"empty"}}\n\n'
                    b'event: message_stop\ndata: {"type":"message_stop"}\n\n')
        if getattr(self.server, 'tool_response', False):
            data = (b'event: message_start\ndata: {"type":"message_start","message":{"id":"tool"}}\n\n'
                    b'event: content_block_start\ndata: {"type":"content_block_start","index":0,"content_block":{"type":"tool_use","name":"Bash","id":"real-tool","input":{}}}\n\n'
                    b'event: message_stop\ndata: {"type":"message_stop"}\n\n')
        self.send_response(self.server.status); self.send_header('Content-Type', 'text/event-stream'); self.send_header('Content-Length', str(len(data))); self.end_headers()
        time.sleep(getattr(self.server, 'body_delay', 0))
        self.wfile.write(data)


class QueueTests(unittest.TestCase):
    def test_update_is_blocked_while_a_team_is_between_provider_requests(self):
        from unittest.mock import patch
        with patch('quota_queue.team_active', return_value=True):
            self.client.request('POST', '/v0/management/update-lock', b'', {'Authorization': 'Bearer admin'})
            response = self.client.getresponse()
            self.assertEqual(response.status, 409)
            response.read()
            self.assertFalse(self.gate.updating)

    def test_grok_client_alias_keeps_history_tools_and_xai_quota_scope(self):
        from grok_auth import desktop_model_id
        route = desktop_model_id('grok-4.7')
        self.backend.model_aliases = []
        original_get = Mock.do_GET
        def get(handler):
            if handler.path == '/v0/management/oauth-model-alias':
                data = json.dumps({'oauth-model-alias': {'xai': [{'alias': route, 'name': 'grok-4.7'}]}}).encode()
                handler.send_response(200)
                handler.send_header('Content-Length', str(len(data)))
                handler.end_headers()
                handler.wfile.write(data)
            else:
                original_get(handler)
        from unittest.mock import patch
        google = account('grok-4.7', seconds=200)
        google['cooldowns'][0]['scope'] = 'credential'
        self.backend.files = [google, {'provider': 'xai', 'name': 'grok'}]
        payload = {'model': route, 'stream': True, 'max_tokens': 32,
                   'messages': [{'role': 'user', 'content': 'Remember blue'},
                                {'role': 'assistant', 'content': 'OK'},
                                {'role': 'user', 'content': 'Which color?'}],
                   'tools': [{'name': 'calculator', 'input_schema': {'type': 'object'}}]}
        with patch.object(Mock, 'do_GET', get):
            self.client.request('POST', '/v1/messages', json.dumps(payload), {'Authorization': 'Bearer client'})
            response = self.client.getresponse()
            self.assertEqual(response.status, 200)
            self.assertIn(b'OK', response.read())
            self.assertEqual(self.backend.last_request, payload)
            self.assertEqual(self.gate.aliases[route], 'grok-4.7')

    def test_grok_quota_wait_is_scoped_to_xai_accounts(self):
        google = account('grok-4', seconds=200)
        google['cooldowns'][0]['scope'] = 'credential'
        xai = {'provider': 'xai', 'name': 'grok', 'status': 'active'}
        self.assertIsNone(quota_wait([google, xai], 'grok-4', {}))
        limited = {**account('grok-4', seconds=200), 'provider': 'xai'}
        self.assertIsNotNone(quota_wait([{'provider': 'antigravity', 'name': 'google'}, limited], 'grok-4', {}))

    def test_grok_request_keeps_history_and_tools_despite_google_quota(self):
        google = account('grok-4', seconds=200)
        google['cooldowns'][0]['scope'] = 'credential'
        self.backend.files = [google, {'provider': 'xai', 'name': 'grok', 'status': 'active'}]
        payload = {'model': 'grok-4', 'stream': True, 'max_tokens': 32,
                   'messages': [{'role': 'user', 'content': 'Remember blue'},
                                {'role': 'assistant', 'content': 'OK'},
                                {'role': 'user', 'content': 'Which color?'}],
                   'tools': [{'name': 'calculator', 'input_schema': {'type': 'object'}}]}
        self.client.request('POST', '/v1/messages', json.dumps(payload), {'Authorization': 'Bearer client'})
        response = self.client.getresponse()
        self.assertEqual(response.status, 200)
        self.assertIn(b'OK', response.read())
        self.assertEqual(self.backend.last_request['model'], 'grok-4')
        self.assertEqual(self.backend.last_request['messages'], payload['messages'])
        self.assertEqual(self.backend.last_request['tools'], payload['tools'])

    def setUp(self):
        self.backend = ThreadingHTTPServer(('127.0.0.1', 0), Mock)
        self.backend.files = [account()]; self.backend.calls = 0; self.backend.status = 200
        threading.Thread(target=self.backend.serve_forever, daemon=True).start()
        self.gate = QueueServer(('127.0.0.1', 0), self.backend.server_address, 'admin', ['client'], {'alias': 'gemini'})
        self.gate.poll_seconds = .05
        threading.Thread(target=self.gate.serve_forever, daemon=True).start()
        self.client = http.client.HTTPConnection(*self.gate.server_address, timeout=3)
    def tearDown(self):
        self.client.close(); self.gate.shutdown(); self.gate.server_close(); self.backend.shutdown(); self.backend.server_close()
    def post(self, key='client', model='alias'):
        self.client.request('POST', '/v1/messages', json.dumps({'model': model, 'stream': True, 'messages': []}), {'x-api-key': key})
        return self.client.getresponse()

    def search_payload(self, model):
        return {'model': model, 'stream': False, 'max_tokens': 1024,
                'system': [{'type': 'text', 'text': 'You are an assistant for performing a web search tool use'}],
                'messages': [{'role': 'user', 'content': 'Perform a web search for the query: Python documentation'}],
                'tools': [{'type': 'web_search_20250305', 'name': 'web_search',
                           'allowed_domains': ['docs.python.org'], 'max_uses': 3}],
                'tool_choice': {'type': 'tool', 'name': 'web_search'}}

    def submit_payload(self, payload, path='/v1/messages'):
        self.client.request('POST', path, json.dumps(payload), {'x-api-key': 'client'})
        response = self.client.getresponse()
        result = response.status, response.read()
        self.client.close()
        self.client = http.client.HTTPConnection(*self.gate.server_address, timeout=3)
        return result

    def test_desktop_search_helper_preserves_search_contract_across_google_claude_and_api(self):
        self.backend.files = []
        self.backend.json_nonstream = True
        self.backend.catalog = ['gemini-3.1-flash-lite', 'gpt-6-luna']
        for model in ['claude-opus-4-6-thinking', 'api/test/deepseek', 'gemini-unlisted']:
            with self.subTest(model=model):
                payload = self.search_payload(model)
                status, _ = self.submit_payload(payload)
                self.assertEqual(status, 200)
                self.assertEqual(self.backend.last_request, {**payload, 'model': 'gpt-6-luna'})
        events = self.gate.diagnostics.snapshot()['events']
        self.assertEqual(sum(e['event'] == 'desktop_search_routed' for e in events), 3)

    def test_native_search_and_ordinary_conversations_do_not_change_models(self):
        self.backend.files = []
        self.backend.json_nonstream = True
        for model in ['gemini-3.1-flash-lite', 'gpt-6-luna']:
            with self.subTest(model=model):
                payload = self.search_payload(model)
                self.assertEqual(self.submit_payload(payload)[0], 200)
                self.assertEqual(self.backend.last_request, payload)
        for modification in [{'system': 'Normal conversation', 'messages': [{'role': 'user', 'content': 'Read this page'}]},
                             {'tools': []}, {'tool_choice': {'type': 'none'}}]:
            payload = {**self.search_payload('claude-opus-4-6-thinking'), **modification}
            self.assertEqual(self.submit_payload(payload)[0], 200)
            self.assertEqual(self.backend.last_request, payload)
        payload = self.search_payload('claude-opus-4-6-thinking')
        payload['tools'].append({'name': 'Read', 'input_schema': {'type': 'object'}})
        self.assertEqual(self.submit_payload(payload)[0], 200)
        self.assertEqual(self.backend.last_request, payload)

    def test_search_helper_uses_chatgpt_without_google_and_reports_missing_account(self):
        self.backend.files = []
        self.backend.json_nonstream = True
        self.backend.catalog = ['gpt-6-luna']
        payload = self.search_payload('claude-opus-4-6-thinking')
        self.assertEqual(self.submit_payload(payload)[0], 200)
        self.assertEqual(self.backend.last_request['model'], 'gpt-6-luna')
        self.backend.catalog = []
        previous_calls = self.backend.calls
        status, body = self.submit_payload(payload)
        self.assertEqual(status, 503)
        self.assertIn(b'Web search needs an available Google or ChatGPT account', body)
        self.assertEqual(self.backend.calls, previous_calls)
        self.assertEqual(self.gate.snapshot()['jobs'], [])

    def test_search_fallback_hides_plain_answer_and_returns_native_results_in_both_modes(self):
        self.backend.files = []
        self.backend.json_nonstream = True
        self.backend.catalog = ['gemini-3.1-flash-lite', 'gpt-6-luna']
        self.backend.search_without_results = {'gemini-3.1-flash-lite'}
        for stream in [False, True]:
            payload = self.search_payload('gemini-3.1-flash-lite')
            payload['stream'] = stream
            before = self.backend.calls
            status, body = self.submit_payload(payload)
            self.assertEqual(status, 200)
            self.assertIn(b'web_search_tool_result', body)
            self.assertNotIn(b'"text":"OK"', body)
            self.assertEqual(self.backend.last_request['model'], 'gpt-6-luna')
            self.assertEqual(self.backend.calls - before, 2)
    def test_sdk_identity_removed_for_stream_nonstream_and_token_count(self):
        from quota_queue import SDK_IDENTITY
        self.backend.files = []
        self.backend.json_nonstream = True
        for path, stream in [('/v1/messages', True), ('/v1/messages', False), ('/v1/messages/count_tokens', False)]:
            with self.subTest(path=path, stream=stream):
                payload = {'model': 'gemini-test', 'stream': stream,
                           'system': [{'type': 'text', 'text': SDK_IDENTITY},
                                      {'type': 'text', 'text': 'Keep all other instructions.', 'cache_control': {'type': 'ephemeral'}}],
                           'messages': [{'role': 'user', 'content': SDK_IDENTITY}],
                           'tools': [{'name': 'test', 'description': SDK_IDENTITY, 'input_schema': {'type': 'object'}}]}
                self.client.request('POST', path, json.dumps(payload), {'x-api-key': 'client'})
                response = self.client.getresponse()
                self.assertEqual(response.status, 200)
                response.read()
                forwarded = self.backend.last_request
                self.assertEqual(forwarded['system'], payload['system'][1:])
                self.assertEqual(forwarded['messages'], payload['messages'])
                self.assertEqual(forwarded['tools'], payload['tools'])
                self.client.close()
                self.client = http.client.HTTPConnection(*self.gate.server_address, timeout=3)

    def test_sdk_identity_only_exact_system_lines_and_idempotent(self):
        from quota_queue import SDK_IDENTITY, normalize_sdk_system
        request = {'system': 'Keep before.\n' + SDK_IDENTITY + '.\nKeep after.'}
        self.assertTrue(normalize_sdk_system(request))
        self.assertEqual(request['system'], 'Keep before.\nKeep after.')
        self.assertFalse(normalize_sdk_system(request))
        request = {'system': 'Quoted: ' + SDK_IDENTITY}
        self.assertFalse(normalize_sdk_system(request))
        request = {'system': SDK_IDENTITY}
        self.assertTrue(normalize_sdk_system(request))
        self.assertNotIn('system', request)

    def test_trailing_thinking_history_is_removed_without_touching_tools_or_text(self):
        from quota_queue import normalize_thinking_history
        request = {'messages': [
            {'role': 'user', 'content': 'Question'},
            {'role': 'assistant', 'content': [
                {'type': 'thinking', 'thinking': 'internal', 'signature': 'sig'},
                {'type': 'text', 'text': 'Answer'},
                {'type': 'thinking', 'thinking': 'late', 'signature': 'late-sig'},
            ]},
            {'role': 'assistant', 'content': [{'type': 'thinking', 'thinking': 'only'}]},
            {'role': 'user', 'content': 'Next'}]}
        self.assertTrue(normalize_thinking_history(request))
        self.assertEqual(request['messages'][1]['content'], [
            {'type': 'thinking', 'thinking': 'internal', 'signature': 'sig'},
            {'type': 'text', 'text': 'Answer'}])
        self.assertEqual(request['messages'][2]['content'], 'Next')
        self.assertFalse(normalize_thinking_history(request))

    def test_wait_heartbeat_then_new_account_real_response(self):
        response = self.post()
        self.assertEqual(response.read(len(PING)), PING)
        self.assertEqual(self.backend.calls, 0)
        self.assertEqual(self.gate.snapshot()['jobs'][0]['state'], 'waiting')
        self.backend.files.append({'provider': 'antigravity', 'name': 'new', 'cooldowns': []})
        data = response.read()
        self.assertIn(b'"id":"real"', data)
        self.assertIn(b'"text":"OK"', data)
        self.assertEqual(self.backend.calls, 1)
    def test_diagnostics_capture_wait_resume_and_finished_request(self):
        self.backend.files = [account(seconds=.35)]
        data = self.post().read()
        deadline = time.monotonic() + 1
        while self.gate.snapshot()['jobs'] and time.monotonic() < deadline:
            time.sleep(.01)
        events = self.gate.diagnostics.snapshot()['events']
        phases = {event['event'] for event in events}
        self.assertTrue({'received', 'validated', 'waiting_provider', 'upstream_started', 'upstream_headers', 'content_available', 'finished'} <= phases, phases)
        self.assertIn(b'OK', data)
        self.assertEqual(len({event['request_id'] for event in events}), 1)
        self.assertNotIn('client', json.dumps(events))

    def test_update_lock_blocks_new_requests_and_can_release(self):
        self.client.request('POST', '/v0/management/update-lock', headers={'Authorization':'Bearer admin'})
        self.assertEqual(self.client.getresponse().status, 200)
        self.client.close()
        self.client = http.client.HTTPConnection(*self.gate.server_address, timeout=3)
        response = self.post()
        self.assertEqual(response.status, 503)
        response.read()
        self.assertEqual(self.backend.calls, 0)
        self.client.request('DELETE', '/v0/management/update-lock', headers={'Authorization':'Bearer admin'})
        response = self.client.getresponse()
        self.assertEqual(response.status, 200)
        response.read()
        self.backend.files = []
        self.assertIn(b'OK', self.post().read())

    def test_reset_automatically_resumes(self):
        self.backend.files = [account(seconds=.2)]
        response = self.post(); data = response.read()
        self.assertTrue(data.startswith(PING))
        self.assertIn(b'message_stop', data); self.assertEqual(self.backend.calls, 1)
    def test_extended_context_suffix_preserves_quota_wait_and_upstream_model(self):
        self.backend.files = [account(seconds=.15)]
        response = self.post(model='alias[1m]')
        data = response.read()
        self.assertIn(PING, data)
        self.assertIn(b'message_stop', data)
        self.assertEqual(self.backend.last_request['model'], 'alias')
    def test_responses_wait_uses_comments_and_resumes_with_real_response(self):
        self.backend.files = [account(seconds=.15)]
        self.client.request('POST', '/v1/responses', json.dumps({'model':'alias','stream':True,'input':'hello'}), {'x-api-key':'client'})
        data = self.client.getresponse().read()
        self.assertIn(b': keep-alive\n\n', data)
        self.assertNotIn(PING, data)
        self.assertIn(b'event: response.completed', data)
        self.assertEqual(self.backend.calls, 1)
    def test_resumption_keeps_heartbeats_during_delayed_headers_and_body(self):
        self.backend.files = [account(seconds=.15)]
        # Keep phases long enough for coarse / loaded CI scheduler ticks.
        self.backend.header_delay = .4
        self.backend.body_delay = .4
        self.gate.heartbeat_seconds = .04
        response = self.post()
        data = response.read()
        self.assertGreaterEqual(data.count(PING), 5)
        self.assertIn(b'"text":"OK"', data)
        self.assertEqual(data.count(b'event: message_start'), 1)
        self.assertEqual(self.backend.calls, 1)
    def test_token_count_normalizes_context_suffix_and_logs_requested_model(self):
        self.client.request('POST', '/v1/messages/count_tokens', json.dumps({'model':'alias[1m]', 'messages':[]}), {'x-api-key':'client'})
        response = self.client.getresponse()
        response.read()
        self.assertEqual(self.backend.last_request['model'], 'alias')
        event = next(e for e in self.gate.diagnostics.snapshot()['events'] if e['event'] == 'token_count_requested')
        self.assertEqual(event['requested_model'], 'alias[1m]')

    def test_other_model_does_not_wait(self):
        response = self.post(model='claude')
        self.assertNotIn(PING, response.read()); self.assertEqual(self.backend.calls, 1)
    def test_empty_completion_retries_without_exposing_empty_message(self):
        self.backend.files = []
        self.backend.empty_attempts = 2
        response = self.post()
        data = response.read()
        self.assertEqual(self.backend.calls, 3)
        self.assertNotIn(b'"id":"empty"', data)
        self.assertEqual(data.count(b'event: message_start'), 1)
        self.assertIn(b'"text":"OK"', data)
    def test_repeated_empty_completion_reports_failure_instead_of_success(self):
        self.backend.files = []
        self.backend.empty_attempts = 100
        response = self.post()
        self.assertEqual(response.status, 502)
        data = response.read()
        self.assertIn(b'after 3 attempts', data)
        self.assertNotIn(b'message_stop', data)
        self.assertEqual(self.backend.calls, 3)
    def test_real_tool_call_is_delivered_once_without_retry(self):
        self.backend.files = []
        self.backend.tool_response = True
        response = self.post()
        data = response.read()
        self.assertIn(b'real-tool', data)
        self.assertEqual(self.backend.calls, 1)
    def test_gemini_guard_preserves_user_messages_system_and_tools(self):
        self.backend.files = []
        self.gate.aliases['alias'] = 'gemini-pro-agent'
        self.client.request('POST', '/v1/messages', json.dumps({'model':'alias','stream':True,
            'system':'Original instructions','messages':[{'role':'user','content':'Fix the bot'}],
            'tools':[{'name':'Bash','input_schema':{'type':'object'}}]}), {'x-api-key':'client'})
        self.client.getresponse().read()
        request = self.backend.last_request
        self.assertEqual(request['messages'], [{'role':'user','content':'Fix the bot'}])
        self.assertEqual(request['tools'][0]['name'], 'Bash')
        self.assertEqual(request['system'], 'Original instructions')
    def test_invalid_client_key_never_waits(self):
        response = self.post(key='wrong'); self.assertEqual(response.status, 401)
        response.read(); self.assertEqual(self.backend.calls, 0)
    def test_valid_bearer_with_stale_api_key_is_accepted(self):
        self.backend.files = []
        self.client.request('POST', '/v1/messages', json.dumps({'model': 'alias', 'stream': True}),
                            {'x-api-key': 'stale', 'Authorization': 'Bearer client'})
        response = self.client.getresponse()
        self.assertEqual(response.status, 200)
        self.assertIn(b'message_start', response.read())
    def test_429_without_cooldown_is_held_and_resumes_without_client_retry(self):
        self.backend.files = []
        self.backend.status = 429
        self.gate.retry_base_seconds = .15
        self.gate.retry_max_seconds = .15
        response = self.post()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.read(len(PING)), PING)
        self.assertEqual(self.backend.calls, 1)
        self.backend.status = 200
        data = response.read()
        self.assertIn(b'OK', data)
        self.assertNotIn(b'Denied', data)
        self.assertNotIn(b'event: error', data)
        self.assertEqual(self.backend.calls, 2)

    def test_verification_error_is_not_hidden_without_quota(self):
        self.backend.files = [account(code=403)]
        self.backend.status = 403
        response = self.post(); self.assertEqual(response.status, 403)
        self.assertIn(b'Denied', response.read())
    def test_disconnect_cancels_wait_without_inference(self):
        response = self.post(); response.read(len(PING))
        response.close(); self.client.close()
        until = time.time() + 2
        while self.gate.snapshot()['jobs'] and time.time() < until: time.sleep(.05)
        self.assertEqual(self.gate.snapshot()['jobs'], [])
        self.assertEqual(self.backend.calls, 0)
    def test_metadata_requires_management_key(self):
        self.client.request('GET', '/v0/management/quota-wait')
        response = self.client.getresponse(); self.assertEqual(response.status, 401); response.read()
    def test_disabled_and_nonquota_are_not_wait_reasons(self):
        a = account(); a['disabled'] = True
        self.assertIsNone(quota_wait([a], 'gemini', {}))
        self.assertIsNone(quota_wait([account(code=403)], 'gemini', {}))
    def test_known_unverified_account_does_not_prevent_quota_wait(self):
        pending = {'provider': 'antigravity', 'access_issue': 'verification', 'cooldowns': []}
        self.assertIsNotNone(quota_wait([account(), pending], 'gemini', {}))
        self.assertIsNone(quota_wait([pending], 'gemini', {}))
    def test_last_real_403_error_after_wait_is_delivered(self):
        response = self.post(); self.assertEqual(response.read(len(PING)), PING)
        self.backend.files = []
        self.backend.status = 403
        data = response.read()
        self.assertIn(b'event: error', data)
        self.assertIn(b'Denied', data)
        self.assertNotIn(b'message_start', data)
        self.assertEqual(self.backend.calls, 1)

    def test_hot_model_selection_does_not_wait_for_old_model_quota(self):
        self.backend.files = [account(model='gemini')]
        self.backend.model_aliases = [{'alias': 'alias', 'name': 'gemini-pro-agent'}]
        response = self.post()
        data = response.read()
        self.assertIn(b'"text":"OK"', data)
        self.assertNotIn(PING, data)
        self.assertEqual(self.gate.aliases['alias'], 'gemini-pro-agent')


if __name__ == '__main__': unittest.main()
