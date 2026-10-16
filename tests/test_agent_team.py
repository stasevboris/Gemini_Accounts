import copy
import hashlib
import json
import tempfile
import threading
import time
from datetime import datetime, timezone
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_routes import AccountRoutes, read_leases, route_scope
from agent_team import DEFAULTS, TeamRun, validate, AgentProviderError, LocalTransport, retry_after_seconds
from agent_tools import TeamTools, public_url
from backend import AccountError, Controller, dpapi
from quota_queue import quota_wait


def person(ident, role='worker', provider='antigravity', model='gemini-3.8-flash-low', account=None):
    return {'id': ident, 'role': role, 'provider': provider, 'model': model,
            'account': account or ident + '.json', 'instructions': ''}


class FakeRoutes:
    def __init__(self):
        self.acquired, self.restored = [], 0

    def acquire(self, agent, stopped):
        self.acquired.append((agent['id'], agent['account'], agent['model']))
        return 'pinned/' + agent['id']

    def restore(self):
        self.restored += 1


class TeamTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.controller = Controller(proxy_dir=self.root / 'proxy', data_dir=self.root / 'data')
        self.controller.quota_wait_status = lambda: {'jobs': [], 'updating': False}
        self.config = {**copy.deepcopy(DEFAULTS), 'enabled': True, 'web': False,
            'participants': [person('lead', 'coordinator'), person('google'),
                             person('gpt', provider='codex', model='gpt-6-luna')]}
        self.routes = FakeRoutes()

    def tearDown(self):
        self.temp.cleanup()

    def transport(self, route, messages, tools, tokens):
        prompt = messages[-1]['content']
        if 'Break the shared task' in prompt:
            text = json.dumps({'tasks': [{'agent_id': 'google', 'task': 'Find A'}, {'agent_id': 'gpt', 'task': 'Find B'}]})
        elif 'Independently review' in prompt:
            text = json.dumps({'approved': True, 'feedback': 'Verified independently'})
        elif 'Synthesize the team' in prompt:
            text = 'Final combined deliverable'
        else:
            text = 'Result from ' + route
        return {'role': 'assistant', 'content': text}, {'prompt_tokens': 10, 'completion_tokens': 5}

    def test_mixed_accounts_run_plan_workers_peer_reviews_and_synthesis(self):
        run = TeamRun(self.controller, self.config, 'Find A and B', self.transport, self.routes)
        run.run()
        state = run.snapshot()
        self.assertEqual(state['status'], 'complete')
        self.assertEqual(state['requests'], 6)
        self.assertEqual(state['input_tokens'], 60)
        self.assertEqual(state['result'], 'Final combined deliverable')
        self.assertTrue(state['agents']['google']['approved'])
        self.assertTrue(state['agents']['gpt']['approved'])
        self.assertEqual(self.routes.restored, 2)
        self.assertIn(('gpt', 'gpt.json', 'gpt-6-luna'), self.routes.acquired)
        self.assertNotIn(b'Find A and B', run.path.read_bytes())
        self.assertEqual(json.loads(dpapi(run.path.read_bytes(), decrypt=True))['status'], 'complete')

    def test_failed_review_prevents_write_tools_and_cannot_report_complete(self):
        self.config.update(workspace=str(self.root), write=True)
        def transport(route, messages, tools, tokens):
            if 'Independently review' in messages[-1]['content']:
                return {'role': 'assistant', 'content': '{"approved":false,"feedback":"Missing evidence"}'}, {}
            if 'Synthesize the team' in messages[-1]['content']:
                self.assertFalse(any(t['function']['name'] == 'write_file' for t in tools))
            return self.transport(route, messages, tools, tokens)
        run = TeamRun(self.controller, self.config, 'Analyze', transport, self.routes)
        run.run()
        self.assertEqual(run.state['status'], 'needs_review')

    def test_request_limit_is_shared_across_all_agents_and_restores_routes(self):
        self.config['max_requests'] = 2
        run = TeamRun(self.controller, self.config, 'Analyze', self.transport, self.routes)
        run.run()
        self.assertEqual(run.state['status'], 'stopped')
        self.assertEqual(run.state['requests'], 2)
        self.assertEqual(self.routes.restored, 2)

    def test_transient_provider_errors_retry_within_the_shared_budget(self):
        failed = []
        def transport(*args):
            if not failed:
                failed.append(True)
                raise AgentProviderError(502, 'Temporary upstream error')
            return self.transport(*args)
        run = TeamRun(self.controller, self.config, 'Analyze', transport, self.routes)
        with patch.object(run.stop_event, 'wait', return_value=False):
            run.run()
        self.assertEqual(run.state['status'], 'complete')
        self.assertEqual(run.state['requests'], 7)

    def test_authentication_errors_are_not_retried(self):
        def transport(*args):
            raise AgentProviderError(401, 'Sign in again')
        run = TeamRun(self.controller, self.config, 'Analyze', transport, self.routes)
        run.run()
        self.assertEqual(run.state['requests'], 1)
        self.assertEqual(run.state['status'], 'error')

    def test_auth_unavailable_distinguishes_overload_from_reauthentication(self):
        self.assertFalse(AgentProviderError(503, 'auth_unavailable: no auth available').retryable)
        self.assertTrue(AgentProviderError(503, 'auth_unavailable; last upstream error: server_is_overloaded').retryable)

    def test_tool_budget_requests_final_result_without_tools(self):
        self.config['steps'] = 1
        lead = self.config['participants'][0]
        calls = []
        def transport(route, messages, tools, tokens):
            calls.append(bool(tools))
            if tools:
                return {'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'read-board', 'type': 'function',
                    'function': {'name': 'team_status', 'arguments': '{}'}}]}, {}
            return {'role': 'assistant', 'content': 'Concrete partial findings; validation remains unrun.'}, {}
        run = TeamRun(self.controller, self.config, 'Analyze', transport, self.routes)
        result = run._turn(lead, 'Find evidence')
        self.assertIn('partial findings', result)
        self.assertEqual(calls, [True, False])

    def test_reviewer_failure_uses_another_independent_account(self):
        author, reviewer, fallback = self.config['participants']
        run = TeamRun(self.controller, self.config, 'Analyze', self.transport, self.routes)
        def review(a, r):
            if r == reviewer:
                raise AgentProviderError(401, 'Sign in again')
            run.state['agents'][a['id']]['approved'] = True
        with patch.object(run, '_review', side_effect=review) as check:
            run._review_with_fallback(author, [reviewer, fallback])
        self.assertEqual(check.call_count, 2)
        self.assertTrue(run.state['agents'][author['id']]['approved'])

    def test_native_cooldown_is_waited_out_before_retrying_same_account(self):
        self.controller.key = 'test-management'
        until = datetime.fromtimestamp(time.time() + 60, timezone.utc).isoformat()
        other = datetime.fromtimestamp(time.time() + 3600, timezone.utc).isoformat()
        self.controller.request = lambda *args: {'files': [
            {'name': 'other.json', 'cooldowns': [{'scope': 'credential', 'retry_at': other}]},
            {'name': 'lead.json', 'cooldowns': [{'scope': 'model', 'model_key': 'unrelated-model', 'retry_at': other},
                {'scope': 'model', 'model_key': self.config['participants'][0]['model'], 'retry_at': until}]}]}
        failed = []
        def transport(*args):
            if not failed:
                failed.append(True)
                raise AgentProviderError(502, 'temporary overload')
            return self.transport(*args)
        run = TeamRun(self.controller, self.config, 'Analyze', transport, self.routes)
        with patch.object(run.stop_event, 'wait', return_value=False) as wait:
            run.run()
        self.assertEqual(run.state['status'], 'complete')
        self.assertGreater(wait.call_args.args[0], 59)
        self.assertLess(wait.call_args.args[0], 62)

    def test_retry_after_header_is_carried_by_transport_and_parsed_safely(self):
        self.controller.proxy_dir.mkdir()
        (self.controller.proxy_dir / 'client-key.txt').write_text('local-test-key')
        with patch('agent_team.http.client.HTTPConnection') as connection:
            response = connection.return_value.getresponse.return_value
            response.status = 503
            response.read.return_value = b'{"error":{"message":"server_is_overloaded"}}'
            response.getheader.return_value = '60'
            with self.assertRaises(AgentProviderError) as caught:
                LocalTransport(self.controller, lambda: False)('pinned/test', [], [], 256)
        self.assertEqual((caught.exception.status, caught.exception.retry_after), (503, 60))
        self.assertEqual(retry_after_seconds('Thu, 01 Jan 1970 00:02:00 GMT', now=60), 60)
        for value in ('nan', 'inf', '-5', None, 'invalid'):
            self.assertIsNone(retry_after_seconds(value))

    def test_stop_interrupts_provider_cooldown_and_does_not_send_next_request(self):
        entered = threading.Event()
        def transport(*args):
            entered.set()
            raise AgentProviderError(503, 'temporary overload', retry_after=60)
        run = TeamRun(self.controller, self.config, 'Analyze', transport, self.routes)
        run.start()
        self.assertTrue(entered.wait(2))
        deadline = time.monotonic() + 2
        while run.state['agents']['lead']['status'] != 'waiting' and time.monotonic() < deadline:
            time.sleep(.01)
        run.cancel()
        run.thread.join(2)
        self.assertFalse(run.thread.is_alive())
        self.assertEqual((run.state['status'], run.state['requests']), ('stopped', 1))

    def test_final_provider_failure_marks_coordinator_and_keeps_http_status(self):
        self.config['retries'] = 0
        def transport(*args):
            raise AgentProviderError(503, 'temporary overload', retry_after=60)
        run = TeamRun(self.controller, self.config, 'Analyze', transport, self.routes)
        run.run()
        self.assertEqual(run.state['error_http_status'], 503)
        self.assertEqual(run.state['agents']['lead']['status'], 'error')
        self.assertIn('temporary overload', run.state['agents']['lead']['feedback'])

    def test_cancelled_team_makes_no_provider_requests(self):
        run = TeamRun(self.controller, self.config, 'Analyze', self.transport, self.routes)
        run.cancel()
        run.run()
        self.assertEqual(run.state['status'], 'stopped')
        self.assertEqual(run.state['requests'], 0)

    def test_roster_validation_and_feature_default_off(self):
        self.assertFalse(DEFAULTS['enabled'])
        for override in ({'parallel': 101}, {'minutes': 0}, {'max_requests': True}, {'mode': 'unknown'}):
            with self.assertRaises(AccountError):
                validate({**self.config, **override})
        self.config['participants'][1]['id'] = 'lead'
        with self.assertRaises(AccountError):
            validate(self.config)

    def test_workers_cannot_write_and_changed_files_are_not_overwritten(self):
        config = {**self.config, 'workspace': str(self.root), 'write': True}
        backups = []
        tools = TeamTools(config, lambda: False, lambda **kw: backups.append(kw) if kw else {}, lambda *a: {})
        path = self.root / 'file.txt'
        path.write_text('before')
        old_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        args = {'path': 'file.txt', 'content': 'after', 'expected_sha256': old_hash}
        with self.assertRaises(AccountError):
            tools.execute('write_file', args, person('a'))
        path.write_text('changed outside the team')
        with self.assertRaises(AccountError):
            tools.execute('write_file', args, person('a'), can_write=True)
        self.assertEqual(path.read_text(), 'changed outside the team')
        read = tools.execute('read_file', {'path': 'file.txt'}, person('a'))
        args['expected_sha256'] = read['sha256']
        tools.execute('write_file', args, person('lead'), can_write=True)
        self.assertEqual(path.read_text(), 'after')
        self.assertEqual(backups[0]['backup_file'].resolve(), path.resolve())
        for value in ('../outside', '.git/config', '.env', '.codex/auth.json'):
            with self.assertRaises(AccountError):
                tools.path(value)
        with self.assertRaises(AccountError):
            tools.execute('run_command', {'argv': ['something']}, person('lead'), can_write=True)

    def test_messages_board_and_private_web_address_rejection(self):
        run = TeamRun(self.controller, self.config, 'Analyze', self.transport, self.routes)
        self.assertTrue(run.send_message('google', 'gpt', 'Please verify A')['delivered'])
        self.assertEqual(run.board(agent_id='gpt')['mailbox'][0]['from'], 'google')
        with self.assertRaises(AccountError):
            run.send_message('google', 'nonexistent', 'x')
        with self.assertRaises(AccountError):
            public_url('http://127.0.0.1:8318/v0/management/auth-files')

    def test_two_coordinators_cannot_control_one_team(self):
        self.config['participants'][1]['role'] = 'coordinator'
        with self.assertRaises(AccountError):
            TeamRun(self.controller, self.config, 'Analyze', self.transport, self.routes)

    def test_one_hundred_agents_use_bounded_parallelism_and_compact_board(self):
        self.config.update(max_requests=300, parallel=6)
        self.config['participants'] = [person('lead', 'coordinator')] + [person('worker-' + str(n)) for n in range(99)]
        activity = {'active': 0, 'peak': 0}
        lock = threading.Lock()
        gate = threading.Event()
        def transport(route, messages, tools, tokens):
            if 'Break the shared task' in messages[-1]['content']:
                text = json.dumps({'tasks': [{'agent_id': 'worker-' + str(n), 'task': 'Part ' + str(n)} for n in range(99)]})
                return {'role': 'assistant', 'content': text}, {}
            if route.startswith('pinned/worker-') and 'Independently review' not in messages[-1]['content']:
                with lock:
                    activity['active'] += 1
                    activity['peak'] = max(activity['peak'], activity['active'])
                    if activity['active'] == 6:
                        gate.set()
                self.assertTrue(gate.wait(timeout=2))
                with lock:
                    activity['active'] -= 1
            return self.transport(route, messages, tools, tokens)
        run = TeamRun(self.controller, self.config, 'Process 99 independent parts', transport, self.routes)
        run.run()
        self.assertEqual(run.state['status'], 'complete')
        self.assertEqual(run.state['requests'], 200)
        self.assertLess(len(json.dumps(run.board())), 50000)
        self.assertEqual(activity['peak'], 6)


    def test_run_lock_prevents_second_team_from_restoring_first_team_routes(self):
        first = TeamRun(self.controller, self.config, 'Analyze', self.transport, self.routes)
        first._acquire_run_lock()
        second_routes = FakeRoutes()
        second = TeamRun(self.controller, self.config, 'Analyze', self.transport, second_routes)
        try:
            second.run()
            self.assertEqual(second.state['status'], 'error')
            self.assertEqual(second_routes.restored, 0)
        finally:
            first.run_lock.close()


class AccountRouteTests(unittest.TestCase):
    def test_native_account_route_is_unique_reversible_and_quota_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            controller = Controller(proxy_dir=root / 'proxy', data_dir=root / 'data')
            auth = controller.proxy_dir / 'auth'
            auth.mkdir(parents=True)
            file = auth / 'google.json'
            file.write_text(json.dumps({'access_token': 'secret-not-shared', 'type': 'antigravity'}))
            requests = []
            def request(path, method='GET', data=None):
                requests.append((path, method, data))
                if path == '/force-model-prefix':
                    return {'force-model-prefix': False}
                if method == 'PATCH':
                    saved = json.loads(file.read_text())
                    saved['prefix'] = data['prefix']
                    file.write_text(json.dumps(saved))
                    return {}
                prefix = json.loads(file.read_text()).get('prefix', '')
                return {'models': [{'id': prefix + '/gemini-3.8-flash-low'}]}
            controller.request = request
            routes = AccountRoutes(controller)
            agent = person('a', account='google.json')
            model = routes.acquire(agent)
            self.assertTrue(model.startswith('ga-team-'))
            self.assertEqual(route_scope(model, routes.path)['name'], 'google.json')
            self.assertNotIn(b'google.json', routes.path.read_bytes())
            # A process crash after the prefix PATCH must be recoverable by a
            # fresh team instance using the durable lease.
            adopted = AccountRoutes(controller).acquire(agent)
            self.assertEqual(adopted, model)
            limit = {'name': 'google.json', 'provider': 'antigravity', 'cooldowns': [{
                'scope': 'model', 'model_key': agent['model'], 'http_status': 429,
                'reason': 'quota', 'retry_at': '2099-01-01T00:00:00Z'}]}
            with patch('quota_queue.route_scope', lambda name: route_scope(name, routes.path)):
                self.assertIsNotNone(quota_wait([limit, {'name': 'other.json', 'provider': 'antigravity'}], model, {}))
                self.assertIsNone(quota_wait([{**limit, 'name': 'other.json'}, {'name': 'google.json', 'provider': 'antigravity'}], model, {}))
            routes.restore()
            self.assertEqual(read_leases(routes.path), {})
            self.assertEqual(json.loads(file.read_text())['prefix'], '')
            self.assertEqual(json.loads(file.read_text())['access_token'], 'secret-not-shared')
            with self.assertRaises(AccountError):
                route_scope(model, routes.path)


if __name__ == '__main__':
    unittest.main()
