# Usage: powershell -ExecutionPolicy Bypass -File scripts/windows/dev.ps1 setup
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$pythonCandidates = @(
    (Join-Path $projectRoot '.venv/Scripts/python.exe'),
    'python.exe',
    'py.exe'
)
foreach ($candidate in $pythonCandidates) {
    $command = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($null -eq $command) { continue }
    & $command.Source -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>$null
    if ($LASTEXITCODE -eq 0) {
        & $command.Source (Join-Path $projectRoot 'scripts/dev.py') @args
        exit $LASTEXITCODE
    }
}
Write-Error 'Python 3.11+ is required. Install it, then rerun this command.'
exit 1
