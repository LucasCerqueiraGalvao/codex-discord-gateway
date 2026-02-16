$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")
python -m src.bot
