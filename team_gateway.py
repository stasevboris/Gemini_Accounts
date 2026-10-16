"""Authenticated local team controls and a virtual chat-model route."""
import hashlib
import json
import secrets
import time
import urllib.parse

from backend import AccountError, Controller
from team_service import TEAM_MODEL, TeamService, chat_context
from agent_team import AgentProviderError


def service(server):
    with server.lock:
        if not getattr(server, 'team_service', None):
            def controller():
                c = Controller()
                c.base = 'http://' + str(server.upstream[0]) + ':' + str(server.upstream[1])
                c.key = server.key
                return c
            server.team_service = TeamService(controller)
        return server.team_service


def management(handler, tokens):
    if not any(secrets.compare_digest(t.encode(), handler.server.key.encode()) for t in tokens):
        handler.json_reply(401, {'error': {'message': 'Unauthorized'}})
        return
    path = urllib.parse.urlsplit(handler.path)
    action = path.path.removeprefix('/v0/management/team/')
    try:
        team = service(handler.server)
        if handler.command == 'GET':
            if action == 'config':
                value = team.configuration()
            elif action == 'current':
                value = {'run': team.current()}
            elif action == 'status':
                value = {'run': team.status(urllib.parse.parse_qs(path.query).get('id', [''])[0])}
            else:
                handler.json_reply(404, {'error': {'message': 'Unknown team action'}})
                return
        elif handler.command == 'POST' and action in ('start', 'cancel'):
            size = int(handler.headers.get('Content-Length', '0'))
            if not 0 < size <= 8 * 1024 * 1024:
                raise AccountError('Invalid team request size.')
            data = json.loads(handler.rfile.read(size))
            if action == 'start':
                with handler.server.lock:
                    if handler.server.updating:
                        raise AccountError('An update is in progress. Retry shortly.')
                value = {'run': team.start(data.get('task'), data.get('context', ''), data.get('source', 'mcp'), data.get('request_key'))}
            else:
                value = {'run': team.cancel(data.get('id'))}
        else:
            handler.json_reply(405, {'error': {'message': 'Unsupported team method'}})
            return
        handler.json_reply(200, value)
    except (AccountError, ValueError, TypeError, AttributeError) as error:
        message = str(error) if isinstance(error, AccountError) else 'Invalid team request.'
        handler.json_reply(400, {'error': {'type': 'invalid_request_error', 'message': message}})


def serve_model(handler, request):
    team = service(handler.server)
    ident = None
    stream = bool(request.get('stream'))
    anthropic = handler.path.split('?')[0] == '/v1/messages'
    responses = handler.path.split('?')[0] == '/v1/responses'
    message_id = 'msg_team_' + secrets.token_hex(12)
    try:
        task, context = chat_context(request)
        # Exact redelivery reuses a recent run; no request headers or credentials
        # become part of the task or saved chat reference.
        fingerprint = hashlib.sha256(context.encode()).hexdigest()
        state = team.start(task, context, 'chat', fingerprint)
        ident = state['id']
        if stream:
            handler.start_stream(True)
            if anthropic:
                event(handler, 'message_start', {'type': 'message_start', 'message': {
                    'id': message_id, 'type': 'message', 'role': 'assistant', 'model': TEAM_MODEL,
                    'content': [], 'stop_reason': None, 'stop_sequence': None,
                    'usage': {'input_tokens': 0, 'output_tokens': 0}}})
                event(handler, 'content_block_start', {'type': 'content_block_start', 'index': 0,
                    'content_block': {'type': 'text', 'text': ''}})
            elif responses:
                event(handler, 'response.created', {'type': 'response.created', 'response': {'id': message_id, 'object': 'response', 'status': 'in_progress', 'output': []}})
            else:
                chat_delta(handler, message_id, {'role': 'assistant', 'content': ''})
        last_event, heartbeat = None, time.monotonic()
        while not state.get('finished'):
            waiting = tuple((key, agent.get('retry_at')) for key, agent in state.get('agents', {}).items() if agent.get('status') == 'waiting')
            marker = (state['status'], state['requests'], waiting)
            if stream and marker != last_event:
                ru = state.get('language') == 'ru'
                phase = {'ready': 'готова', 'planning': 'планирование', 'working': 'выполнение',
                         'reviewing': 'проверка', 'synthesizing': 'подготовка итога'}.get(state['status'], state['status']) if ru else state['status']
                text = ('Команда · ' if ru else 'Team · ') + phase + (' · запросов: ' if ru else ' · requests: ') + str(state['requests']) + '\n'
                if waiting:
                    seconds = max(0, round(max(value or time.time() for _, value in waiting) - time.time()))
                    text += ('Ожидают повтора: ' if ru else 'Waiting to retry: ') + ', '.join(key for key, _ in waiting) + ' · ' + str(seconds) + (' с\n' if ru else ' s\n')
                delta(handler, message_id, text, anthropic, responses)
                last_event = marker
                heartbeat = time.monotonic()
            elif stream and time.monotonic() - heartbeat >= 5:
                handler.chunk(b': team-running\n\n')
                heartbeat = time.monotonic()
            time.sleep(.25)
            state = team.status(ident)
        if state['status'] in ('error', 'stopped', 'interrupted'):
            if state.get('error_http_status'):
                code = state['error_http_status']
                detail = state.get('error', '').removeprefix('Agent provider returned HTTP ' + str(code) + ': ')
                raise AgentProviderError(code, detail, state.get('error_retry_after'))
            raise AccountError(state.get('error') or 'The team did not finish. See its task board for partial results.')
        text = state.get('result') or 'The team produced no final result. See the task board.'
        if state['status'] != 'complete':
            text = ('Команда завершила работу с замечаниями; часть результатов требует проверки.\n\n' if state.get('language') == 'ru' else
                    'The team finished with outstanding review findings; some results still need review.\n\n') + text
        if state.get('route_restore_error'):
            text += ('\n\nНе удалось восстановить часть временных маршрутов. Подробности во вкладке «Команда».' if state.get('language') == 'ru' else
                     '\n\nSome temporary routes could not be restored. See the Team tab for details.')
        usage = {'input_tokens': state.get('input_tokens', 0), 'output_tokens': state.get('output_tokens', 0)}
        if not stream:
            if anthropic:
                value = {'id': message_id, 'type': 'message', 'role': 'assistant', 'model': TEAM_MODEL,
                         'content': [{'type': 'text', 'text': text}], 'stop_reason': 'end_turn', 'stop_sequence': None, 'usage': usage}
            elif responses:
                value = response_value(message_id, text, usage)
            else:
                value = {'id': message_id, 'object': 'chat.completion', 'created': int(time.time()), 'model': TEAM_MODEL,
                         'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': text}, 'finish_reason': 'stop'}],
                         'usage': {'prompt_tokens': usage['input_tokens'], 'completion_tokens': usage['output_tokens'], 'total_tokens': sum(usage.values())}}
            handler.json_reply(200, value)
        else:
            delta(handler, message_id, '\n' + text, anthropic, responses)
            if anthropic:
                event(handler, 'content_block_stop', {'type': 'content_block_stop', 'index': 0})
                event(handler, 'message_delta', {'type': 'message_delta', 'delta': {'stop_reason': 'end_turn', 'stop_sequence': None}, 'usage': usage})
                event(handler, 'message_stop', {'type': 'message_stop'})
            elif responses:
                event(handler, 'response.completed', {'type': 'response.completed', 'response': response_value(message_id, text, usage)})
            else:
                chat_delta(handler, message_id, {}, finish='stop')
                handler.chunk(b'data: [DONE]\n\n')
            handler.wfile.write(b'0\r\n\r\n')
            handler.wfile.flush()
    except AccountError as error:
        status = error.status if isinstance(error, AgentProviderError) else 400
        value = {'type': 'error', 'error': {'type': 'overloaded_error' if status in (502, 503, 504) else 'api_error',
                                         'message': str(error), 'status_code': status}}
        if handler.response_started:
            event(handler, 'error', value)
            handler.wfile.write(b'0\r\n\r\n')
            handler.wfile.flush()
        else:
            handler.json_reply(status, value)
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError):
        if ident:
            team.cancel(ident)


def event(handler, name, value):
    handler.chunk(('event: ' + name + '\ndata: ' + json.dumps(value, ensure_ascii=False) + '\n\n').encode())


def chat_delta(handler, ident, content, finish=None):
    value = {'id': ident, 'object': 'chat.completion.chunk', 'created': int(time.time()), 'model': TEAM_MODEL,
             'choices': [{'index': 0, 'delta': content, 'finish_reason': finish}]}
    handler.chunk(('data: ' + json.dumps(value, ensure_ascii=False) + '\n\n').encode())


def delta(handler, ident, text, anthropic, responses):
    if anthropic:
        event(handler, 'content_block_delta', {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': text}})
    elif responses:
        event(handler, 'response.output_text.delta', {'type': 'response.output_text.delta', 'item_id': ident + '_text', 'output_index': 0, 'content_index': 0, 'delta': text})
    else:
        chat_delta(handler, ident, {'content': text})


def response_value(ident, text, usage):
    return {'id': ident, 'object': 'response', 'created_at': int(time.time()), 'status': 'completed', 'model': TEAM_MODEL,
            'output': [{'id': ident + '_text', 'type': 'message', 'status': 'completed', 'role': 'assistant',
                        'content': [{'type': 'output_text', 'text': text, 'annotations': []}]}],
            'usage': {**usage, 'total_tokens': sum(usage.values())}}
