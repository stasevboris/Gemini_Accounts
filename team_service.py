"""One saved team, shared by the desktop panel, model gateway and local MCP."""
import copy
import hashlib
import json
import re
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

from backend import AccountError, Controller, QUEUE_PORT, atomic_write, dpapi
from agent_team import TeamRun, validate
from agent_routes import team_active

TEAM_MODEL = 'claude-sonnet-4-5-team-100000000001'


def public_state(state):
    config = {k: copy.deepcopy(v) for k, v in state['config'].items() if k != 'participants'}
    return {**{k: copy.deepcopy(v) for k, v in state.items() if k not in ('context', 'file_backups', 'agents', 'config')},
            'config': config, 'agents': {key: {k: copy.deepcopy(v) for k, v in agent.items()
                if k not in ('messages', 'archive', 'archives', 'mailbox')} for key, agent in state['agents'].items()}}


def chat_context(request):
    # Content blocks are retained as reference. Binary attachment data is not
    # useful as text and must not crowd out the actual conversation.
    def clean(value):
        if isinstance(value, dict):
            if value.get('type') in ('base64', 'image_url'):
                return {'type': value['type'], 'note': 'Binary attachment: use the project file tools for its local source.'}
            return {k: clean(v) for k, v in value.items() if k not in ('cache_control', 'signature')}
        if isinstance(value, list):
            return [clean(v) for v in value]
        return value
    messages = request.get('messages', request.get('input', []))
    if isinstance(messages, str):
        messages = [{'role': 'user', 'content': messages}]
    if not isinstance(messages, list):
        raise AccountError('The chat must provide a message history.')
    context = json.dumps(clean({'system': request.get('system', request.get('instructions', '')),
                               'messages': messages}), ensure_ascii=False)
    if len(context) > 2000000:
        raise AccountError('Chat history exceeds 2,000,000 characters. Start a narrower team task.')
    task = ''
    for message in reversed(messages):
        if not isinstance(message, dict) or message.get('role') != 'user':
            continue
        content = message.get('content', '')
        if isinstance(content, str):
            task = content
        elif isinstance(content, list):
            task = '\n'.join(str(block.get('text', '')) for block in content
                             if isinstance(block, dict) and block.get('type') in ('text', 'input_text'))
        if task.strip():
            break
    if not task.strip():
        task = 'Continue the user task from the supplied conversation history, in the user language.'
    if len(task) > 50000:
        task = 'Complete the latest user request in the supplied conversation. Read its full text using read_chat_context.\n' + task[-40000:]
    return task, context


class TeamService:
    def __init__(self, controller_factory=Controller, run_factory=TeamRun):
        self.controller_factory, self.run_factory = controller_factory, run_factory
        self.lock = threading.RLock()
        self.run = None
        self.recent = {}

    def configuration(self):
        c = self.controller_factory()
        config = c.preferences.get('agent-team', {})
        people = config.get('participants', [])
        return {'enabled': bool(config.get('enabled')), 'workspace': config.get('workspace', ''),
                'participants': [{k: p.get(k) for k in ('id', 'provider', 'model', 'role', 'instructions')} for p in people],
                'limits': {k: config.get(k) for k in ('parallel', 'max_requests', 'minutes', 'steps', 'output_tokens', 'review_rounds')},
                'permissions': {k: bool(config.get(k)) for k in ('web', 'write', 'commands')},
                'ready': bool(config.get('enabled') and people)}

    def load(self, ident):
        if not isinstance(ident, str) or not re.fullmatch('[a-f0-9]{32}', ident):
            raise AccountError('Invalid team run ID.')
        c = self.controller_factory()
        try:
            return json.loads(dpapi((c.data_dir / 'team-runs' / (ident + '.dpapi')).read_bytes(), decrypt=True))
        except (OSError, ValueError):
            raise AccountError('Team run not found.') from None

    def current(self):
        with self.lock:
            if self.run and self.run.thread and self.run.thread.is_alive():
                return public_state(self.run.snapshot())
        c = self.controller_factory()
        try:
            ident = json.loads((c.data_dir / 'team-current.json').read_text('utf-8'))['id']
            state = self.load(ident)
            if not state.get('finished') and not team_active(c.data_dir):
                state.update(status='interrupted', finished=time.time(), error='The team process stopped; the run was not resumed automatically.')
            return public_state(state)
        except (OSError, ValueError, KeyError, AccountError):
            return None

    def status(self, ident):
        with self.lock:
            if self.run and self.run.id == ident:
                return public_state(self.run.snapshot())
        state = self.load(ident)
        if not state.get('finished') and not team_active(self.controller_factory().data_dir):
            state.update(status='interrupted', finished=time.time())
        return public_state(state)

    def start(self, task, context='', source='client', request_key=None):
        if source not in ('chat', 'mcp', 'ui', 'client'):
            raise AccountError('Invalid team invocation source.')
        if request_key is not None and (not isinstance(request_key, str) or not 1 <= len(request_key) <= 256):
            raise AccountError('Request key must be a string of 1–256 characters.')
        with self.lock:
            # Repeated network delivery must not spend a second team's budget.
            now = time.monotonic()
            self.recent = {k: v for k, v in self.recent.items() if now - v[0] < 3600
                           or self.run and self.run.id == v[1] and self.run.thread.is_alive()}
            c = self.controller_factory()
            config = copy.deepcopy(c.preferences.get('agent-team', {}))
            if not config.get('enabled') or not config.get('participants'):
                raise AccountError('Open Team in Gemini Accounts, configure the roster, enable the feature and click Save settings first.')
            config = validate(config)
            if request_key:
                request_key = hashlib.sha256((request_key + json.dumps(config, sort_keys=True)).encode()).hexdigest()
                if request_key in self.recent:
                    previous = self.status(self.recent[request_key][1])
                    # A completed failure is retryable delivery, not a cached
                    # successful answer. Active and completed results stay deduped.
                    if previous['status'] != 'error' or not previous.get('finished'):
                        return previous
            if team_active(c.data_dir):
                raise AccountError('A team is already running. View its progress or stop it before another task.')
            run = self.run_factory(c, config, task, context=context)
            run.state['source'] = source
            run.state['language'] = c.preferences.get('language', 'en')
            run.start()
            self.run = run
            if request_key:
                self.recent[request_key] = (now, run.id)
            return public_state(run.snapshot())

    def cancel(self, ident):
        with self.lock:
            if self.run and self.run.id == ident:
                self.run.cancel()
            else:
                state = self.load(ident)
                if not state.get('finished'):
                    c = self.controller_factory()
                    atomic_write(c.data_dir / 'team-runs' / (ident + '.cancel'), b'cancel')
            return self.status(ident)


class TeamClient:
    def __init__(self, controller=None):
        import os
        self.controller = controller or Controller(data_dir=os.environ.get('GEMINI_TEAM_DATA_DIR'), proxy_dir=os.environ.get('GEMINI_TEAM_PROXY_DIR'))

    def request(self, endpoint, payload=None):
        c = self.controller
        key = c.key or dpapi((c.data_dir / 'management-key.dpapi').read_bytes(), decrypt=True).decode()
        request = urllib.request.Request(f'http://127.0.0.1:{QUEUE_PORT}/v0/management/team/' + endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None,
            headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=10) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            try:
                message = json.loads(error.read(20000)).get('error', {}).get('message')
            except (ValueError, AttributeError):
                message = None
            raise AccountError(message or 'The team gateway rejected this action.') from None
        except (OSError, ValueError):
            raise AccountError('Cannot reach the team gateway. Open or update Gemini Accounts first.') from None
