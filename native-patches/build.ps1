param([string]$Python='python')
$ErrorActionPreference='Stop'
$taskRoot = Split-Path $PSScriptRoot
Set-Location -LiteralPath $taskRoot
& $Python build/prepare_login_fix.py
if ($LASTEXITCODE -ne 0) { throw 'Native source preparation failed' }
$metadata=Get-Content build/login-fix/source-manifest.json -Raw | ConvertFrom-Json
$goFix=Join-Path $taskRoot 'build/login-fix/toolchain/go/bin/go.exe'
$env:GOTOOLCHAIN='local'
$env:GOCACHE=Join-Path $taskRoot 'build/login-fix/gocache'
$env:GOMODCACHE=Join-Path $taskRoot 'build/login-fix/gomodcache'
Push-Location -LiteralPath $metadata.source
try {
    git apply --ignore-whitespace --ignore-space-change (Join-Path $PSScriptRoot 'callback-port.patch')
    if ($LASTEXITCODE -ne 0) { throw 'Native patch application failed' }
    & $goFix test ./internal/api/handlers/management -run 'Test.*(OAuth|Callback|RequestCodexToken)' -count=1
    if ($LASTEXITCODE -ne 0) { throw 'Native OAuth tests failed' }
    & $goFix build -trimpath -ldflags '-s -w -X main.Version=8.0.16+callbackfix1 -X main.Commit=a2976eb8a303f11b4ea5177bce9f9ff752634dfc -X main.BuildDate=2026-10-10' -o '../../cli-proxy-api.exe' ./cmd/server
    if ($LASTEXITCODE -ne 0) { throw 'Native build failed' }
} finally { Pop-Location }
& $Python build/login-fix/export_patch.py
if ($LASTEXITCODE -ne 0) { throw 'Native manifest generation failed' }
