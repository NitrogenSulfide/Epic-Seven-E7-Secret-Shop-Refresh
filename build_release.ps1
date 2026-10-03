[CmdletBinding()]
param(
    [string] $OutputDirectory,
    [string] $CompilerPath = "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repository = $PSScriptRoot
$version = (Get-Content -Raw -LiteralPath (Join-Path $repository 'VERSION')).Trim()
if ($version -notmatch '^\d+\.\d+\.\d+(-rc[1-9]\d*)?$') {
    throw 'VERSION must contain a release version, optionally followed by -rcN.'
}
$safeRepository = $repository.Replace('\', '/')
$candidateCommit = & git -c "safe.directory=$safeRepository" -C $repository rev-parse HEAD
if ($LASTEXITCODE -ne 0) { throw 'Could not identify candidate commit.' }
$worktreeStatus = @(& git -c "safe.directory=$safeRepository" -C $repository status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0 -or $worktreeStatus.Count -ne 0) {
    throw 'Build from a clean committed checkout; preserve/stage unrelated work separately.'
}
$compiler = (Resolve-Path -LiteralPath $CompilerPath).Path
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $repository "dist\candidates\$version"
}
$output = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $output) { throw "Candidate directory already exists: $output" }
New-Item -ItemType Directory -Path $output | Out-Null
$staging = Join-Path $output 'staging'
New-Item -ItemType Directory -Path $staging | Out-Null
$mapping = [ordered]@{
    'e7_shop_refresh_gui.py' = 'e7_shop_refresh_gui.py'
    'e7_process.py' = 'e7_process.py'
    'e7_windows_icon.py' = 'e7_windows_icon.py'
    'launch_e7_shop_refresh_gui.ps1' = 'launch_e7_shop_refresh_gui.ps1'
    'E7 Secret Shop Refresh GUI.cmd' = 'E7 Secret Shop Refresh GUI.cmd'
    'E7ShopLauncher.cs' = 'E7ShopLauncher.cs'
    'engine-location.example.ini' = 'engine-location.example.ini'
    'LICENSE' = 'LICENSE'
    'CREDITS.txt' = 'CREDITS.txt'
    'UPSTREAM.md' = 'UPSTREAM.md'
    'VERSION' = 'VERSION'
    'release/README.md' = 'README.md'
    'release/BUILDING.md' = 'BUILDING.md'
    'ENGINE.md' = 'ENGINE.md'
    'docs/UPSTREAM-README.md' = 'docs/UPSTREAM-README.md'
}
$assets = @(& git -c "safe.directory=$safeRepository" -C $repository ls-files -- e7_gui_assets)
if ($LASTEXITCODE -ne 0 -or $assets.Count -eq 0) { throw 'Tracked GUI artwork/audio is missing.' }
foreach ($asset in $assets) { $mapping[$asset] = $asset }
$files = [ordered]@{}
foreach ($sourceName in $mapping.Keys) {
    $source = Join-Path $repository $sourceName
    $member = $mapping[$sourceName]
    $destination = Join-Path $staging $member
    New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination
    $hash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
    $files[$member] = [ordered]@{ source = $sourceName; sha256 = $hash }
}
$launcher = Join-Path $staging 'E7 Secret Shop Refresh.exe'
Push-Location $staging
try {
    & $compiler /nologo /target:winexe /reference:System.Windows.Forms.dll `
        /win32icon:e7_gui_assets\shopkeeper-v2.ico "/out:$launcher" .\E7ShopLauncher.cs
    if ($LASTEXITCODE -ne 0) { throw 'Launcher compilation failed.' }
}
finally { Pop-Location }
$files['E7 Secret Shop Refresh.exe'] = [ordered]@{
    source = 'E7ShopLauncher.cs + e7_gui_assets/shopkeeper-v2.ico'
    sha256 = (Get-FileHash -LiteralPath $launcher -Algorithm SHA256).Hash.ToLowerInvariant()
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$archivePath = Join-Path $output "E7ShopRefreshGUI-$version.zip"
$zip = [IO.Compression.ZipFile]::Open($archivePath, [IO.Compression.ZipArchiveMode]::Create)
try {
    foreach ($member in $files.Keys) {
        [IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $zip, (Join-Path $staging $member), $member,
            [IO.Compression.CompressionLevel]::Optimal) | Out-Null
    }
}
finally { $zip.Dispose() }
$manifest = [ordered]@{
    version = $version
    candidate_commit = $candidateCommit.Trim()
    created_utc = [DateTime]::UtcNow.ToString('o')
    build_host = 'Windows'
    compiler = [ordered]@{
        path = $compiler
        version = (Get-Item -LiteralPath $compiler).VersionInfo.FileVersion
        sha256 = (Get-FileHash -LiteralPath $compiler -Algorithm SHA256).Hash.ToLowerInvariant()
        options = '/nologo /target:winexe /reference:System.Windows.Forms.dll /win32icon:e7_gui_assets\shopkeeper-v2.ico'
    }
    archive = [ordered]@{
        name = [IO.Path]::GetFileName($archivePath)
        bytes = (Get-Item -LiteralPath $archivePath).Length
        sha256 = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    files = $files
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $output 'build-manifest.json') -Encoding utf8
Write-Output "Candidate commit: $($manifest.candidate_commit)"
Write-Output "Archive: $archivePath"
Write-Output "SHA-256: $($manifest.archive.sha256)"
