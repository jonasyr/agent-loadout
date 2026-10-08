# Set up loadout on this machine. All logic lives in `loadout bootstrap`.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  Write-Error 'loadout needs Python (>= 3.10). Install it (e.g. winget install Python.Python.3.12) and re-run.'
  exit 1
}
if (-not (Get-Command bash -ErrorAction SilentlyContinue)) {
  Write-Warning 'Git Bash not found: Claude Code hooks need Git for Windows.'
}
python bin/loadout bootstrap @args
exit $LASTEXITCODE
