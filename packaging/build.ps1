<#
  Build ALEXIS.exe (one-folder) with PyInstaller.

  Run from the repo root in PowerShell:
      .\packaging\build.ps1

  Output: C:\ALEXIS_build\dist\ALEXIS\ALEXIS.exe
  Build artifacts go to a LOCAL drive (not the WSL/UNC source) for speed.
#>

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $Root

$Dist = "C:\ALEXIS_build\dist"
$Work = "C:\ALEXIS_build\work"

Write-Host "[build] repo   : $Root"
Write-Host "[build] dist   : $Dist"
Write-Host "[build] python : $(py -3.11 -c 'import sys; print(sys.version.split()[0])')"

# Confirm the sklearn pin matches the pickled models before building.
py -3.11 -c "import sklearn; assert sklearn.__version__.startswith('1.6'), 'sklearn must be 1.6.x to match the models, got '+sklearn.__version__; print('[build] sklearn', sklearn.__version__)"

py -3.11 -m PyInstaller packaging\alexis.spec --noconfirm --distpath $Dist --workpath $Work

Write-Host ""
Write-Host "[build] done -> $Dist\ALEXIS\ALEXIS.exe"
Write-Host "[build] smoke test:  & '$Dist\ALEXIS\ALEXIS.exe' --headless --port 18099"
