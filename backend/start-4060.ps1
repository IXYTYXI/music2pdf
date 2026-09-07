$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $pythonExe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path $pythonExe)) { throw 'Run install-4060.ps1 first.' }
    $env:PYTHONUTF8 = '1'
    & $pythonExe cli.py doctor
    if ($LASTEXITCODE -ne 0) { throw 'CUDA check failed; the service was not started.' }
    Write-Host 'API: http://127.0.0.1:8765/docs (one GPU worker; keep this window open)'
    & $pythonExe -m uvicorn app:app --host 127.0.0.1 --port 8765 --workers 1
    if ($LASTEXITCODE -ne 0) { throw 'API exited with an error.' }
} finally {
    Pop-Location
}
