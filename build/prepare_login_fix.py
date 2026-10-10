import concurrent.futures
import hashlib
import json
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

root = Path(__file__).resolve().parents[1]
work = root / 'build/login-fix'
work.mkdir(exist_ok=True)

def fetch_json(url):
    return json.load(urllib.request.urlopen(url, timeout=40))

def download(url, target, expected=None):
    if not target.exists():
        with urllib.request.urlopen(url, timeout=60) as r, target.open('wb') as out:
            while chunk := r.read(1024 * 1024):
                out.write(chunk)
    with target.open('rb') as f:
        actual = hashlib.file_digest(f, 'sha256').hexdigest()
    if expected and actual != expected:
        raise RuntimeError('Download checksum mismatch: ' + target.name)
    return actual

versions = fetch_json('https://go.dev/dl/?mode=json&include=all')
version = next(v for v in versions if v['stable'] and v['version'].startswith('go1.26.'))
toolchain = next(f for f in version['files'] if f['os'] == 'windows' and f['arch'] == 'amd64' and f['kind'] == 'archive')
commit = fetch_json('https://api.github.com/repos/router-for-me/CLIProxyAPI/commits/v8.0.16')['sha']
go_zip = work / toolchain['filename']
source_zip = work / 'CLIProxyAPI-v8.0.16-source.zip'
with concurrent.futures.ThreadPoolExecutor() as pool:
    one = pool.submit(download, 'https://go.dev/dl/' + toolchain['filename'], go_zip, toolchain['sha256'])
    two = pool.submit(download, 'https://codeload.github.com/router-for-me/CLIProxyAPI/zip/' + commit, source_zip)
    go_sha, source_sha = one.result(), two.result()
with zipfile.ZipFile(go_zip) as z:
    z.extractall(work / 'toolchain')
with zipfile.ZipFile(source_zip) as z:
    z.extractall(work / 'source')
source = work / 'source' / ('CLIProxyAPI-' + commit)
manifest = dict(upstream_version='8.0.16', commit=commit, source=str(source),
    source_sha256=source_sha, go_version=version['version'], go_sha256=go_sha)
(work / 'source-manifest.json').write_text(json.dumps(manifest, indent=2), 'utf-8')
print(json.dumps(manifest))

# Keep the complete local rollback copy, including the currently installed binary.
manager = Path.home() / 'AppData/Local/GeminiAccounts'
proxy = Path.home() / 'AppData/Local/ClaudeGemini'
backup = root / 'backups' / ('GeminiAccounts-before-login-fix-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.zip')
with zipfile.ZipFile(backup, 'w', zipfile.ZIP_DEFLATED) as z:
    for folder, prefix in ((manager, 'installed/GeminiAccounts'), (proxy, 'installed/ClaudeGemini')):
        for path in folder.rglob('*'):
            if path.is_file():
                z.write(path, prefix + '/' + path.relative_to(folder).as_posix())
    for name in ('app.py', 'backend.py', 'runtime.py', 'installer.py', 'build-release.ps1', 'locales.py'):
        z.write(root / name, 'source/' + name)
with zipfile.ZipFile(backup) as z:
    assert z.testzip() is None
(work / 'backup-path.txt').write_text(str(backup), 'utf-8')
print('Backup verified:', backup)
