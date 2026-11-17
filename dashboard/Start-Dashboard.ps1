$ErrorActionPreference = 'Stop'
$dashboardRoot = $PSScriptRoot
$workspaceRoot = Split-Path -Parent $dashboardRoot
$dashboardUrl = 'http://127.0.0.1:8765'
try {
    $dashboardResponse = Invoke-WebRequest -Uri $dashboardUrl -TimeoutSec 2
    if ($dashboardResponse.StatusCode -eq 200 -and $dashboardResponse.Content -match 'Astral') {
        Start-Process $dashboardUrl
        exit 0
    }
} catch { }
$pythonExecutable = (Get-Command python -ErrorAction Stop).Source
$dashboardProcess = Start-Process -FilePath $pythonExecutable -ArgumentList ('"' + (Join-Path $dashboardRoot 'server.py') + '"') -WorkingDirectory $workspaceRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $workspaceRoot 'private/dashboard-output.log') -RedirectStandardError (Join-Path $workspaceRoot 'private/dashboard-error.log')
for ($dashboardAttempt = 0; $dashboardAttempt -lt 30; $dashboardAttempt++) {
    Start-Sleep -Milliseconds 500
    try {
        $dashboardResponse = Invoke-WebRequest -Uri $dashboardUrl -TimeoutSec 2
        if ($dashboardResponse.StatusCode -eq 200 -and $dashboardResponse.Content -match 'Astral') {
            Start-Process $dashboardUrl
            Write-Host 'Dashboard ready. Login details: private\dashboard\LOGIN.txt'
            exit 0
        }
    } catch { }
    if ($dashboardProcess.HasExited) { break }
}
throw 'Dashboard did not start. Check private/dashboard-error.log.'
