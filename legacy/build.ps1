param(
    [ValidateSet('win-x64', 'win-arm64')][string]$Runtime = 'win-x64',
    [string]$DotnetPath = 'dotnet',
    [switch]$RunUiSmoke
)
$ErrorActionPreference = 'Stop'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$env:DOTNET_NOLOGO = '1'
$projectRoot = $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    $version = (& $DotnetPath --version)
    if ($LASTEXITCODE -ne 0 -or $version -notmatch '^10\.') {
        throw 'Install the .NET 10 SDK (not only the runtime), then run build.ps1 again.'
    }
    & $DotnetPath run --project 'tests/PixivBatchBookmark.Tests' -c Release
    if ($LASTEXITCODE -ne 0) { throw 'Offline tests failed. Publishing cancelled.' }
    & $DotnetPath build 'PixivBatchBookmark.sln' -c Release
    if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
    if ($RunUiSmoke) {
        & $DotnetPath run --project 'tests/PixivBatchBookmark.UiSmoke' -c Release
        if ($LASTEXITCODE -ne 0) { throw 'UI smoke test failed.' }
    }
    $publishPath = Join-Path $projectRoot ('dist/' + $Runtime)
    & $DotnetPath publish 'src/PixivBatchBookmark.Windows/PixivBatchBookmark.Windows.csproj' -c Release -r $Runtime --self-contained true -p:PublishSingleFile=false -p:DebugType=None -p:DebugSymbols=false -o $publishPath
    if ($LASTEXITCODE -ne 0) { throw 'Publish failed.' }
    Copy-Item -LiteralPath (Join-Path $projectRoot 'README.md') -Destination $publishPath
    Copy-Item -LiteralPath (Join-Path $projectRoot 'THIRD_PARTY_NOTICES.md') -Destination $publishPath
    Copy-Item -LiteralPath (Join-Path $projectRoot 'licenses') -Destination $publishPath -Recurse -Force
    $zipPath = Join-Path $projectRoot ('dist/PixivBatchBookmark_Windows_v1.0.4_' + $Runtime + '.zip')
    Compress-Archive -Path (Join-Path $publishPath '*') -DestinationPath $zipPath -Force
    Write-Host ('Runnable EXE: ' + (Join-Path $publishPath 'PixivBatchBookmark.exe'))
    Write-Host ('Portable ZIP: ' + $zipPath)
    Get-FileHash -LiteralPath $zipPath -Algorithm SHA256
} finally { Pop-Location }
