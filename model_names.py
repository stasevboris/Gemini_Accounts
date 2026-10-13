"""Concrete upstream model names, retaining version and variant information."""
# Retain historical fallback labels; live routes come from the gateway config.
DEFAULT_ALIASES = {'claude-sonnet-4-5': 'gemini-3.1-pro-low', 'claude-haiku-4-5': 'gemini-3-flash'}


def model_name(model, aliases=None):
    model = (DEFAULT_ALIASES if aliases is None else aliases).get(model, model)
    known = {
        'gemini-pro-agent': '3.1 Pro High',
        'gemini-3-flash-agent': '3.5 Flash High',
        'gemini-3.5-flash-low': '3.5 Flash Medium',
        'gemini-3.5-flash-extra-low': '3.5 Flash Low',
        'gemini-4-argon': '4 Argon',
        'claude-haiku-4-5': 'Haiku 4.5',
        'claude-haiku-5.5:free': 'Haiku 5.5 (TokenHarbor)',
        'claude-sonnet-4-6': 'Sonnet 4.6',
        'claude-opus-4-6-thinking': 'Opus 4.6 Thinking',
        'claude-opus-5-5-high': 'Opus 5.5 High',
        'claude-sonnet-5-5-high': 'Sonnet 5.5 High',
    }
    if model in known:
        return known[model]
    if model.startswith('gemini-'):
        return ' '.join(word.title() for word in model[7:].split('-'))
    # Do not truncate or strip model variants from other providers.
    return model


def reasoning_level(model):
    levels = {"gemini-3-flash-agent": "high", "gemini-3.5-flash-low": "medium", "gemini-3.5-flash-extra-low": "low"}
    return levels.get(model, next((level for level in ("high", "medium", "low") if model.endswith("-" + level)), "medium"))
