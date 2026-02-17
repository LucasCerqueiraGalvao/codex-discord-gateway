param(
    [string]$TaskName = "CodexDiscordGateway"
)

$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

$projectRoot = (Resolve-Path ".").Path
$venvPythonw = Join-Path $projectRoot ".venv\Scripts\pythonw.exe"
$pythonwExe = if (Test-Path $venvPythonw) { $venvPythonw } else { "pythonw.exe" }

$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$action = New-ScheduledTaskAction -Execute $pythonwExe -Argument "-m src.tray_app" -WorkingDirectory $projectRoot
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Trigger $trigger `
    -Action $action `
    -Settings $settings `
    -Principal $principal `
    -Description "Starts Codex Discord Gateway tray app at user logon." `
    -Force | Out-Null

Start-ScheduledTask -TaskName $TaskName
Write-Host "Task '$TaskName' installed and started."
