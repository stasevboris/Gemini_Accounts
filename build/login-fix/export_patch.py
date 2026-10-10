import difflib
import hashlib
import json
import zipfile
from pathlib import Path

work = Path(__file__).resolve().parent
root = work.parents[1]
metadata = json.loads((work / 'source-manifest.json').read_text('utf-8'))
source = Path(metadata['source'])
dest = root / 'native-patches'
dest.mkdir(exist_ok=True)
paths = ('internal/api/handlers/management/auth_files_oauth_callback.go',
    'internal/api/handlers/management/auth_files_provider_oauth.go',
    'internal/api/handlers/management/oauth_callback_port_test.go')
patch = []
with zipfile.ZipFile(work / 'CLIProxyAPI-v8.0.16-source.zip') as z:
    prefix = 'CLIProxyAPI-' + metadata['commit'] + '/'
    for name in paths:
        try:
            original = z.read(prefix + name).decode('utf-8')
            old_name = 'a/' + name
        except KeyError:
            original = ''
            old_name = '/dev/null'
        changed = (source / name).read_text('utf-8')
        patch += difflib.unified_diff(original.splitlines(keepends=True),
            changed.splitlines(keepends=True), fromfile=old_name, tofile='b/' + name)
patch_file = dest / 'callback-port.patch'
patch_file.write_text(''.join(patch), 'utf-8', newline='\n')
with (work / 'cli-proxy-api.exe').open('rb') as f:
    binary_sha = hashlib.file_digest(f, 'sha256').hexdigest()
manifest = {**metadata, 'source': 'build/login-fix/source/CLIProxyAPI-' + metadata['commit'],
    'version': '8.0.16+callbackfix1', 'binary': 'build/login-fix/cli-proxy-api.exe',
    'binary_sha256': binary_sha, 'patch_sha256': hashlib.sha256(patch_file.read_bytes()).hexdigest()}
(dest / 'manifest.json').write_text(json.dumps(manifest, indent=2), 'utf-8')
payload = root / 'build/payload'
(payload / 'native-build.json').write_text(json.dumps(manifest, indent=2), 'utf-8')
print('Patch exported; binary SHA256:', binary_sha)
