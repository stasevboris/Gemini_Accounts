import copy
import http.client
import json
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from backend import AccountError, Controller, dpapi
from agent_team import DEFAULTS, TeamRun, AgentProviderError
from agent_tools import TeamTools
from agent_routes import team_active
from project_files import read_text, read_chunk, read_document
from quota_queue import QueueServer
from team_service import TEAM_MODEL, TeamService, chat_context
from team_mcp import dispatch
from tests.test_agent_team import FakeRoutes, person


class ProjectReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_large_unicode_file_can_be_read_completely_by_lines_and_offsets(self):
        text = ''.join('Строка ' + str(n) + ': ' + 'текст ' * 25 + '\n' for n in range(2000))
        path = self.root / 'large.md'
        path.write_bytes(text.encode('utf-8'))
        offset, chunks = 0, []
        while offset is not None:
            page = read_chunk(path, offset)
            chunks.append(page['text'])
            offset = page['next_offset']
        self.assertEqual(''.join(chunks), text)
        start, lines = 1, []
        while start is not None:
            page = read_text(path, start)
            lines.extend(page['text'].splitlines())
            start = page['next_line']
        self.assertEqual(lines, text.splitlines())

    def test_docx_extracts_paragraphs_tables_and_paginates(self):
        path = self.root / 'requirements.docx'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Техническое задание</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Критерий: 42</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>')
        data = read_text(path, max_lines=1)
        self.assertEqual(data['text'], 'Техническое задание')
        self.assertEqual(read_text(path, data['next_line'])['text'], 'Критерий: 42')

    def test_pdf_page_ranges_and_encryption_are_handled(self):
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
        writer = PdfWriter()
        for n in range(2):
            page = writer.add_blank_page(width=200, height=200)
            font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
            page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
            stream = DecodedStreamObject()
            stream.set_data(('BT /F1 12 Tf 20 100 Td (Page ' + str(n + 1) + ' evidence) Tj ET').encode())
            page[NameObject('/Contents')] = writer._add_object(stream)
        path = self.root / 'source.pdf'
        writer.write(path)
        first = read_document(path, max_pages=1)
        self.assertEqual(first['total_pages'], 2)
        self.assertIn('Page 1 evidence', first['pages'][0]['text'])
        self.assertIn('Page 2 evidence', read_document(path, start_page=first['next_page'])['pages'][0]['text'])
        writer.encrypt('test-password')
        writer.write(path)
        with self.assertRaises(AccountError):
            read_document(path)

    def test_search_recurses_and_keeps_secret_and_external_paths_out(self):
        (self.root / 'src').mkdir()
        (self.root / 'src/code.py').write_text('value = "needle"\n', 'utf-8')
        (self.root / '.env').write_text('needle=private', 'utf-8')
        (self.root / 'node_modules').mkdir()
        (self.root / 'node_modules/noise.py').write_text('needle', 'utf-8')
        tools = TeamTools({**DEFAULTS, 'workspace': str(self.root)}, lambda: False, lambda **kw: {}, lambda *a: {})
        result = tools.execute('search_files', {'query': 'needle'}, {'id': 'worker'})
        self.assertEqual([m['path'] for m in result['matches']], ['src/code.py'])
        with self.assertRaises(AccountError):
            tools.execute('read_text_chunk', {'path': '../outside.md'}, {'id': 'worker'})


class TeamChatTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = {**copy.deepcopy(DEFAULTS), 'enabled': True, 'web': False, 'review_rounds': 1,
                       'participants': [person('lead', 'coordinator'), person('worker')]}
        c = self.controller()
        c.preferences['agent-team'] = self.config
        c.save()
        self.messages = []
        def transport(model, messages, tools, output_tokens):
            self.messages.append(copy.deepcopy(messages))
            last = messages[-1]['content']
            if 'Break the shared task' in last:
                content = json.dumps({'tasks': [{'agent_id': 'worker', 'task': 'Read the user context and answer.'}]})
            elif 'Independently review' in last:
                content = json.dumps({'approved': True, 'feedback': 'Checked the evidence.'})
            else:
                content = 'Project Mars: reviewed answer 42.'
            return {'role': 'assistant', 'content': content}, {'prompt_tokens': 10, 'completion_tokens': 5}
        self.service = TeamService(self.controller, lambda c, config, task, context='':
            TeamRun(c, config, task, transport=transport, routes=FakeRoutes(), context=context))
        self.gate = QueueServer(('127.0.0.1', 0), ('127.0.0.1', 1), 'test-admin', ['test-client'], {})
        self.gate.team_service = self.service
        threading.Thread(target=self.gate.serve_forever, daemon=True).start()

    def controller(self):
        c = Controller(proxy_dir=self.root / 'proxy', data_dir=self.root / 'data')
        c.quota_wait_status = lambda: {'updating': False}
        return c

    def tearDown(self):
        if self.service.run and self.service.run.thread.is_alive():
            self.service.run.cancel()
            self.service.run.thread.join(3)
        self.gate.shutdown()
        self.gate.server_close()
        self.temp.cleanup()

    def request(self, path, payload=None, key='test-client'):
        conn = http.client.HTTPConnection(*self.gate.server_address, timeout=5)
        conn.request('POST' if payload is not None else 'GET', path,
                     json.dumps(payload) if payload is not None else None, {'Authorization': 'Bearer ' + key})
        response = conn.getresponse()
        result = response.status, response.read()
        conn.close()
        return result

    def test_virtual_model_preserves_existing_chat_context_and_returns_anthropic_result(self):
        payload = {'model': TEAM_MODEL, 'stream': False, 'messages': [
            {'role': 'user', 'content': 'Our project is named Mars.'},
            {'role': 'assistant', 'content': 'I remember Mars.'},
            {'role': 'user', 'content': 'Ask the team for a reviewed answer.'}]}
        status, raw = self.request('/v1/messages', payload)
        self.assertEqual(status, 200)
        result = json.loads(raw)
        self.assertEqual(result['stop_reason'], 'end_turn')
        self.assertIn('Mars', result['content'][0]['text'])
        self.assertTrue(any('Our project is named Mars' in json.dumps(m) for m in self.messages))
        run = self.service.run
        private = json.loads(dpapi(run.path.read_bytes(), decrypt=True))
        self.assertIn('Our project is named Mars', private['context'])
        current = self.service.current()
        self.assertNotIn('context', current)
        self.assertNotIn('messages', current['agents']['worker'])

    def test_streams_and_openai_compatible_routes_finish_correctly(self):
        for path in ('/v1/messages', '/v1/chat/completions', '/v1/responses'):
            payload = {'model': TEAM_MODEL, 'stream': True, 'messages': [{'role': 'user', 'content': 'Test ' + path}]}
            status, raw = self.request(path, payload)
            self.assertEqual(status, 200)
            self.assertIn(b'reviewed answer 42', raw)
            self.assertIn(b'message_stop' if path.endswith('messages') else b'response.completed' if path.endswith('responses') else b'[DONE]', raw)

    def test_management_requires_management_key_and_never_accepts_permission_overrides(self):
        self.assertEqual(self.request('/v0/management/team/config')[0], 401)
        status, raw = self.request('/v0/management/team/config', key='test-admin')
        self.assertEqual(status, 200)
        self.assertNotIn('account', json.loads(raw)['participants'][0])
        status, raw = self.request('/v0/management/team/start', {'task': 'Safe test', 'config': {'commands': True, 'write': True}}, key='test-admin')
        self.assertEqual(status, 200)
        self.service.run.thread.join(3)
        self.assertFalse(self.service.run.config['commands'])
        self.assertFalse(self.service.run.config['write'])

    def test_identical_redelivery_reuses_run_and_disabled_feature_has_actionable_error(self):
        first = self.service.start('Task', 'history', 'chat', 'same-request')
        self.service.run.thread.join(3)
        second = self.service.start('Task', 'history', 'chat', 'same-request')
        self.assertEqual(first['id'], second['id'])
        c = self.controller()
        c.preferences['agent-team']['enabled'] = False
        c.save()
        status, raw = self.request('/v1/messages', {'model': TEAM_MODEL, 'messages': [{'role': 'user', 'content': 'New task'}]})
        self.assertEqual(status, 400)
        self.assertIn('Save settings', raw.decode())

    def test_mcp_initializes_lists_tools_and_delegates_without_exposing_credentials(self):
        response = dispatch({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-06-18'}}, None)
        self.assertIn('tools', response['result']['capabilities'])
        tools = dispatch({'id': 2, 'method': 'tools/list'}, None)['result']['tools']
        self.assertEqual({t['name'] for t in tools}, {'team_start', 'team_status', 'team_wait', 'team_stop', 'team_config'})
        client = type('Client', (), {'request': lambda _, endpoint, payload=None:
            {'run': self.service.start(payload['task'], payload.get('context', ''), 'mcp')} if endpoint == 'start' else {'run': self.service.current()}})()
        result = dispatch({'id': 3, 'method': 'tools/call', 'params': {'name': 'team_start', 'arguments': {'task': 'Test', 'context': 'Existing project notes'}}}, client)
        self.assertFalse(result['result']['isError'])
        self.service.run.thread.join(3)
        self.assertEqual(self.service.run.state['source'], 'mcp')
        self.assertNotIn('test-admin', result['result']['content'][0]['text'])

    def test_provider_error_keeps_status_and_identical_retry_starts_fresh_run(self):
        c = self.controller()
        c.preferences['agent-team']['retries'] = 0
        c.save()
        def transport(*args):
            raise AgentProviderError(503, 'server_is_overloaded', retry_after=60)
        self.service.run_factory = lambda c, config, task, context='': TeamRun(c, config, task, transport=transport, routes=FakeRoutes(), context=context)
        payload = {'model': TEAM_MODEL, 'messages': [{'role': 'user', 'content': 'Retry this task'}]}
        status, raw = self.request('/v1/messages', payload)
        self.assertEqual(status, 503)
        self.assertEqual(json.loads(raw)['error']['status_code'], 503)
        self.assertEqual(json.loads(raw)['error']['type'], 'overloaded_error')
        before = self.service.run.id
        self.service.run.thread.join(3)
        status, raw = self.request('/v1/messages', payload)
        self.assertNotEqual(self.service.run.id, before)
        self.assertEqual(status, 503)

    def test_stream_provider_error_keeps_status_in_error_event(self):
        c = self.controller()
        c.preferences['agent-team']['retries'] = 0
        c.save()
        def transport(*args):
            raise AgentProviderError(503, 'server_is_overloaded')
        self.service.run_factory = lambda c, config, task, context='': TeamRun(c, config, task, transport=transport, routes=FakeRoutes(), context=context)
        status, raw = self.request('/v1/messages', {'model': TEAM_MODEL, 'stream': True, 'messages': [{'role': 'user', 'content': 'Test overload'}]})
        self.assertEqual(status, 200)
        self.assertIn(b'event: error', raw)
        self.assertIn(b'"status_code": 503', raw)
        self.assertNotIn(b'event: message_stop', raw)

    def test_token_count_and_catalog_recognize_team_without_native_alias(self):
        status, raw = self.request('/v1/messages/count_tokens', {'model': TEAM_MODEL, 'messages': [{'role': 'user', 'content': 'Hi'}]})
        self.assertEqual(status, 200)
        self.assertGreater(json.loads(raw)['input_tokens'], 0)
        status, raw = self.request('/v1/models')
        self.assertEqual(status, 200)
        self.assertIn(TEAM_MODEL, [m['id'] for m in json.loads(raw)['data']])

    def test_context_retains_tool_results_but_not_binary_payloads(self):
        task, context = chat_context({'messages': [
            {'role': 'user', 'content': [{'type': 'text', 'text': 'Analyse project'}, {'type': 'image', 'source': {'type': 'base64', 'data': 'private-binary'}}]},
            {'role': 'assistant', 'content': [{'type': 'tool_use', 'name': 'Read', 'id': 'read1', 'input': {'path': 'plan.md'}}]},
            {'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': 'read1', 'content': 'Project evidence'}]}]})
        self.assertEqual(task, 'Analyse project')
        self.assertIn('Project evidence', context)
        self.assertNotIn('private-binary', context)

    def test_panel_owned_run_is_visible_and_cancelled_from_another_process_interface(self):
        entered, cancelled = threading.Event(), threading.Event()
        class BlockingTransport:
            def __call__(self, *args):
                entered.set()
                cancelled.wait(5)
                return {'role': 'assistant', 'content': '{}'}, {}
            def cancel(self):
                cancelled.set()
        run = TeamRun(self.controller(), self.config, 'UI task', transport=BlockingTransport(), routes=FakeRoutes())
        run.start()
        self.assertTrue(entered.wait(2))
        self.assertEqual(self.service.current()['id'], run.id)
        self.service.cancel(run.id)
        run.thread.join(3)
        self.assertFalse(run.thread.is_alive())
        self.assertEqual(self.service.status(run.id)['status'], 'stopped')
        self.assertFalse(team_active(self.controller().data_dir))

    def test_long_agent_context_is_summarized_and_full_record_stays_encrypted(self):
        requests = []
        def transport(model, messages, tools, output_tokens):
            requests.append(copy.deepcopy(messages))
            if 'Summarize this agent work history' in messages[-1]['content']:
                return {'role': 'assistant', 'content': 'Evidence: src/main.py line 12. Pending: final analysis.'}, {}
            self.assertIn('src/main.py line 12', messages[1]['content'])
            return {'role': 'assistant', 'content': 'Analysis complete'}, {}
        run = TeamRun(self.controller(), self.config, 'Task', transport=transport, routes=FakeRoutes())
        run.state['agents']['lead']['messages'] = [{'role': 'system', 'content': 'System instructions'},
            {'role': 'user', 'content': 'old source evidence ' * 12000}]
        self.assertEqual(run._turn(self.config['participants'][0], 'Finish the analysis'), 'Analysis complete')
        self.assertEqual(len(requests), 2)
        run.save(force=True)
        self.assertNotIn(b'old source evidence', run.path.read_bytes())
        archived = json.loads(dpapi(run.path.read_bytes(), decrypt=True))['agents']['lead']['archives']
        self.assertGreater(len(archived[0][1]['content']), 180000)


if __name__ == '__main__':
    unittest.main()
