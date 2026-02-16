$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

$venvPython = ".\.venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    & $venvPython -m src.bot
} else {
    python -m src.bot
}
