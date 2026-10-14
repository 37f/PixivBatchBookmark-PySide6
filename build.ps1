param(
    [string]$PythonPath = '',
    [string]$DotnetPath = 'dotnet',
    [switch]$RunUiSmoke
)
$ErrorActionPreference = 'Stop'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$env:DOTNET_NOLOGO = '1'
Push-Location -LiteralPath $PSScriptRoot
try {
    if ($env:OS -ne 'Windows_NT') { throw 'Build the unified Windows package on Windows x64.' }
    if (!$PythonPath) {
        if (!(Test-Path '.venv/Scripts/python.exe')) {
            & py -3.12 -m venv .venv
            if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 x64 is required.' }
        }
        $PythonPath = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
    }
    & $DotnetPath --version
    if ($LASTEXITCODE -ne 0) { throw '.NET 10 SDK is required to build the original legacy version.' }
    & $PythonPath -m pip install -r requirements-build.txt
    if ($LASTEXITCODE -ne 0) { throw 'Python dependencies failed.' }
    & $PythonPath scripts/prepare_resources.py
    if ($LASTEXITCODE -ne 0) { throw 'Resource preparation failed.' }
    & $PythonPath -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Modern offline tests failed.' }
    Push-Location legacy
    try {
        & $DotnetPath run --project tests/PixivBatchBookmark.Tests -c Release
        if ($LASTEXITCODE -ne 0) { throw 'Legacy offline tests failed.' }
        & $DotnetPath build PixivBatchBookmark.sln -c Release
        if ($LASTEXITCODE -ne 0) { throw 'Legacy build failed.' }
        if ($RunUiSmoke) {
            & $DotnetPath run --project tests/PixivBatchBookmark.UiSmoke -c Release
            if ($LASTEXITCODE -ne 0) { throw 'Legacy UI smoke failed.' }
        }
        if (Test-Path dist/win-x64) { Remove-Item dist/win-x64 -Recurse -Force }
        & $DotnetPath publish src/PixivBatchBookmark.Windows/PixivBatchBookmark.Windows.csproj -c Release -r win-x64 --self-contained true -p:PublishSingleFile=false -p:DebugType=None -p:DebugSymbols=false -o dist/win-x64
        if ($LASTEXITCODE -ne 0) { throw 'Legacy publish failed.' }
    } finally { Pop-Location }
    & $PythonPath -m PyInstaller --noconfirm --clean PixivBatchBookmark.spec
    if ($LASTEXITCODE -ne 0) { throw 'Modern publish failed.' }
    $output = Join-Path $PSScriptRoot 'dist/PixivBatchBookmark'
    $legacyOutput = Join-Path $output 'legacy'
    if (Test-Path $legacyOutput) { Remove-Item $legacyOutput -Recurse -Force }
    Copy-Item legacy/dist/win-x64 -Destination $legacyOutput -Recurse
    Copy-Item legacy/THIRD_PARTY_NOTICES.md -Destination $legacyOutput
    Copy-Item legacy/licenses -Destination $legacyOutput -Recurse
    Copy-Item README.md -Destination $output
    if ($RunUiSmoke) {
        & $PythonPath tests/windows_version_smoke.py
        if ($LASTEXITCODE -ne 0) { throw 'Actual WPF/Qt switching smoke failed.' }
    }
    $version = & $PythonPath -c 'from app_config import VERSION; print(VERSION)'
    $zip = Join-Path $PSScriptRoot "dist/PixivBatchBookmark_Unified_v${version}_win-x64.zip"
    Compress-Archive -Path (Join-Path $output '*') -DestinationPath $zip -Force
    Write-Host "Unified application: $output/PixivBatchBookmark.exe"
    Get-FileHash -LiteralPath $zip -Algorithm SHA256
} finally { Pop-Location }
