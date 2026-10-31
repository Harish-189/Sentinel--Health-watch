# Sentinel: one command on Windows.  Usage: .\start.ps1  [-ApiPort 8000] [-WebPort 5173]
param([int]$ApiPort = 8000, [int]$WebPort = 5173)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path backend\.venv)) {
  Write-Host "[sentinel] creating Python venv..."
  python -m venv backend\.venv
  backend\.venv\Scripts\python -m pip install -q -r backend\requirements.txt
}
if (-not (Test-Path frontend\node_modules)) { Push-Location frontend; npm install --silent; Pop-Location }
Write-Host "[sentinel] API -> http://127.0.0.1:$ApiPort  (warms the demo; builds the eval report on first run)"
$api = Start-Process -PassThru -NoNewWindow -WorkingDirectory "$PSScriptRoot\backend" -FilePath "$PSScriptRoot\backend\.venv\Scripts\python.exe" `
  -ArgumentList "-m", "uvicorn", "app.main:app", "--port", "$ApiPort"
try {
  Write-Host "[sentinel] UI  -> http://localhost:$WebPort"
  $env:SENTINEL_API = "http://127.0.0.1:$ApiPort"
  Push-Location frontend; npx vite --port $WebPort --strictPort
} finally { Pop-Location; Stop-Process -Id $api.Id -ErrorAction SilentlyContinue }
