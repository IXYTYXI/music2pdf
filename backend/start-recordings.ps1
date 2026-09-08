$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$collectorPython = Join-Path $PSScriptRoot '.venv-collector\Scripts\python.exe'
if (-not (Test-Path $collectorPython)) {
    py -3 -m venv .venv-collector
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
$marker = Join-Path $PSScriptRoot '.venv-collector\requirements-installed.txt'
if (-not (Test-Path $marker) -or ((Get-FileHash requirements-collector.txt).Hash -ne (Get-FileHash $marker).Hash)) {
    & $collectorPython -m pip install -r requirements-collector.txt
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Copy-Item requirements-collector.txt $marker
}
if ($args.Count -eq 0) { & $collectorPython recording_collector.py --help }
else { & $collectorPython recording_collector.py @args }
exit $LASTEXITCODE
