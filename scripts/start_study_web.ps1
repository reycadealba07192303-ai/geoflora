# Start the usability-study web app on http://127.0.0.1:5180 against the isolated geoflora_study database.
# Prepare it first with scripts/prepare_usability_study.py. The live app on 5173 and its database are not touched.
$root = Split-Path -Parent $PSScriptRoot
$env:GEOFLORA_MONGODB_URI = "mongodb://127.0.0.1:27017/geoflora_study"
$env:GEOFLORA_ML_API_URL = "http://127.0.0.1:8000"
$process = Start-Process -FilePath "node" -ArgumentList "node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", "5180" `
  -WorkingDirectory (Join-Path $root "apps\web") -RedirectStandardOutput (Join-Path $root "storage\logs\study-web-stdout.log") `
  -RedirectStandardError (Join-Path $root "storage\logs\study-web-stderr.log") -WindowStyle Hidden -PassThru
$process.Id | Set-Content (Join-Path $root "storage\logs\study-web.pid")
Remove-Item Env:GEOFLORA_MONGODB_URI, Env:GEOFLORA_ML_API_URL
Write-Output "Study workspace starting at http://127.0.0.1:5180 (PID $($process.Id)). Stop it with: Stop-Process -Id $($process.Id)"
