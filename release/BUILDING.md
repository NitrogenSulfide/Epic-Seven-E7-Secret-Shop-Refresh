# Rebuild the E7 GUI launcher

The Python modules are supplied as executable source and need no compilation.
The EXE launches the adjacent GUI through Python's Windows launcher. It does not
embed Python or the engine. Keep all Python modules and artwork beside it.

From an extracted package on Windows, use the .NET Framework C# compiler if
available. Choose a new output directory to preserve the supplied launcher:

```powershell
$launcherBuild = Join-Path $PWD 'launcher-rebuild'
if (Test-Path -LiteralPath $launcherBuild) { throw 'Choose a new build directory.' }
New-Item -ItemType Directory -Path $launcherBuild | Out-Null
& "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe" `
  /nologo /target:winexe /reference:System.Windows.Forms.dll `
  /win32icon:e7_gui_assets\shopkeeper-v2.ico `
  "/out:$launcherBuild\E7 Secret Shop Refresh.exe" .\E7ShopLauncher.cs
if ($LASTEXITCODE -ne 0) { throw 'Launcher compilation failed.' }
```

To use the rebuilt EXE, stage a separate copy of the package with that EXE beside
the Python modules. Do not overwrite the reviewed candidate or retain its old
hash/verdict after changing it. Check launcher prerequisites without starting
the GUI using `--verify`; this check does not establish runtime correctness.

The maintained source checkout contains `build_release.ps1`, the version file,
release documentation and fixture tests. Its builder requires a clean exact
commit, compiles the launcher, packages an explicit file list, and records hashes
in an adjacent private build manifest. It never bundles a personal engine/config.
