$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonExecutable = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonExecutable)) { throw 'Run scripts/setup.ps1 first.' }
$server = Start-Process -FilePath $pythonExecutable -ArgumentList @('-m','uvicorn','battleship_lab.web:create_app','--factory','--host','127.0.0.1','--port','8000') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
try {
    Set-Location -LiteralPath (Join-Path $projectRoot 'frontend')
    Write-Host 'Development UI: http://127.0.0.1:5173 (Ctrl+C to stop)'
    npm.cmd run dev
} finally {
    if (-not $server.HasExited) { Stop-Process -Id $server.Id }
}
