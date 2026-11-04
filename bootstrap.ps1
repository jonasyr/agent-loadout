# Set up loadout on this machine (native Windows, experimental). All logic lives in `loadout bootstrap`.
# From a clone:  powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap.ps1 --install
# Without one:   & ([scriptblock]::Create((irm https://raw.githubusercontent.com/jonasyr/agent-loadout/main/bootstrap.ps1))) --install
$ErrorActionPreference = 'Stop'
Write-Warning 'Native Windows is experimental and not recommended. WSL 2 is the recommended setup on Windows: https://github.com/jonasyr/agent-loadout/blob/main/docs/how-to/wsl.md'
# Run as a scriptblock (the one-liner), `exit` would close the user's PowerShell window:
# failures then set $LASTEXITCODE and `return` instead.
$asFile = [bool]$PSCommandPath
function Fail($msg) {
  $host.UI.WriteErrorLine($msg)
  $global:LASTEXITCODE = 1
  if ($asFile) { exit 1 }
}
$repoUrl = if ($env:LOADOUT_REPO_URL) { $env:LOADOUT_REPO_URL } else { 'https://github.com/jonasyr/agent-loadout' }
$ref = if ($env:LOADOUT_REF) { $env:LOADOUT_REF } else { 'main' }
$dir = $null; $rest = @(); $channel = 'stable'; $given = $false
for ($i = 0; $i -lt $args.Count; $i++) {
  if ($args[$i] -eq '--dir') {
    if ($i + 1 -ge $args.Count) { Fail '--dir needs a path'; return }
    $dir = $args[$i + 1]; $i++
  }
  elseif ($args[$i] -like '--dir=*') { $dir = $args[$i].Substring(6) }
  elseif ($args[$i] -eq '--channel') {
    if ($i + 1 -ge $args.Count) { Fail '--channel needs stable or dev'; return }
    $channel = $args[$i + 1]; $given = $true; $rest += $args[$i], $args[$i + 1]; $i++
  }
  elseif ($args[$i] -like '--channel=*') { $channel = $args[$i].Substring(10); $given = $true; $rest += $args[$i] }
  else { $rest += $args[$i] }
}
if ($channel -cnotin 'stable', 'dev') { Fail '--channel: use stable or dev'; return }
# The newest annotated vX.Y.Z tag at or above 0.2.0 whose tagger date is 3 days old; same rule as bootstrap.sh and channels.py.
function Get-ReleaseTag($d) {
  $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
  $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
  try { $lines = @(git -C $d for-each-ref --sort=-v:refname --format='%(refname) %(objecttype) %(taggerdate:unix)' refs/tags 2>$null) }
  finally { $ErrorActionPreference = $prev }
  foreach ($line in $lines) {
    $p = "$line" -split ' '
    if ($p.Count -lt 3 -or $p[1] -cne 'tag') { continue }
    if ($p[0] -cnotmatch '^refs/tags/(v(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8}))$') { continue }
    $name = $Matches[1]; $major = [int64]$Matches[2]; $minor = [int64]$Matches[3]
    if ($major -eq 0 -and $minor -lt 2) { continue }
    if ($p[2] -cnotmatch '^[0-9]+$') { continue }
    if ($now - [int64]$p[2] -lt 259200) { continue }
    return $name
  }
  return $null
}
function Fail-NoRelease {
  Fail ("no stable release is ready yet; wait a few days, or install dev:`n" +
        "  & ([scriptblock]::Create((irm https://raw.githubusercontent.com/jonasyr/agent-loadout/main/bootstrap.ps1))) --install --channel dev")
}
function Normalize-Origin($o) { ("$o").Trim().TrimEnd('/') -replace '\.git$', '' -replace '/$', '' }
function Test-Clone($d) {
  if (-not (Test-Path (Join-Path $d 'bin/loadout'))) { return $false }
  $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
  try {
    $origin = Normalize-Origin (git -C $d remote get-url origin 2>$null)
    $top = "$(git -C $d rev-parse --show-toplevel 2>$null)"
  } finally { $ErrorActionPreference = $prev }
  $known = @('https://github.com/jonasyr/agent-loadout', 'git@github.com:jonasyr/agent-loadout', 'ssh://git@github.com/jonasyr/agent-loadout', (Normalize-Origin $repoUrl))
  if (-not $origin -or $known -notcontains $origin) { return $false }
  if (-not $top) { return $false }
  return ([IO.Path]::GetFullPath($top).TrimEnd('\', '/') -ieq [IO.Path]::GetFullPath((Resolve-Path $d).Path).TrimEnd('\', '/'))
}
# A reused clone on main with a clean tree gets the commits pushed since; a release clone stays put.
function Update-Clone($d) {
  if ($env:LOADOUT_NO_AUTO_PULL -eq '1' -or $env:LOADOUT_REF) { return }
  $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
  try {
    if ("$(git -C $d symbolic-ref -q --short HEAD 2>$null)" -cne 'main') { return }
    if ("$(git -C $d status --porcelain --untracked-files=no 2>$null)") { return }
    Write-Host 'updating the clone (git pull --ff-only)'
    $prompt = $env:GIT_TERMINAL_PROMPT  # the one-liner runs in the user's session: put their value back
    $env:GIT_TERMINAL_PROMPT = '0'
    try { git -C $d pull -q --ff-only } finally { $env:GIT_TERMINAL_PROMPT = $prompt }
    if ($LASTEXITCODE -ne 0) {
      $host.UI.WriteErrorLine("could not update the clone in $d; going on with the code it has (loadout update tries again)")
      $global:LASTEXITCODE = 0
    }
  } finally { $ErrorActionPreference = $prev }
}
# Run inside an existing clone, the one-liner uses that clone instead of cloning again. Only a fresh clone picks a
# release here; an existing one stays where it is (loadout bootstrap --channel stable, loadout channel stable and
# loadout update move it, with the undo in a backup).
if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot 'bin/loadout'))) {
  $kit = $PSScriptRoot
} else {
  if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Fail 'loadout needs git to download itself. Install it, then run this command again: winget install --id Git.Git -e'
    return
  }
  $kit = if ($dir) { $dir } else { Join-Path (Get-Location) 'agent-loadout' }
  if (-not $dir -and (Test-Clone (Get-Location).Path)) {
    $kit = (Get-Location).Path
    Write-Host "using the clone in $kit"
    Update-Clone $kit
  } elseif (Test-Path $kit) {
    if (-not (Test-Clone $kit)) {
      Fail "$kit exists and is not a clone of agent-loadout; choose another folder with --dir PATH"
      return
    }
    Write-Host "using the existing clone in $kit"
    Update-Clone $kit
  } else {
    Write-Host "cloning agent-loadout into $kit"
    git clone -q $repoUrl $kit
    if ($LASTEXITCODE -ne 0) { Fail "could not download agent-loadout from $repoUrl (offline?). Check your connection and run this again."; return }
    if ($env:LOADOUT_REF -or $channel -eq 'dev') {
      git -C $kit checkout -q $ref
      if ($LASTEXITCODE -ne 0) { Fail "could not check out '$ref' in $kit"; return }
    } else {
      $tag = Get-ReleaseTag $kit
      if (-not $tag) {
        Remove-Item -Recurse -Force $kit  # the clone this run just made; nothing of the user's
        Fail-NoRelease; return
      }
      git -C $kit checkout -q --detach "refs/tags/$tag"
      if ($LASTEXITCODE -ne 0) { Fail "could not check out $tag in $kit"; return }
      Write-Host "using release $tag"
      if (-not $given) { $rest += '--channel', 'stable' }  # a new install records its channel; a re-run forwards nothing
    }
  }
}
# Git for Windows puts only Git\cmd on PATH, and System32\bash.exe is WSL's: look for Git\bin\bash.exe itself
$gitBash = @($env:CLAUDE_CODE_GIT_BASH_PATH, "$env:ProgramFiles\Git\bin\bash.exe")
$gitExe = Get-Command git -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if ($gitExe) { $gitBash += Join-Path (Split-Path (Split-Path $gitExe.Source)) 'bin\bash.exe' }
if (-not ($gitBash | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) })) {
  Write-Warning 'Git Bash not found: Claude Code hooks need Git for Windows.'
}
$env:Path = "$HOME\.local\bin;$env:Path"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Host 'installing uv (it also provides Python for loadout)'
  $env:UV_NO_MODIFY_PATH = '1'
  try { Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression } catch { }
  $env:Path = "$HOME\.local\bin;$env:Path"
  if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Fail 'could not install uv (offline?). Install it from https://docs.astral.sh/uv/ and run this again.'
    return
  }
}
# Look Python up from a neutral folder and run it directly: uv started in a project folder would use its .venv.
function Find-Python {
  Push-Location $env:SystemRoot
  $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
  try { "$(uv python find --system --no-config --no-project '>=3.11' 2>$null | Select-Object -First 1)".Trim() }
  finally { $ErrorActionPreference = $prev; Pop-Location }
}
$py = Find-Python
if (-not $py) {
  Push-Location $env:SystemRoot
  $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
  try { uv python install --no-config '>=3.11' 2>&1 | Out-Host }
  finally { $ErrorActionPreference = $prev; Pop-Location }
  $py = Find-Python
}
if (-not $py) {
  Fail 'could not get Python 3.11 or newer through uv (offline?). Check your connection and run this again.'
  return
}
Push-Location $kit
try { & $py bin/loadout bootstrap @rest; $code = $LASTEXITCODE }
finally { Pop-Location }
if ($asFile) { exit $code }
$global:LASTEXITCODE = $code
