"""Compatibility for the Claude Desktop/Agent SDK identity banner."""

SDK_BANNER = "You are a Claude agent, built on Anthropic's Claude Agent SDK."


def strip_sdk_banner(request):
    """Remove only the SDK's leading identity sentence from system text.

    Antigravity returns a generic 429 for this banner, including on accounts
    with available Claude quota. User messages, tools and task instructions
    must remain intact. Return whether the request was changed.
    """
    def clean(text):
        if not isinstance(text, str):
            return text
        if text.strip() == SDK_BANNER:
            return ''
        if text.startswith(SDK_BANNER + '\r\n'):
            return text[len(SDK_BANNER) + 2:]
        if text.startswith(SDK_BANNER + '\n'):
            return text[len(SDK_BANNER) + 1:]
        return text

    system = request.get('system')
    if isinstance(system, str):
        result = clean(system)
        if result == system:
            return False
        if result:
            request['system'] = result
        else:
            request.pop('system')
        return True
    if not isinstance(system, list):
        return False
    changed = False
    result = []
    for block in system:
        if isinstance(block, dict) and block.get('type') == 'text':
            text = clean(block.get('text'))
            if text != block.get('text'):
                changed = True
                if not text:
                    continue
                block = dict(block, text=text)
        result.append(block)
    if changed:
        if result:
            request['system'] = result
        else:
            request.pop('system')
    return changed
