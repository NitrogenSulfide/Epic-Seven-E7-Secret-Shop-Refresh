$ErrorActionPreference = "Stop"

$script = Join-Path $PSScriptRoot "e7_shop_refresh_gui.py"
if (-not (Test-Path -LiteralPath $script)) {
    throw "Missing GUI script: $script"
}

py -3 $script
