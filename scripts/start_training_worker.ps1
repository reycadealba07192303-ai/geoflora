$ErrorActionPreference = 'Stop'
$workspaceRoot = Split-Path -Parent $PSScriptRoot
$workerPython = Join-Path $workspaceRoot 'services/ml/.venv/Scripts/python.exe'
$workerScript = Join-Path $workspaceRoot 'scripts/auto_training_worker.py'
$workerLogs = Join-Path $workspaceRoot 'storage/logs'
New-Item -ItemType Directory -Path $workerLogs -Force | Out-Null
$workerPidPath = Join-Path $workerLogs 'auto-training-worker.pid'
if (Test-Path -LiteralPath $workerPidPath) {
  $existingWorker = Get-Process -Id ([int](Get-Content -LiteralPath $workerPidPath)) -ErrorAction SilentlyContinue
  if ($existingWorker -and $existingWorker.ProcessName -like 'python*') {
    Write-Output "Training worker process already exists: $($existingWorker.Id)"
    return
  }
}
$workerProcess = Start-Process -FilePath $workerPython -ArgumentList @('-u', $workerScript) -WorkingDirectory $workspaceRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $workerLogs 'auto-training-worker-stdout.log') -RedirectStandardError (Join-Path $workerLogs 'auto-training-worker-stderr.log') -PassThru
$workerProcess.Id | Set-Content -LiteralPath $workerPidPath
Write-Output "Training worker started: $($workerProcess.Id)"
