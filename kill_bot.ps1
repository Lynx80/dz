# kill_bot.ps1
# Script to terminate existing bot.py processes

$processes = Get-WmiObject Win32_Process -Filter "name = 'python.exe'" | Where-Object { 
    $_.CommandLine -like "*bot.py*" 
}

if ($processes) {
    Write-Host "Found $($processes.Count) bot processes. Terminating..."
    $processes | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Write-Host "Processes terminated."
} else {
    Write-Host "No running bot processes found."
}

if (Test-Path "bot.pid") {
    Remove-Item "bot.pid"
    Write-Host "Removed leftover bot.pid"
}
