[CmdletBinding()]
param(
    [string] $OutputDirectory,
    [Parameter(Mandatory=$true)][string] $BuildPython
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
$python = (Resolve-Path -LiteralPath $BuildPython).Path
& $python -c 'import PIL, tkinter, PyInstaller'
if ($LASTEXITCODE -ne 0) { throw 'The private build environment must include Pillow, Tkinter and PyInstaller.' }
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
    'e7_engine_protocol.py' = 'e7_engine_protocol.py'
    'e7_timing.py' = 'e7_timing.py'
    'e7_history.py' = 'e7_history.py'
    'e7_links.py' = 'e7_links.py'
    'e7_appearance.py' = 'e7_appearance.py'
    'e7_about.py' = 'e7_about.py'
    'e7_setup.py' = 'e7_setup.py'
    'e7_connection.py' = 'e7_connection.py'
    'e7_windows_capture.py' = 'e7_windows_capture.py'
    'e7_native_mouse.py' = 'e7_native_mouse.py'
    'e7_elevation.py' = 'e7_elevation.py'
    'e7_windows_icon.py' = 'e7_windows_icon.py'
    'engine-location.example.ini' = 'engine-location.example.ini'
    'LICENSE' = 'LICENSE'
    'CREDITS.txt' = 'CREDITS.txt'
    'CHANGELOG.txt' = 'CHANGELOG.txt'
    'UPSTREAM.md' = 'UPSTREAM.md'
    'VERSION' = 'VERSION'
    'release/README.md' = 'README.md'
    'release/BUILDING.md' = 'BUILDING.md'
    'release/SETUP.md' = 'SETUP.md'
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
    & $python -m PyInstaller --noconfirm --clean --onefile --windowed --name 'E7 Secret Shop Refresh' `
        --icon (Join-Path $staging 'e7_gui_assets/shopkeeper-v2.ico') --distpath $staging --workpath (Join-Path $output 'work') `
        --specpath $output .\e7_shop_refresh_gui.py *> (Join-Path $output 'compiler.log')
    if ($LASTEXITCODE -ne 0) { throw 'GUI compilation failed; inspect compiler.log.' }
}
finally { Pop-Location }
$files['E7 Secret Shop Refresh.exe'] = [ordered]@{
    source = 'e7_shop_refresh_gui.py and adjacent Python modules + e7_gui_assets/shopkeeper-v2.ico'
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
    build_python = $python
    dependencies = @(& $python -m pip freeze)
    options = '--onefile --windowed; external tracked artwork beside EXE; Python/Tk/Pillow embedded'
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
