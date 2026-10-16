"""Local, cancellable quota waiting. No synthetic assistant output or tool calls."""
import http.client
import json
import queue
import secrets
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from backend import Controller, QUEUE_PORT, dpapi, AccountError
from agent_routes import route_scope, team_active
import yaml
from model_context import strip_context_suffix
from response_guard import StreamProbe, usable_message
from gateway_diagnostics import Diagnostics
from provider_errors import failure_reason, provider_error_metadata
import tokenharbor
import api_keys
from claude_auth import is_desktop_model as is_claude_subscription
from grok_auth import is_desktop_model as is_grok_subscription
from kimi_auth import is_desktop_model as is_kimi_subscription
from desktop_web import SEARCH_HELPERS, desktop_search_request, google_search_models, needs_search_helper

PING = b'event: ping\ndata: {"type":"ping"}\n\n'
HOP = {'connection', 'transfer-encoding', 'content-length', 'keep-alive',
       'proxy-authenticate', 'proxy-authorization', 'te', 'trailer', 'upgrade', 'host'}


SDK_IDENTITY = "You are a Claude agent, built on Anthropic's Claude Agent SDK"


class ProviderConfigurationError(OSError):
    pass


def normalize_sdk_system(request):
    """Drop only the standalone SDK identity line; never edit user messages or tools."""
    def clean(text):
        return ''.join(line for line in text.splitlines(keepends=True)
                       if line.strip() not in (SDK_IDENTITY, SDK_IDENTITY + '.'))
    system = request.get('system')
    changed = False
    if isinstance(system, str):
        value = clean(system)
        changed = value != system
        if changed:
            if value.strip():
                request['system'] = value
            else:
                request.pop('system')
    elif isinstance(system, list):
        blocks = []
        for block in system:
            if isinstance(block, dict) and block.get('type') == 'text' and isinstance(block.get('text'), str):
                value = clean(block['text'])
                if value != block['text']:
                    changed = True
                    if not value.strip():
                        continue
                    block = {**block, 'text': value}
            blocks.append(block)
        if changed:
            if blocks:
                request['system'] = blocks
            else:
                request.pop('system')
    return changed


def normalize_thinking_history(request):
    """Remove only trailing thinking blocks from replayed Anthropic turns.

    Anthropic accepts thinking blocks inside an assistant turn, but a turn sent
    back as history cannot end in ``thinking``. Preserve text, tool calls and
    user content; drop a malformed thinking-only assistant turn instead of
    inventing assistant output.
    """
    messages = request.get('messages')
    if not isinstance(messages, list):
        return False
    changed = False
    cleaned = []
    for message in messages:
        if not isinstance(message, dict) or message.get('role') != 'assistant':
            cleaned.append(message)
            continue
        content = message.get('content')
        if not isinstance(content, list):
            cleaned.append(message)
            continue
        blocks = list(content)
        while blocks and isinstance(blocks[-1], dict) and blocks[-1].get('type') in ('thinking', 'redacted_thinking'):
            blocks.pop()
            changed = True
        if blocks:
            if len(blocks) != len(content):
                message = {**message, 'content': blocks}
            cleaned.append(message)
        elif content:
            changed = True
        else:
            cleaned.append(message)
    if changed:
        request['messages'] = cleaned
    return changed


def deadline(item):
    try:
        return datetime.fromisoformat(item['retry_at'].replace('Z', '+00:00')).timestamp()
    except (KeyError, ValueError, TypeError):
        return 0


def gateway_aliases(channels):
    aliases = {a['alias']: a['name'] for a in channels.get('antigravity', [])}
    # A separate channel pins these models to native Claude credentials. Keep
    # the client alias in inference requests; replacing it would mix providers.
    aliases.update({a['alias']: 'claude-oauth/' + a['name'] for a in channels.get('claude', [])
                    if is_claude_subscription(a.get('alias'))})
    aliases.update({a['alias']: a['name'] for a in channels.get('xai', [])
                    if is_grok_subscription(a.get('alias'))})
    for provider in ('kimi', 'kimi-ai'):
        aliases.update({a['alias']: provider + '/' + a['name'] for a in channels.get(provider, [])
                        if is_kimi_subscription(a.get('alias'))})
    return aliases


def quota_wait(files, model, aliases, now=None):
    """Wait only for actual quota blocks, scoped to the requested upstream model."""
    now = time.time() if now is None else now
    model = strip_context_suffix(model)
    scope = route_scope(model)
    if scope:
        files = [a for a in files if a.get('name') == scope['name'] and
                 a.get('provider', a.get('type')) == scope['provider']]
        model = scope['model']
    model = aliases.get(model, model)
    if api_keys.is_model(model):
        # Google credential cooldowns have no bearing on this independent API.
        return None
    quota = []
    provider = ('claude' if model.startswith('claude-oauth/') or is_claude_subscription(model)
                else 'codex' if model.startswith('gpt-')
                else 'xai' if model.startswith('grok-') or is_grok_subscription(model)
                else 'kimi-ai' if model.startswith('kimi-ai/')
                else 'kimi' if model.startswith(('kimi-', 'kimi/')) else 'antigravity')
    if scope:
        provider = scope['provider']
    if model.startswith('claude-oauth/'):
        model = model.split('/', 1)[1]
    if model.startswith(('kimi/', 'kimi-ai/')):
        model = model.split('/', 1)[1]
    enabled = [a for a in files if not a.get('disabled') and
               a.get('provider', a.get('type')) == provider]
    for account in enabled:
        if account.get('access_issue') in ('verification', 'login', 'denied'):
            continue
        blocks = [b for b in account.get('cooldowns', []) if deadline(b) > now and
                  (b.get('scope') == 'credential' or b.get('model_key') == model)]
        if not blocks:
            # Verification is not a reason to hold a request forever.
            try:
                code = json.loads(account.get('status_message') or '{}').get('error', {}).get('code')
            except (ValueError, TypeError, AttributeError):
                code = None
            if code in (401, 403):
                continue
            return None
        quota_blocks = [b for b in blocks if b.get('http_status') == 429 and
                        b.get('reason') in ('quota', 'credential_quota', 'quota_exhausted', 'usage_limit')]
        if quota_blocks:
            quota.append(max(deadline(b) for b in blocks))
    return min(quota) if quota else None


class QueueServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, upstream, key, client_keys, aliases):
        super().__init__(address, Handler)
        self.upstream = upstream
        self.key = key
        self.client_keys = client_keys
        self.aliases = aliases
        self.jobs = {}
        self.updating = False
        self.diagnostics = Diagnostics()
        self.lock = threading.Lock()
        self.poll_seconds = 3
        self.retry_base_seconds = 5
        self.retry_max_seconds = 60
        self.heartbeat_seconds = 10
        self.verifications_path = None
        self.aliases_checked = 0
        self.tokenharbor_key = lambda: None
        self.api_profiles = lambda: []
        self.api_stats = api_keys.Stats()
        self.google_search_models = google_search_models()
        self.team_service = None

    def search_helper_model(self, exclude=()):
        """Select a supported search model currently published by the native service."""
        conn = http.client.HTTPConnection(*self.upstream, timeout=5)
        try:
            conn.request('GET', '/v1/models', headers={'Authorization': 'Bearer ' + self.client_keys[0]})
            response = conn.getresponse()
            if response.status != 200:
                raise OSError('Search model catalog unavailable')
            rows = json.loads(response.read()).get('data', [])
            available = {m['id'] for m in rows if isinstance(m, dict) and isinstance(m.get('id'), str)}
            return next((m for m in SEARCH_HELPERS if m in available and m not in exclude
                         and (m.startswith('gpt-') or m in self.google_search_models)), None)
        finally:
            conn.close()

    def refresh_aliases(self):
        # Hot model selection must also update quota-wait model scoping.
        with self.lock:
            if time.monotonic() - self.aliases_checked < 1:
                return
            self.aliases_checked = time.monotonic()
        conn = http.client.HTTPConnection(*self.upstream, timeout=3)
        try:
            conn.request('GET', '/v0/management/oauth-model-alias', headers={'Authorization': 'Bearer ' + self.key})
            response = conn.getresponse()
            if response.status == 200:
                result = json.loads(response.read())
                if 'oauth-model-alias' in result:
                    aliases = gateway_aliases(result['oauth-model-alias'] or {})
                    with self.lock:
                        self.aliases = aliases
        except (OSError, ValueError, KeyError, http.client.HTTPException):
            pass
        finally:
            conn.close()

    def accounts(self):
        conn = http.client.HTTPConnection(*self.upstream, timeout=12)
        try:
            conn.request('GET', '/v0/management/auth-files', headers={'Authorization': 'Bearer ' + self.key})
            response = conn.getresponse()
            if response.status != 200:
                raise OSError('Account metadata unavailable')
            files = json.loads(response.read()).get('files', [])
            if self.verifications_path:
                try:
                    issues = json.loads(dpapi(self.verifications_path.read_bytes(), decrypt=True))
                    for account in files:
                        account.update(issues.get(account.get('name'), {}))
                except (OSError, ValueError):
                    pass
            return files
        finally:
            conn.close()

    def snapshot(self):
        with self.lock:
            return {'jobs': [dict(j, upstream_model=self.aliases.get(j['model'], j['model'])) for j in self.jobs.values()], 'poll_seconds': self.poll_seconds, 'diagnostics_enabled': True, 'log_write_error': self.diagnostics.write_error, 'updating': self.updating}


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass  # Never log credentials, request bodies, or Google verification links.

    def trace(self, event, **fields):
        elapsed = round(time.monotonic() - self.trace_started, 3)
        fields['elapsed_seconds'] = elapsed
        fields.setdefault('response_bytes', self.response_bytes)
        self.server.diagnostics.record(self.request_id, event, **fields)
        with self.server.lock:
            job = self.server.jobs.get(self.request_id)
            if job is not None:
                job.update(phase=event, elapsed_seconds=elapsed, last_event_at=time.time())

    def chunk(self, data):
        self.wfile.write(('%x\r\n' % len(data)).encode() + data + b'\r\n')
        self.wfile.flush()

    def await_upstream(self, operation, stream, cleanup=None):
        """Keep the client alive while upstream headers or the next bytes are pending."""
        pending_since = time.monotonic()
        results = queue.Queue()
        cancelled = threading.Event()
        def run():
            try:
                value = operation()
                results.put((value, None))
                if cancelled.is_set() and cleanup:
                    cleanup(value)
            except Exception as error:
                results.put((None, error))
        threading.Thread(target=run, daemon=True).start()
        try:
            while True:
                try:
                    value, error = results.get(timeout=self.server.heartbeat_seconds)
                    if error:
                        raise error
                    return value
                except queue.Empty:
                    self.trace('upstream_pending', pending_seconds=round(time.monotonic() - pending_since, 3))
                    if stream:
                        if not self.response_started:
                            self.start_stream(True)
                        self.chunk(self.keepalive)
        except Exception:
            cancelled.set()
            if cleanup:
                try:
                    value, error = results.get_nowait()
                    if error is None:
                        cleanup(value)
                except queue.Empty:
                    pass
            raise

    def start_stream(self, stream):
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream' if stream else 'application/json')
        self.send_header('Transfer-Encoding', 'chunked')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.response_started = True

    def json_reply(self, status, value):
        data = json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def handle_request(self):
        self.response_started = False
        self.request_id = secrets.token_hex(8)
        self.trace_started = time.monotonic()
        self.response_bytes = 0
        self.api_profile = None
        self.api_profile_row = None
        self.api_failure = ''
        self.api_retry_after = None
        self.api_usage = api_keys.Usage()
        self.api_status = 502
        self.api_complete = False
        self.keepalive = PING if self.path.split('?')[0] == '/v1/messages' else b': keep-alive\n\n'
        tokens = [self.headers.get('x-api-key', ''), self.headers.get('Authorization', '').removeprefix('Bearer ')]
        if self.path.split('?')[0].startswith('/v0/management/team/'):
            from team_gateway import management
            management(self, tokens)
            return
        if self.path in ('/v0/management/quota-wait', '/v0/management/diagnostics', '/v0/management/update-lock', '/v0/management/api-key-stats'):
            if not any(secrets.compare_digest(token.encode(), self.server.key.encode()) for token in tokens):
                self.json_reply(401, {'error': {'type': 'authentication_error', 'message': 'Unauthorized'}})
                return
            if self.path.endswith('update-lock'):
                if self.command not in ('POST', 'DELETE'):
                    self.json_reply(405, {'error':'Use POST or DELETE'})
                    return
                if self.command == 'DELETE':
                    with self.server.lock:
                        self.server.updating = False
                    self.json_reply(200, {'locked':False})
                    return
                with self.server.lock:
                    if self.server.jobs or team_active():
                        self.json_reply(409, {'error':'Requests are running'})
                        return
                    self.server.updating = True
                self.json_reply(200, {'locked':True})
                return
            if self.path.endswith('api-key-stats'):
                self.json_reply(200, self.server.api_stats.snapshot())
            else:
                self.json_reply(200, self.server.snapshot() if self.path.endswith('quota-wait') else dict(self.server.diagnostics.snapshot(), **self.server.snapshot()))
            return
        if self.command == 'GET' and self.path.split('?')[0] == '/v1/models':
            if not any(secrets.compare_digest(token.encode(), key.encode()) for token in tokens for key in self.server.client_keys):
                self.json_reply(401, {'error': {'type': 'authentication_error', 'message': 'Invalid API key'}})
                return
            self.model_catalog()
            return
        self.trace('received', method=self.command, path=self.path.split('?')[0])
        size = int(self.headers.get('Content-Length', '0'))
        body = self.rfile.read(size) if size else None
        inference = self.command == 'POST' and self.path.split('?')[0] in ('/v1/messages', '/v1/responses', '/v1/chat/completions')
        if not inference:
            if self.command == 'POST' and self.path.split('?')[0] == '/v1/messages/count_tokens':
                try:
                    request = json.loads(body)
                    changed = normalize_sdk_system(request)
                    changed = normalize_thinking_history(request) or changed
                    if changed:
                        self.trace('history_normalized')
                        body = json.dumps(request, ensure_ascii=False).encode()
                    raw_model = request.get('model')
                    normalized = strip_context_suffix(raw_model)
                    from team_service import TEAM_MODEL
                    if normalized == TEAM_MODEL and any(secrets.compare_digest(token.encode(), key.encode()) for token in tokens for key in self.server.client_keys):
                        self.json_reply(200, {'input_tokens': max(1, len(json.dumps(request.get('messages', []))) // 4)})
                        return
                    if isinstance(normalized, str):
                        self.trace('token_count_requested', model=normalized, requested_model=raw_model)
                        request['model'] = normalized
                        body = json.dumps(request, ensure_ascii=False).encode()
                except (ValueError, TypeError, AttributeError):
                    pass
            self.forward(body)
            return
        if not any(secrets.compare_digest(token.encode(), key.encode()) for token in tokens for key in self.server.client_keys):
            self.trace('authentication_rejected', status=401)
            self.json_reply(401, {'error': {'type': 'authentication_error', 'message': 'Invalid API key'}})
            return
        try:
            request = json.loads(body)
            model = request['model']
            if not isinstance(model, str):
                raise ValueError()
            if self.path.split('?')[0] == '/v1/messages':
                changed = normalize_sdk_system(request)
                changed = normalize_thinking_history(request) or changed
                if changed:
                    self.trace('history_normalized')
                    body = json.dumps(request, ensure_ascii=False).encode()
            requested_model = model
            normalized = strip_context_suffix(model)
            if normalized != model:
                model = normalized
                request['model'] = model
                body = json.dumps(request, ensure_ascii=False).encode()
        except (ValueError, KeyError, TypeError):
            self.forward(body)
            return
        stream = bool(request.get('stream'))
        guarded = self.path.split('?')[0] == '/v1/messages'
        ident = self.request_id
        attempt = 0
        self.trace('validated', model=model, requested_model=requested_model, stream=stream, request_bytes=size)
        started = False
        empty_retries = 0
        rate_retries = 0
        provider_retry_at = 0
        self.api_attempted = set()
        with self.server.lock:
            if self.server.updating:
                self.json_reply(503, {'error': {'type':'api_error', 'message':'Gateway updating. Retry shortly.'}})
                return
            self.server.jobs[ident] = {'model': model, 'state': 'running', 'since': time.time(), 'retry_at': None}
        try:
            from team_service import TEAM_MODEL
            if model == TEAM_MODEL and not (guarded and desktop_search_request(request)):
                from team_gateway import serve_model
                serve_model(self, request)
                return
            self.desktop_search = guarded and desktop_search_request(request)
            search_attempted = set()
            if guarded:
                self.server.refresh_aliases()
                actual = self.server.aliases.get(model, model)
                if self.desktop_search:
                    search_attempted.add(actual)
                if needs_search_helper(request, actual, self.server.google_search_models):
                    helper = self.server.search_helper_model()
                    if helper is None:
                        raise ProviderConfigurationError(
                            'Web search needs an available Google or ChatGPT account. '
                            'Connect or resume one in Gemini Accounts, then retry the search.')
                    request['model'] = model = helper
                    search_attempted.add(helper)
                    body = json.dumps(request, ensure_ascii=False).encode()
                    with self.server.lock:
                        self.server.jobs[ident]['model'] = model
                    self.trace('desktop_search_routed', requested_model=requested_model, upstream_model=helper)
            while True:
                accounts = []
                try:
                    self.server.refresh_aliases()
                    external = api_keys.is_model(self.server.aliases.get(model, model))
                    accounts = [] if external else self.server.accounts()
                    reset = quota_wait(accounts, model, self.server.aliases)
                except (OSError, ValueError, http.client.HTTPException):
                    reset = None
                if provider_retry_at > time.time():
                    reset = max(reset or 0, provider_retry_at)
                if reset:
                    with self.server.lock:
                        was_waiting = self.server.jobs[ident].get('state') == 'waiting'
                        self.server.jobs[ident].update(state='waiting', retry_at=reset)
                    if not was_waiting:
                        self.trace('waiting_provider', retry_at=reset, wait_seconds=round(max(0, reset-time.time()), 3),
                            accounts=[{'name': a.get('name'), 'disabled': bool(a.get('disabled')), 'unavailable': bool(a.get('unavailable')),
                                       'cooldowns': [{k: c.get(k) for k in ('scope', 'model_key', 'reason', 'http_status', 'retry_at')} for c in a.get('cooldowns') or []]} for a in accounts])
                    if not started:
                        self.start_stream(stream)
                        started = True
                    self.chunk(self.keepalive if stream else b'\n')
                    # A disconnected client cancels on the next heartbeat. New accounts
                    # and manually cleared cooldowns are observed on every poll.
                    time.sleep(min(self.server.poll_seconds, max(.05, reset - time.time())))
                    continue
                with self.server.lock:
                    self.server.jobs[ident].update(state='running', retry_at=None)
                attempt += 1
                actual_model = self.server.aliases.get(model, model)
                team_scope = route_scope(model)
                external = api_keys.is_model(actual_model)
                self.trace('upstream_started', attempt=attempt, model=model, upstream_model=actual_model,
                           provider=team_scope['provider'] if team_scope else 'api' if external else 'claude' if actual_model.startswith('claude-oauth/') else 'codex' if actual_model.startswith('gpt-') else 'xai' if actual_model.startswith('grok-') else 'kimi-ai' if actual_model.startswith('kimi-ai/') else 'kimi' if actual_model.startswith(('kimi-', 'kimi/')) else 'antigravity')
                try:
                    conn, response = self.await_upstream(lambda: self.open_upstream(body, model=model), stream,
                                                         cleanup=lambda result: result[0].close())
                except (OSError, http.client.HTTPException):
                    self.record_api_attempt()
                    if external and self.api_fallback_available(actual_model):
                        self.trace('api_key_fallback', cause='connection_error')
                        continue
                    raise
                started = self.response_started
                self.api_status = response.status
                self.trace('upstream_headers', attempt=attempt, status=response.status)
                try:
                    if external and response.status >= 400:
                        error = response.read()
                        self.api_failure = api_keys.failure_state(response.status, error)
                        try:
                            self.api_retry_after = float(response.getheader('Retry-After') or 0)
                        except (ValueError, TypeError):
                            self.api_retry_after = None
                        self.trace('provider_rejected', status=response.status, provider='api', reason='API provider rejected request')
                        if (self.api_failure == 'exhausted' or response.status in (401, 402, 403, 429, 500, 502, 503, 504)) and self.api_fallback_available(actual_model):
                            self.trace('api_key_fallback', status=response.status)
                            continue
                        if self.api_failure == 'exhausted':
                            # Make the terminal response actionable instead of
                            # exposing only a provider-specific one-liner.
                            self.trace('api_tokens_exhausted', status=response.status,
                                       reason='No compatible API key remains with usable quota.')
                            error = json.dumps({'type': 'error', 'error': {'type': 'insufficient_quota',
                                'message': 'API key tokens or quota are exhausted; no compatible key is currently available. Add another key or replenish the provider balance.'}}).encode()
                        self.deliver(response, error, started, stream)
                        self.api_complete = True
                        return
                    if response.status in (429, 403, 503):
                        error = response.read()
                        reason = 'API provider rejected request' if external else failure_reason(response.status, error) or 'Provider rejected request'
                        self.trace('provider_rejected', status=response.status, reason=reason,
                                   provider='api' if external else 'antigravity', **provider_error_metadata(error))
                        try:
                            reset = None if external else quota_wait(self.server.accounts(), model, self.server.aliases)
                        except (OSError, ValueError, http.client.HTTPException):
                            reset = None
                        if response.status == 429:
                            if (team_scope['model'] if team_scope else actual_model).startswith('gpt-') and not reset:
                                self.deliver(response, error, started, stream)
                                return
                            rate_retries += 1
                            delay = min(self.server.retry_max_seconds,
                                        self.server.retry_base_seconds * (2 ** min(rate_retries - 1, 8)))
                            try:
                                reported = float(response.getheader('Retry-After') or 0)
                                if reported > 0:
                                    delay = max(delay, min(reported, 3600))
                            except (ValueError, TypeError):
                                pass
                            # Account cooldowns must be re-evaluated on each poll:
                            # a newly available account should wake this request.
                            provider_retry_at = 0 if reset else time.time() + delay
                            self.trace('rate_limit_retry_scheduled', attempt=attempt,
                                retry_at=reset or provider_retry_at, wait_seconds=max(0, (reset or provider_retry_at)-time.time()))
                            continue
                        if reset:
                            continue
                        self.deliver(response, error, started, stream)
                        self.api_complete = True
                        return
                    if guarded and response.status == 200:
                        try:
                            valid = self.deliver_validated(response, stream)
                        except ValueError:
                            self.recovery_error(stream)
                            return
                        if not valid:
                            self.api_status = 502
                            self.trace('empty_response', attempt=attempt)
                            if self.desktop_search:
                                helper = self.server.search_helper_model(search_attempted)
                                if helper is None or attempt >= 3:
                                    self.provider_configuration_error(
                                        'The available models did not return web-search results. '
                                        'Check Google/ChatGPT account access and retry the search.', stream)
                                    return
                                search_attempted.add(helper)
                                request['model'] = model = helper
                                body = json.dumps(request, ensure_ascii=False).encode()
                                with self.server.lock:
                                    self.server.jobs[ident]['model'] = model
                                self.trace('desktop_search_fallback', requested_model=requested_model,
                                           upstream_model=helper)
                                continue
                            if external and self.api_fallback_available(actual_model):
                                self.trace('api_key_fallback', cause='empty_response')
                                continue
                            empty_retries += 1
                            if empty_retries <= 2:
                                if external:
                                    self.api_attempted.discard(self.api_profile)
                                with self.server.lock:
                                    self.server.jobs[ident].update(recovery_reason='empty_response', attempt=empty_retries + 1)
                                continue
                            self.recovery_error(stream)
                        else:
                            self.api_complete = True
                        return
                    self.deliver(response, None, started, stream)
                    self.api_complete = True
                    return
                finally:
                    conn.close()
                    self.record_api_attempt()
        except (ProviderConfigurationError, AccountError) as error:
            self.trace('provider_configuration_error', status=503, provider='api')
            self.provider_configuration_error(str(error), stream)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError) as error:
            self.trace('connection_ended', exception_type=type(error).__name__)
            self.close_connection = True
        except (OSError, http.client.HTTPException) as exception:
            self.trace('upstream_error', exception_type=type(exception).__name__)
            error = {'type': 'error', 'error': {'type': 'api_error', 'message': 'Local inference service unavailable'}}
            try:
                if self.response_started:
                    self.chunk((b'event: error\ndata: ' + json.dumps(error).encode() + b'\n\n') if stream else json.dumps(error).encode())
                    self.wfile.write(b'0\r\n\r\n')
                else:
                    self.json_reply(502, error)
            except OSError:
                pass
        finally:
            self.record_api_attempt()
            self.trace('finished', attempt=attempt)
            with self.server.lock:
                self.server.jobs.pop(ident, None)

    def open_upstream(self, body, model=None):
        actual = self.server.aliases.get(strip_context_suffix(model), strip_context_suffix(model))
        if api_keys.is_model(actual):
            rows = self.server.api_profiles()
            choices = api_keys.candidates(rows, actual, getattr(self, 'api_attempted', set()),
                                          health=self.server.api_stats.snapshot())
            profile, raw = choices[0] if choices else (None, None)
            # Accept the old direct model ID during migration, without aliasing Google models.
            if profile is None and not rows and tokenharbor.is_model(actual) and self.server.tokenharbor_key():
                profile = {'id': 'tokenharbor', 'kind': 'tokenharbor', 'base_url': 'https://' + tokenharbor.HOST,
                           'key': self.server.tokenharbor_key()}
                raw = actual
            if profile is None or not profile.get('key'):
                if api_keys.candidates(rows, actual):
                    raise ProviderConfigurationError('All compatible API keys are temporarily unavailable (quota, authentication or request limit). See API keys for the reason and retry time.')
                raise ProviderConfigurationError('API key is missing or disabled. Add it in the API keys tab (TokenHarbor API key).')
            if not hasattr(self, 'api_attempted'):
                self.api_attempted = set()
            self.api_attempted.add(profile['id'])
            self.api_profile = profile['id']
            self.api_profile_row = profile
            self.api_failure = ''
            self.api_retry_after = None
            self.api_model = raw
            self.api_usage = api_keys.Usage()
            self.api_status = 502
            self.api_complete = False
            self.api_started = time.monotonic()
            request = json.loads(body)
            request['model'] = raw
            body = json.dumps(request, ensure_ascii=False).encode()
            # Preserve the client's protocol: Anthropic messages and SSE must
            # remain Anthropic, while OpenAI requests keep their own endpoint.
            # Header names are case-insensitive. urllib sends "Content-type";
            # retaining it alongside a new "Content-Type" makes some providers
            # reject a valid JSON body because they see two media types.
            headers = {k.lower(): v for k, v in self.headers.items()
                       if k.lower() not in HOP | {'authorization', 'x-api-key', 'cookie', 'x-goog-api-key', 'user-agent', 'content-type'}}
            headers['User-Agent'] = api_keys.request_headers()['User-Agent']
            if profile.get('kind') == 'anthropic':
                headers['x-api-key'] = profile['key']
                headers.setdefault('anthropic-version', '2023-06-01')
            else:
                headers['Authorization'] = 'Bearer ' + profile['key']
            headers['Content-Type'] = 'application/json'
            base = urllib.parse.urlsplit(profile['base_url'])
            conn = http.client.HTTPSConnection(base.netloc, timeout=60)
            try:
                conn.request(self.command, base.path.rstrip('/') + self.path, body=body, headers=headers)
                return conn, conn.getresponse()
            except Exception:
                conn.close()
                raise

        if actual and actual.startswith('gpt-') and actual != model:
            request = json.loads(body)
            request['model'] = actual
            body = json.dumps(request, ensure_ascii=False).encode()
        conn = http.client.HTTPConnection(*self.server.upstream, timeout=600)
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP}
        try:
            conn.request(self.command, self.path, body=body, headers=headers)
            return conn, conn.getresponse()
        except Exception:
            conn.close()
            raise

    def api_fallback_available(self, model):
        return bool(api_keys.candidates(self.server.api_profiles(), model, self.api_attempted,
                                       health=self.server.api_stats.snapshot()))

    def deliver_validated(self, response, stream):
        """Retry only before any assistant content or tool call reaches the client."""
        if not stream:
            data = self.await_upstream(response.read, False)
            self.response_bytes += len(data)
            self.trace('nonstream_body_received')
            try:
                value = json.loads(data)
                self.api_usage.json(value)
                valid = usable_message(value, require_search=getattr(self, 'desktop_search', False))
            except (ValueError, AttributeError, TypeError):
                valid = False
            if valid:
                self.deliver(response, data, self.response_started, False)
            return valid
        probe = StreamProbe(require_search=getattr(self, 'desktop_search', False))
        while True:
            data = self.await_upstream(lambda: response.read1(65536), True)
            if not data:
                break
            self.response_bytes += len(data)
            if not probe.buffer:
                self.trace('first_upstream_bytes')
            self.trace('stream_progress')
            probe.feed(data)
            self.api_usage.feed(data)
            if probe.usable or probe.error:
                if probe.error:
                    self.api_status = 502
                self.trace('content_available', terminal=probe.terminal, error=probe.error)
                if not self.response_started:
                    self.start_stream(True)
                self.chunk(bytes(probe.buffer))
                # Continue the original stream; never retry a tool already exposed.
                self.deliver(response, None, True, True)
                return True
            if probe.terminal:
                break
        self.trace('stream_without_answer', terminal=probe.terminal)
        return False

    def recovery_error(self, stream):
        self.api_status = 502
        self.trace('recovery_exhausted', status=502)
        error = {'type': 'error', 'error': {'type': 'api_error',
            'message': 'The model returned no usable answer after 3 attempts. Retry the request; no tool call was delivered.'}}
        if not self.response_started:
            self.json_reply(502, error)
        else:
            self.chunk((b'event: error\ndata: ' + json.dumps(error).encode() + b'\n\n') if stream else json.dumps(error).encode())
            self.wfile.write(b'0\r\n\r\n')
            self.wfile.flush()

    def provider_configuration_error(self, message, stream=False):
        error = {'type': 'error', 'error': {'type': 'api_error', 'message': message}}
        if not self.response_started:
            self.json_reply(503, error)
        else:
            data = json.dumps(error).encode()
            self.chunk(b'event: error\ndata: ' + data + b'\n\n' if stream else data)
            self.wfile.write(b'0\r\n\r\n')
            self.wfile.flush()

    def deliver(self, response, body, started=False, stream=False):
        if not started:
            self.send_response(response.status)
            for key, value in response.getheaders():
                if key.lower() not in HOP:
                    self.send_header(key, value)
            self.send_header('Transfer-Encoding', 'chunked')
            self.end_headers()
            self.response_started = True
        elif response.status >= 400:
            data = body if body is not None else response.read()
            if stream:
                self.chunk(b'event: error\ndata: ' + data.replace(b'\n', b' ') + b'\n\n')
            else:
                self.chunk(data)
            self.wfile.write(b'0\r\n\r\n')
            return
        if body is not None:
            if self.api_profile:
                try:
                    self.api_usage.json(json.loads(body))
                except ValueError:
                    pass
            if body:
                self.chunk(body)
        else:
            captured = bytearray()
            while True:
                data = self.await_upstream(lambda: response.read1(65536), stream)
                if not data:
                    break
                self.response_bytes += len(data)
                self.trace('stream_progress')
                if self.api_profile:
                    self.api_usage.feed(data)
                    if not stream and len(captured) < 1000000:
                        captured.extend(data)
                self.chunk(data)
            if self.api_profile and captured:
                try:
                    self.api_usage.json(json.loads(captured))
                except ValueError:
                    pass
        self.wfile.write(b'0\r\n\r\n')
        self.wfile.flush()

    def forward(self, body):
        conn = None
        try:
            model = None
            try:
                if body:
                    req = json.loads(body)
                    model = req.get("model")
            except Exception:
                pass
            if model is not None:
                self.server.refresh_aliases()
            if api_keys.is_model(self.server.aliases.get(model, model)):
                tokens = [self.headers.get('x-api-key', ''), self.headers.get('Authorization', '').removeprefix('Bearer ')]
                if not any(secrets.compare_digest(token.encode(), key.encode()) for token in tokens for key in self.server.client_keys):
                    self.json_reply(401, {'error': {'type': 'authentication_error', 'message': 'Invalid API key'}})
                    return
            conn, response = self.open_upstream(body, model=model)
            self.trace('forwarded_headers', status=response.status)
            self.deliver(response, None)
            self.trace('finished')
        except ProviderConfigurationError as error:
            self.provider_configuration_error(str(error))
        except (OSError, http.client.HTTPException):
            self.close_connection = True
        finally:
            if conn:
                conn.close()

    do_GET = do_POST = do_PATCH = do_PUT = do_DELETE = do_OPTIONS = handle_request

    def record_api_attempt(self):
        if self.api_profile is not None and not self.api_profile.startswith('test-'):
            status = self.api_status
            if self.api_usage.failed and status == 200:
                status = 502
            if status == 200 and not self.api_complete:
                status = 499
            self.server.api_stats.record(self.api_profile, self.api_model, status, self.api_usage,
                                         time.monotonic() - self.api_started, failure=self.api_failure or self.api_usage.failure,
                                         retry_after=self.api_retry_after, profile=self.api_profile_row)
        self.api_profile = None

    def model_catalog(self):
        conn = http.client.HTTPConnection(*self.server.upstream, timeout=5)
        models = []
        try:
            conn.request('GET', '/v1/models', headers={'Authorization': 'Bearer ' + self.server.client_keys[0]})
            response = conn.getresponse()
            if response.status == 200:
                models = json.loads(response.read()).get('data', [])
        except (OSError, ValueError, http.client.HTTPException):
            pass
        finally:
            conn.close()
        models = [entry for entry in models if entry.get('owned_by') not in ('xai', 'grok', 'kimi', 'kimi-ai')
                  and not str(entry.get('id', '')).startswith(('grok-', 'kimi-', 'kimi/', 'kimi-ai/'))
                  and not is_grok_subscription(entry.get('id')) and not is_kimi_subscription(entry.get('id'))]
        models.extend({'id': entry['id'], 'object': 'model', 'owned_by': 'api', 'display_name': entry['label']}
                      for entry in api_keys.catalog_rows(self.server.api_profiles()))
        from team_service import TEAM_MODEL
        models.append({'id': TEAM_MODEL, 'object': 'model', 'owned_by': 'gemini-accounts', 'display_name': 'Agent team / Команда агентов'})
        self.json_reply(200, {'object': 'list', 'data': models})


def main():
    controller = Controller()
    config = yaml.safe_load((controller.proxy_dir / 'config.yaml').read_text('utf-8-sig'))
    key = dpapi((controller.data_dir / 'management-key.dpapi').read_bytes(), decrypt=True).decode()
    aliases = gateway_aliases(config.get('oauth', {}).get('model-alias', {}))
    keys = config.get('access', {}).get('api-keys', [])
    server = QueueServer(('127.0.0.1', QUEUE_PORT), ('127.0.0.1', config['server']['port']), key, keys, aliases)
    server.diagnostics = Diagnostics(controller.data_dir / 'gateway-diagnostics.jsonl')
    server.diagnostics.record('service', 'started', phase='ready')
    server.verifications_path = controller.verification_path
    server.api_profiles = lambda: api_keys.profiles(controller, private=True)
    server.api_stats = api_keys.Stats(controller.data_dir / 'api-key-stats.json')
    server.serve_forever()


if __name__ == '__main__':
    main()
