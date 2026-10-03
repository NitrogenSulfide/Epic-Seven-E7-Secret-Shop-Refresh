[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string] $BuildPython,
    [Parameter(Mandatory=$true)][string] $OutputDirectory
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repository = $PSScriptRoot
$safe = $repository.Replace('\', '/')
$commit = & git -c "safe.directory=$safe" -C $repository rev-parse HEAD
if ($LASTEXITCODE -ne 0) { throw 'Could not identify candidate commit.' }
$status = @(& git -c "safe.directory=$safe" -C $repository status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0 -or $status.Count -ne 0) { throw 'Use a clean committed checkout.' }
$version = (Get-Content -Raw -LiteralPath (Join-Path $repository 'VERSION')).Trim()
$python = (Resolve-Path -LiteralPath $BuildPython).Path
$output = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $output) { throw 'Choose a new candidate output directory.' }
New-Item -ItemType Directory -Path $output | Out-Null
& (Join-Path $repository 'build_release.ps1') -OutputDirectory (Join-Path $output 'gui-build')
& (Join-Path $repository 'build_engine_release.ps1') -BuildPython $python -OutputDirectory (Join-Path $output 'engine-build')
# The component ZIPs are private build evidence. Players receive one assembled ZIP.
$staging = Join-Path $output 'player-staging'
New-Item -ItemType Directory -Path $staging | Out-Null
Copy-Item -Path (Join-Path $output 'gui-build/staging/*') -Destination $staging -Recurse
$runtime = Join-Path $staging 'runtime'
New-Item -ItemType Directory -Path $runtime | Out-Null
Copy-Item -Path (Join-Path $output 'engine-build/staging/*') -Destination $runtime -Recurse
$adbAssets = @(& git -c "safe.directory=$safe" -C $repository ls-files -- adb-assets)
if ($LASTEXITCODE -ne 0 -or $adbAssets.Count -eq 0) { throw 'Tracked upstream ADB tools/templates are missing.' }
foreach ($asset in $adbAssets) {
    $target = Join-Path $runtime $asset
    New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $repository $asset) -Destination $target
}
# Portable generated configuration, never copied from an installed runtime.
"[engine]`ndirectory = runtime`n" | Set-Content -LiteralPath (Join-Path $staging 'engine-location.ini') -Encoding utf8
Copy-Item -LiteralPath (Join-Path $repository 'release/SETUP.md') -Destination (Join-Path $staging 'START-HERE.md')
$playerFiles = [ordered]@{}
Get-ChildItem -LiteralPath $staging -Recurse -File | ForEach-Object {
    $member = [IO.Path]::GetRelativePath($staging, $_.FullName).Replace('\', '/')
    $playerFiles[$member] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
}
$player = Join-Path $output "E7ShopRefresh-$version.zip"
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [IO.Compression.ZipFile]::Open($player, [IO.Compression.ZipArchiveMode]::Create)
try {
    foreach ($member in $playerFiles.Keys) {
        [IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $zip, (Join-Path $staging $member), $member,
            [IO.Compression.CompressionLevel]::Optimal) | Out-Null
    }
}
finally { $zip.Dispose() }
$source = Join-Path $output "E7Source-$version.zip"
& git -c "safe.directory=$safe" -C $repository archive --format=zip "--output=$source" $commit.Trim()
if ($LASTEXITCODE -ne 0) { throw 'Source archive failed.' }
$packages = @($player, $source) | ForEach-Object {
    [ordered]@{
        name = [IO.Path]::GetFileName($_)
        bytes = (Get-Item -LiteralPath $_).Length
        sha256 = (Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
$packages | ForEach-Object { "$($_.sha256)  $($_.name)" } |
    Set-Content -LiteralPath (Join-Path $output 'SHA256SUMS.txt') -Encoding utf8
Copy-Item -LiteralPath (Join-Path $repository 'release/SETUP.md') -Destination (Join-Path $output 'START-HERE.md')
[ordered]@{
    candidate_commit = $commit.Trim()
    version = $version
    maintainer = 'NitrogenSulfide (Blue Natto)'
    created_utc = [DateTime]::UtcNow.ToString('o')
    packages = $packages
    player_files = $playerFiles
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $output 'release-assets.json') -Encoding utf8
Write-Output "Release assets: $output"
