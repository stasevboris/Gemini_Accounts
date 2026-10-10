param([string]$Python='python')
$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
$build = Join-Path $PSScriptRoot 'build'
$payload = Join-Path $build 'payload'
$icon = Join-Path $PSScriptRoot 'app.ico'
New-Item -ItemType Directory -Force -Path $payload | Out-Null
& $Python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {throw 'Dependency installation failed'}
# Qt uses the Windows ICU API. Tools such as Poppler can expose incompatible
# ICU DLLs on PATH; do not let the packager substitute them for system DLLs.
$qtBuildOriginalPath = $env:PATH
try {
    $env:PATH = (Split-Path (Get-Command $Python).Source) + ';' + (Join-Path $env:SystemRoot 'System32') + ';' + $env:SystemRoot
    & $Python -m PyInstaller --clean --noconfirm --onefile --windowed --name GeminiAccounts --icon $icon --add-data ($icon+';.') --collect-all tzdata --distpath $payload --workpath (Join-Path $build 'app') --specpath $build app.py
} finally {
    $env:PATH = $qtBuildOriginalPath
}
if ($LASTEXITCODE -ne 0) {throw 'Manager build failed'}
& $Python -m PyInstaller --noconfirm --onefile --windowed --name GeminiQuotaQueue --collect-all tzdata --distpath $payload --workpath (Join-Path $build 'queue') --specpath $build quota_queue.py
if ($LASTEXITCODE -ne 0) {throw 'Queue build failed'}
& $Python -m PyInstaller --noconfirm --onefile --name GeminiAccounts-CLI --collect-all tzdata --distpath dist --workpath (Join-Path $build 'console') --specpath $build console.py
if ($LASTEXITCODE -ne 0) {throw 'Terminal build failed'}
Compress-Archive -LiteralPath 'dist/GeminiAccounts-CLI.exe','CLI.md','LICENSE','THIRD_PARTY.md' -DestinationPath 'dist/GeminiAccounts-CLI-windows-x64.zip' -Force
$archive=Join-Path $build 'CLIProxyAPI_8.0.16_windows_amd64.zip'
if (-not (Test-Path -LiteralPath $archive)) {
    Invoke-WebRequest 'https://github.com/router-for-me/CLIProxyAPI/releases/download/v8.0.16/CLIProxyAPI_8.0.16_windows_amd64.zip' -OutFile $archive
}
$expected='e0d999703c9af70067b15bf50e6521e76392da604d1543541361e6891c676c43'
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) {throw 'CLIProxyAPI checksum mismatch'}
$upstream = Join-Path $build 'upstream'
Expand-Archive -LiteralPath $archive -DestinationPath $upstream -Force
$nativeManifest=Join-Path $PSScriptRoot 'native-patches/manifest.json'
if (Test-Path -LiteralPath $nativeManifest) {
    $nativeBuild=Get-Content -LiteralPath $nativeManifest -Raw | ConvertFrom-Json
    $nativePatched=Join-Path $PSScriptRoot $nativeBuild.binary
    if (-not (Test-Path -LiteralPath $nativePatched)) { throw 'Build the login fix with native-patches/build.ps1 before packaging' }
    if ((Get-FileHash -LiteralPath $nativePatched -Algorithm SHA256).Hash.ToLowerInvariant() -ne $nativeBuild.binary_sha256) { throw 'Patched native service checksum mismatch' }
    Copy-Item -LiteralPath $nativePatched -Destination (Join-Path $payload 'cli-proxy-api.exe') -Force
    Copy-Item -LiteralPath $nativeManifest -Destination (Join-Path $payload 'native-build.json') -Force
} else {
    Copy-Item -LiteralPath (Join-Path $upstream 'cli-proxy-api.exe') -Destination $payload -Force
}
Copy-Item -LiteralPath (Join-Path $upstream 'LICENSE') -Destination (Join-Path $payload 'CLIProxyAPI-LICENSE.txt') -Force
Copy-Item -LiteralPath 'start-proxy.ps1' -Destination $payload -Force
& $Python -m PyInstaller --noconfirm --onefile --windowed --name GeminiAccounts-Setup --icon $icon --add-data ($payload+';payload') --distpath dist --workpath (Join-Path $build 'installer') --specpath $build installer.py
if ($LASTEXITCODE -ne 0) {throw 'Installer build failed'}
$sum=(Get-FileHash 'dist/GeminiAccounts-Setup.exe' -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'dist/SHA256SUMS.txt'),$sum+'  GeminiAccounts-Setup.exe'+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
Write-Output 'Release files are in dist/'
