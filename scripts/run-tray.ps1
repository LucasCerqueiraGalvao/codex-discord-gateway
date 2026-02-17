$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

$projectRoot = (Resolve-Path ".").Path
$venvPythonw = Join-Path $projectRoot ".venv\Scripts\pythonw.exe"
$pythonwExe = if (Test-Path $venvPythonw) { $venvPythonw } else { "pythonw.exe" }

Start-Process -FilePath $pythonwExe -ArgumentList "-m src.tray_app" -WorkingDirectory $projectRoot -WindowStyle Hidden
Write-Host "Codex tray iniciado em segundo plano."
