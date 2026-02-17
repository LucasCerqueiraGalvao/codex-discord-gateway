$ErrorActionPreference = "Stop"

$targets = Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -in @("python.exe", "pythonw.exe")) -and (
        $_.CommandLine -like "*src.tray_app*" -or $_.CommandLine -like "*src.bot*"
    )
}

if (-not $targets) {
    Write-Host "Nenhum processo do tray/bot encontrado."
    exit 0
}

$targets | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

Write-Host "Processos do tray/bot finalizados."
