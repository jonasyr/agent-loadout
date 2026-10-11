# Set up loadout on this machine (native Windows, experimental). All logic lives in `loadout bootstrap`.
# From a clone:  powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap.ps1 --install
# Without one:   & ([scriptblock]::Create((irm https://raw.githubusercontent.com/jonasyr/agent-loadout/main/bootstrap.ps1))) --install
$ErrorActionPreference = 'Stop'
Write-Warning 'Native Windows is experimental and not recommended. WSL 2 is the recommended setup on Windows: docs/how-to/wsl.md'
$repoUrl = if ($env:LOADOUT_REPO_URL) { $env:LOADOUT_REPO_URL } else { 'https://github.com/jonasyr/agent-loadout' }
$ref = if ($env:LOADOUT_REF) { $env:LOADOUT_REF } else { 'main' }
$dir = $null; $rest = @()
for ($i = 0; $i -lt $args.Count; $i++) {
  if ($args[$i] -eq '--dir') { $dir = $args[$i + 1]; $i++ }
  elseif ($args[$i] -like '--dir=*') { $dir = $args[$i].Substring(6) }
  else { $rest += $args[$i] }
}
if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot 'bin/loadout'))) {
  $kit = $PSScriptRoot
} else {
  if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Error 'loadout needs git to download itself. Install it, then run this command again: winget install --id Git.Git -e'
    exit 1
  }
  $kit = if ($dir) { $dir } else { Join-Path (Get-Location) 'agent-loadout' }
  if (Test-Path $kit) {
    $origin = git -C $kit remote get-url origin 2>$null
    if ($origin -notmatch 'jonasyr/agent-loadout' -and $origin -ne $repoUrl) {
      Write-Error "$kit exists and is not a clone of agent-loadout; choose another folder with --dir PATH"
      exit 1
    }
    Write-Host "using the existing clone in $kit"
  } else {
    Write-Host "cloning agent-loadout into $kit"
    git clone -q $repoUrl $kit
    git -C $kit checkout -q $ref
  }
}
if (-not (Get-Command bash -ErrorAction SilentlyContinue)) {
  Write-Warning 'Git Bash not found: Claude Code hooks need Git for Windows.'
}
$env:Path = "$HOME\.local\bin;$env:Path"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Host 'installing uv (it also provides Python for loadout)'
  $env:UV_NO_MODIFY_PATH = '1'
  Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
}
Set-Location $kit
uv run --no-project --no-config --python '>=3.10' bin/loadout bootstrap @rest
exit $LASTEXITCODE
