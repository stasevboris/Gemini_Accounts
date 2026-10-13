"""Route Desktop's isolated search tool without switching its conversation model."""
import json
import sys
from pathlib import Path

SEARCH_TYPES = {'web_search_20250305', 'web_search_20260209'}
SEARCH_SYSTEM = 'You are an assistant for performing a web search tool use'
SEARCH_QUERY = 'Perform a web search for the query: '
SEARCH_HELPERS = ('gpt-6-luna', 'gpt-5.6-luna', 'gpt-5.5',
                  'gemini-3.8-flash-low', 'gemini-3.1-flash-lite',
                  'gemini-3.5-flash-lite', 'gemini-3-flash')


def text_content(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return '\n'.join(b.get('text', '') for b in content
                         if isinstance(b, dict) and b.get('type') == 'text'
                         and isinstance(b.get('text'), str))
    return ''


def desktop_search_request(request):
    """Recognize the SDK's separate search turn, never an ordinary chat/tool turn."""
    tools = request.get('tools')
    if not isinstance(tools, list) or not tools or not all(
            isinstance(t, dict) and t.get('type') in SEARCH_TYPES
            and t.get('name') == 'web_search' for t in tools):
        return False
    choice = request.get('tool_choice')
    if choice == 'none' or isinstance(choice, dict) and choice.get('type') == 'none':
        return False
    if isinstance(choice, dict) and choice.get('type') == 'tool' and choice.get('name') != 'web_search':
        return False
    if SEARCH_SYSTEM in text_content(request.get('system')):
        return True
    messages = request.get('messages')
    return (isinstance(messages, list) and len(messages) == 1
            and isinstance(messages[0], dict) and messages[0].get('role') == 'user'
            and text_content(messages[0].get('content')).startswith(SEARCH_QUERY))


def google_search_models():
    path = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / 'assets' / 'cliproxy-models.json'
    try:
        catalog = json.loads(path.read_text('utf-8-sig'))
        return {m['id'] for m in catalog.get('antigravity', []) if isinstance(m, dict)
                and isinstance(m.get('id'), str) and m.get('supports_web_search') is True}
    except (OSError, ValueError, AttributeError):
        return set()


def needs_search_helper(request, actual_model, google_capabilities):
    return (desktop_search_request(request)
            and not actual_model.startswith(('gpt-', 'claude-oauth/'))
            and actual_model not in google_capabilities)
