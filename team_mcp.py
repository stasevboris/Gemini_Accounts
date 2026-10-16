"""Local MCP stdio bridge. Only JSON-RPC goes to stdout; no API key in config."""
import json
import sys
import time
from team_service import TeamClient
from backend import AccountError
from runtime import VERSION

TOOLS = [
    {'name': 'team_config', 'description': 'Inspect the agent team saved in Gemini Accounts: roles, models, project folder, permissions and limits. No credentials are returned.',
     'inputSchema': {'type': 'object', 'properties': {}}},
    {'name': 'team_start', 'description': 'Delegate a shared task to the configured agent team. Include relevant current-chat context, project requirements and acceptance criteria in context. Returns a run_id immediately; use team_wait/status for progress. The saved UI permissions and budget apply.',
     'inputSchema': {'type': 'object', 'properties': {'task': {'type': 'string'}, 'context': {'type': 'string'}, 'request_key': {'type': 'string'}}, 'required': ['task']}},
    {'name': 'team_status', 'description': 'Read the team task board, peer reviews and final/partial result. Without run_id, inspect the current team.',
     'inputSchema': {'type': 'object', 'properties': {'run_id': {'type': 'string'}}}},
    {'name': 'team_wait', 'description': 'Wait up to 20 seconds for a team, returning its latest state/result. Repeat while unfinished; do not start another team.',
     'inputSchema': {'type': 'object', 'properties': {'run_id': {'type': 'string'}, 'seconds': {'type': 'integer', 'minimum': 1, 'maximum': 20}}, 'required': ['run_id']}},
    {'name': 'team_stop', 'description': 'Stop the specified team and restore its temporary account routes. The task board retains partial work.',
     'inputSchema': {'type': 'object', 'properties': {'run_id': {'type': 'string'}}, 'required': ['run_id']}},
]


def call_tool(name, args, client):
    if name == 'team_config':
        return client.request('config')
    if name == 'team_start':
        return client.request('start', {'task': args['task'], 'context': args.get('context', ''),
                                       'request_key': args.get('request_key'), 'source': 'mcp'})
    if name == 'team_stop':
        return client.request('cancel', {'id': args['run_id']})
    if name in ('team_wait', 'team_status'):
        seconds = args.get('seconds', 15) if name == 'team_wait' else 0
        if not isinstance(seconds, int) or isinstance(seconds, bool) or not 0 <= seconds <= 20:
            raise AccountError('Wait time must be 1–20 seconds.')
        deadline = time.monotonic() + seconds
        while True:
            ident = args.get('run_id')
            result = client.request('status?id=' + str(ident)) if ident else client.request('current')
            if not result.get('run') or result['run'].get('finished') or time.monotonic() >= deadline:
                return result
            time.sleep(.5)
    raise AccountError('Unknown team tool.')


def dispatch(message, client):
    method, params = message.get('method'), message.get('params') or {}
    if 'id' not in message:
        return None
    ident = message['id']
    try:
        if method == 'initialize':
            requested = params.get('protocolVersion')
            version = requested if requested in ('2025-11-25', '2025-06-18', '2025-03-26', '2024-11-05') else '2025-06-18'
            result = {'protocolVersion': version, 'capabilities': {'tools': {'listChanged': False}},
                      'serverInfo': {'name': 'Gemini Accounts Team', 'version': VERSION}}
        elif method == 'ping':
            result = {}
        elif method == 'tools/list':
            result = {'tools': TOOLS}
        elif method == 'tools/call':
            try:
                value = call_tool(params['name'], params.get('arguments') or {}, client)
                result = {'content': [{'type': 'text', 'text': json.dumps(value, ensure_ascii=False)}], 'isError': False}
            except (AccountError, KeyError, TypeError, OSError) as error:
                text = str(error) if isinstance(error, AccountError) else 'Invalid team tool arguments or local gateway unavailable.'
                result = {'content': [{'type': 'text', 'text': text}], 'isError': True}
        else:
            return {'jsonrpc': '2.0', 'id': ident, 'error': {'code': -32601, 'message': 'Method not found'}}
        return {'jsonrpc': '2.0', 'id': ident, 'result': result}
    except (ValueError, TypeError, AttributeError):
        return {'jsonrpc': '2.0', 'id': ident, 'error': {'code': -32602, 'message': 'Invalid request parameters'}}


def main():
    client = TeamClient()
    for raw in sys.stdin.buffer:
        try:
            if len(raw) > 8 * 1024 * 1024:
                raise ValueError()
            message = json.loads(raw)
            result = dispatch(message, client)
        except (ValueError, AttributeError):
            result = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Parse error'}}
        if result is not None:
            sys.stdout.buffer.write((json.dumps(result, ensure_ascii=False) + '\n').encode('utf-8'))
            sys.stdout.buffer.flush()


if __name__ == '__main__':
    main()
