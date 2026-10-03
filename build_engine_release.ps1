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
if ($LASTEXITCODE -ne 0) { throw 'Could not identify source commit.' }
$status = @(& git -c "safe.directory=$safe" -C $repository status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0 -or $status.Count -ne 0) { throw 'Use a clean committed checkout.' }
$version = (Get-Content -Raw -LiteralPath (Join-Path $repository 'VERSION')).Trim()
$python = (Resolve-Path -LiteralPath $BuildPython).Path
$output = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $output) { throw 'Choose a new output directory.' }
New-Item -ItemType Directory -Path $output | Out-Null
$work = Join-Path $output 'work'
$staging = Join-Path $output 'staging'
New-Item -ItemType Directory -Path $staging | Out-Null
& $python -m pip freeze | Set-Content -LiteralPath (Join-Path $output 'environment.txt')
if ($LASTEXITCODE -ne 0) { throw 'Could not record build dependencies.' }
$environment = & $python -c "import json,sys,site; print(json.dumps(dict(version=sys.version,base=sys.base_prefix,site=site.getsitepackages())))" | ConvertFrom-Json
Push-Location $repository
try {
    & $python -m PyInstaller --noconfirm --clean --onefile --console --name E7ADBShopRefresh `
        --distpath $staging --workpath $work --specpath $output .\E7ADBShopRefresh.py *> (Join-Path $output 'compiler.log')
    if ($LASTEXITCODE -ne 0) { throw 'Engine build failed; inspect compiler.log.' }
}
finally { Pop-Location }
$sourceFiles = @('E7ADBShopRefresh.py', 'e7_shop_navigation.py', 'prepare_navigation_references.py', 'test_e7_shop_navigation.py', 'test_e7_live_engine.py', 'engine-build-requirements.txt', 'build_engine_release.ps1', 'ENGINE.md', 'VERSION', 'LICENSE')
foreach ($name in $sourceFiles) { Copy-Item -LiteralPath (Join-Path $repository $name) -Destination (Join-Path $staging $name) }
Copy-Item -LiteralPath (Join-Path $repository 'ENGINE.md') -Destination (Join-Path $staging 'README.md')
Copy-Item -LiteralPath (Join-Path $repository 'release/SETUP.md') -Destination (Join-Path $staging 'SETUP.md')
foreach ($name in @('CREDITS.txt', 'UPSTREAM.md')) {
    Copy-Item -LiteralPath (Join-Path $repository $name) -Destination (Join-Path $staging $name)
}
$licences = Join-Path $staging 'third-party-licenses'
New-Item -ItemType Directory -Path $licences | Out-Null
foreach ($site in $environment.site) {
    if (-not (Test-Path -LiteralPath $site)) { continue }
    Get-ChildItem -LiteralPath $site -File -Recurse | Where-Object { $_.Name -match '^(LICENSE|LICENCE|COPYING|NOTICE)' } | ForEach-Object {
        $relative = [IO.Path]::GetRelativePath($site, $_.FullName)
        $target = Join-Path $licences $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $target
    }
}
$pythonLicence = Join-Path $environment.base 'LICENSE.txt'
if (Test-Path -LiteralPath $pythonLicence) { Copy-Item -LiteralPath $pythonLicence -Destination (Join-Path $licences 'Python-LICENSE.txt') }
$tclDirectory = Join-Path $environment.base 'tcl'
if (Test-Path -LiteralPath $tclDirectory) {
    Get-ChildItem -LiteralPath $tclDirectory -Recurse -File -Filter 'license.terms' | ForEach-Object {
        $target = Join-Path $licences (Join-Path 'tcl-tk' ([IO.Path]::GetRelativePath($tclDirectory, $_.FullName)))
        New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $target
    }
}
$files = [ordered]@{}
Get-ChildItem -LiteralPath $staging -Recurse -File | ForEach-Object {
    $member = [IO.Path]::GetRelativePath($staging, $_.FullName).Replace('\', '/')
    $files[$member] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
}
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = Join-Path $output "E7LiveEngine-$version.zip"
$zip = [IO.Compression.ZipFile]::Open($archive, [IO.Compression.ZipArchiveMode]::Create)
try {
    foreach ($member in $files.Keys) {
        [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, (Join-Path $staging $member), $member, [IO.Compression.CompressionLevel]::Optimal) | Out-Null
    }
}
finally { $zip.Dispose() }
$manifest = [ordered]@{
    candidate_commit=$commit.Trim(); version=$version; created_utc=[DateTime]::UtcNow.ToString('o')
    python=$environment.version; dependencies=(Get-Content -LiteralPath (Join-Path $output 'environment.txt'))
    engine_sha256=$files['E7ADBShopRefresh.exe']; files=$files
    archive=[ordered]@{name=[IO.Path]::GetFileName($archive); sha256=(Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant(); bytes=(Get-Item -LiteralPath $archive).Length}
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $output 'build-manifest.json') -Encoding utf8
Write-Output "Engine candidate: $archive"
Write-Output "SHA-256: $($manifest.archive.sha256)"
