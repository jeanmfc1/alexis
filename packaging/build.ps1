<#
  Build ALEXIS.exe (one-folder) with PyInstaller.

  Run from anywhere in PowerShell:
      .\packaging\build.ps1

  VERSIONED OUTPUT (builds never overwrite each other):
      C:\ALEXIS_build\dist\<yyyyMMdd-HHmmss>[_<gitsha>]\ALEXIS\ALEXIS.exe
  A 'latest' junction always points at the newest build (stable path for testing):
      C:\ALEXIS_build\dist\latest\ALEXIS\ALEXIS.exe
  Every build appends a line to:
      C:\ALEXIS_build\dist\builds.log

  Old builds are KEPT (that's the point) -- prune C:\ALEXIS_build\dist\* manually
  when disk gets tight. The work/ cache is shared and reused for speed.
#>

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..").Path
# REQUIRED, not cosmetic: the spec's collect_submodules('pipelines'|'app'|...)
# must IMPORT those packages at build time, which needs the repo on the path.
# Building from elsewhere silently ships an exe with NO pipelines package.
Set-Location $Root

$DistRoot = "C:\ALEXIS_build\dist"
$Work     = "C:\ALEXIS_build\work"     # shared scratch cache (safe to reuse; speeds rebuilds)

# --- app version: single source of truth is core/version.py (bump it to release) ---
$AppVer = (py -3.11 -c "from core.version import __version__ as v; print(v)" 2>$null)
if ([string]::IsNullOrWhiteSpace($AppVer)) { $AppVer = "0.0.0" }

# --- versioned output dir: app version + timestamp + short git sha (never overwrite) ---
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Sha   = $null
try { $Sha = (git rev-parse --short HEAD 2>$null) } catch { $Sha = $null }
if ([string]::IsNullOrWhiteSpace($Sha)) { $Sha = $null }
$Version = if ($Sha) { "v${AppVer}_${Stamp}_${Sha}" } else { "v${AppVer}_${Stamp}" }
$Dist    = Join-Path $DistRoot $Version
$ExePath = Join-Path $Dist "ALEXIS\ALEXIS.exe"

Write-Host "[build] repo    : $Root"
Write-Host "[build] app ver : $AppVer"
Write-Host "[build] version : $Version"
Write-Host "[build] dist    : $Dist"
Write-Host "[build] python  : $(py -3.11 -c 'import sys; print(sys.version.split()[0])')"

# Confirm the sklearn pin matches the pickled models BEFORE building.
py -3.11 -c "import sklearn; assert sklearn.__version__.startswith('1.6'), 'sklearn must be 1.6.x to match the models, got '+sklearn.__version__; print('[build] sklearn', sklearn.__version__)"
if ($LASTEXITCODE -ne 0) { throw "sklearn version check failed (need 1.6.x; do not build with the WSL .venv)" }

# Guard: every bundled .py must COMPILE under this Python (3.11). A file written
# with 3.12-only syntax (e.g. nested same-quote f-strings, valid in the WSL 3.12
# .venv) cannot be compiled by PyInstaller under 3.11 -- it is SILENTLY dropped as
# an "invalid module" and the job fails at runtime with ModuleNotFoundError. Fail
# loudly here instead of shipping a hollow bundle.
Write-Host "[build] compile check (Python 3.11)..."
py -3.11 -m compileall -q app core pipelines analytics classifiers collectors policy utils storage config tools
if ($LASTEXITCODE -ne 0) { throw "compile check FAILED: a bundled .py will not compile under Python 3.11 (see above) -- fix it or it gets dropped from the exe" }

py -3.11 -m PyInstaller packaging\alexis.spec --noconfirm --distpath $Dist --workpath $Work
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed (exit $LASTEXITCODE)" }

# --- repoint 'latest' at this build (junction; no admin needed; only the link is removed) ---
$Latest = Join-Path $DistRoot "latest"
try {
    if (Test-Path $Latest) { cmd /c rmdir "$Latest" | Out-Null }   # removes the junction link only, never the target
    cmd /c mklink /J "$Latest" "$Dist" | Out-Null
    Write-Host "[build] latest  -> $Latest  (junction -> $Version)"
} catch {
    Write-Host "[build] WARN: could not update 'latest' junction: $_"
}

# --- stamp the app version into the build, and record a manifest line ---
"$AppVer" | Set-Content -Path (Join-Path $Dist "ALEXIS\VERSION.txt") -Encoding utf8
"$Stamp`t$AppVer`t$Version`t$ExePath" | Add-Content -Path (Join-Path $DistRoot "builds.log") -Encoding utf8

Write-Host ""
Write-Host "[build] app ver: $AppVer"
Write-Host "[build] done   -> $ExePath"
Write-Host "[build] latest -> $(Join-Path $Latest 'ALEXIS\ALEXIS.exe')"
Write-Host "[build] smoke test:  & '$ExePath' --headless --port 18099"
