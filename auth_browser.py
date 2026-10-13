"""Open account authorization in a normal Firefox tab."""
import os
import shutil
import subprocess
import urllib.parse
from pathlib import Path
from backend import AccountError


def find_firefox():
    candidates = []
    if os.name == 'nt':
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for flags in (winreg.KEY_READ | winreg.KEY_WOW64_64KEY, winreg.KEY_READ | winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(hive, r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\firefox.exe', 0, flags) as key:
                        value, _ = winreg.QueryValueEx(key, None)
                        if isinstance(value, str):
                            candidates.append(Path(value.strip('"')))
                except OSError:
                    pass
        for root in (os.environ.get('PROGRAMFILES'), os.environ.get('PROGRAMFILES(X86)'), os.environ.get('LOCALAPPDATA')):
            if root:
                candidates.append(Path(root) / 'Mozilla Firefox' / 'firefox.exe')
    found = shutil.which('firefox')
    if found:
        candidates.append(Path(found))
    candidates.append(Path('/Applications/Firefox.app/Contents/MacOS/firefox'))
    for path in candidates:
        if path.is_file():
            return path
    raise AccountError('Firefox was not found. Install Firefox to open account authorization.')


def open_authorization_tab(url, provider='chatgpt'):
    parts = urllib.parse.urlsplit(url)
    hosts = {'chatgpt': 'auth.openai.com', 'claude': 'claude.ai'}
    if (provider not in hosts or parts.scheme != 'https' or parts.hostname != hosts[provider]
            or parts.username or parts.password or (provider == 'claude' and parts.path != '/oauth/authorize')):
        raise AccountError('The gateway did not provide a safe account sign-in page.')
    try:
        return subprocess.Popen([str(find_firefox()), '-new-tab', url], close_fds=True)
    except OSError as error:
        raise AccountError('Could not open the authorization tab in Firefox.') from error
