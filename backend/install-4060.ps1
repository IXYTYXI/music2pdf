$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        throw 'Install Python 3.11 x64 from python.org with the Python launcher, then retry.'
    }
    & py -3.11 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 venv creation failed.' }
    $pythonExe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    & $pythonExe -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw 'pip update failed.' }
    & $pythonExe -m pip install torch==2.9.1 --index-url https://download.pytorch.org/whl/cu128
    if ($LASTEXITCODE -ne 0) { throw 'CUDA PyTorch installation failed.' }
    & $pythonExe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    & $pythonExe -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Dependency conflict detected.' }
    $env:PYTHONUTF8 = '1'
    & $pythonExe cli.py doctor
    if ($LASTEXITCODE -ne 0) { throw 'GPU check failed. Update the NVIDIA driver and read the output above.' }
    Write-Host 'Ready. Run start-4060.ps1 or use cli.py separate. Models download on first use.'
} finally {
    Pop-Location
}
