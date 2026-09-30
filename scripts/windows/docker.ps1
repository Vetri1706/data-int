param(
    [ValidateSet('start', 'stop', 'status', 'logs', 'build')]
    [string]$Action = 'start',
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Services
)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$composeArgs = @('--project-directory', $projectRoot, '--env-file', (Join-Path $projectRoot '.env'), '-f', (Join-Path $projectRoot 'compose.yml'))
switch ($Action) {
    'start' { $composeArgs += @('up', '-d', '--build', '--wait', '--wait-timeout', '240') }
    'stop' { $composeArgs += 'stop' }
    'status' { $composeArgs += 'ps' }
    'logs' { $composeArgs += @('logs', '--tail', '100', '-f') }
    'build' { $composeArgs += 'build' }
}
if ($Services) { $composeArgs += $Services }
& docker compose @composeArgs
exit $LASTEXITCODE
