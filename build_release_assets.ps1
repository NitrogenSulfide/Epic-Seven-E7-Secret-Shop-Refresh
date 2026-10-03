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
$gui = Join-Path $output "E7ShopRefreshGUI-$version.zip"
$engine = Join-Path $output "E7LiveEngine-$version.zip"
Copy-Item -LiteralPath (Join-Path $output "gui-build\E7ShopRefreshGUI-$version.zip") -Destination $gui
Copy-Item -LiteralPath (Join-Path $output "engine-build\E7LiveEngine-$version.zip") -Destination $engine
$source = Join-Path $output "E7Source-$version.zip"
& git -c "safe.directory=$safe" -C $repository archive --format=zip "--output=$source" $commit.Trim()
if ($LASTEXITCODE -ne 0) { throw 'Source archive failed.' }
$packages = @($gui, $engine, $source) | ForEach-Object {
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
    created_utc = [DateTime]::UtcNow.ToString('o')
    packages = $packages
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $output 'release-assets.json') -Encoding utf8
Write-Output "Release assets: $output"
