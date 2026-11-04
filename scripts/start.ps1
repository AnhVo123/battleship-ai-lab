$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) { throw 'Run scripts/setup.ps1 first.' }
if (-not (Test-Path -LiteralPath 'frontend/dist/index.html')) { throw 'Run scripts/setup.ps1 to build the UI.' }
Write-Host 'Battleship Strategy Lab: http://127.0.0.1:8000 (Ctrl+C to stop)'
& '.venv/Scripts/python.exe' -m uvicorn battleship_lab.web:create_app --factory --host 127.0.0.1 --port 8000
if ($LASTEXITCODE -ne 0) { throw 'Local server stopped with an error.' }
