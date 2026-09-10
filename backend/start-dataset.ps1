$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $pythonExe = Join-Path $PSScriptRoot '.venv-dataset\Scripts\python.exe'
    if (-not (Test-Path $pythonExe)) {
        & py -3.11 -m venv .venv-dataset
        if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.11 x64 with the Python launcher, then retry.' }
    }
    & $pythonExe -m pip install -r requirements-api.txt -r requirements-r2.txt -r requirements-alignment.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    $env:PYTHONUTF8 = '1'
    Write-Host 'Dataset workbench: http://127.0.0.1:8766 - keep this window open.'
    & $pythonExe -m uvicorn dataset_app:app --host 127.0.0.1 --port 8766 --workers 1
    if ($LASTEXITCODE -ne 0) { throw 'Dataset service exited with an error.' }
} finally { Pop-Location }
