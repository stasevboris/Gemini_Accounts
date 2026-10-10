"""TokenHarbor routing metadata and protected, per-installation credentials."""
MODEL = 'claude-haiku-5.5:free'
HOST = 'tokenharbor.ai'


def is_model(model):
    return model == MODEL


def read_key(controller):
    from backend import dpapi, AccountError
    try:
        return dpapi((controller.data_dir / 'tokenharbor-key.dpapi').read_bytes(), decrypt=True).decode('utf-8')
    except (OSError, ValueError, UnicodeError, AccountError):
        return None


def save_key(controller, key):
    from backend import atomic_write, dpapi, AccountError
    key = key.strip()
    path = controller.data_dir / 'tokenharbor-key.dpapi'
    if not key:
        path.unlink(missing_ok=True)
        return
    if any(character.isspace() for character in key):
        raise AccountError('The TokenHarbor key must not contain spaces or line breaks.')
    atomic_write(path, dpapi(key.encode('utf-8')))
