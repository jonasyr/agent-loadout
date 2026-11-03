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
$dir = $null; $rest = @(); $channel = 'stable'
for ($i = 0; $i -lt $args.Count; $i++) {
  if ($args[$i] -eq '--dir') {
    if ($i + 1 -ge $args.Count) { Fail '--dir needs a path'; return }
    $dir = $args[$i + 1]; $i++
  }
  elseif ($args[$i] -like '--dir=*') { $dir = $args[$i].Substring(6) }
  elseif ($args[$i] -eq '--channel') {
    if ($i + 1 -ge $args.Count) { Fail '--channel needs stable or dev'; return }
    $channel = $args[$i + 1]; $rest += $args[$i], $args[$i + 1]; $i++
  }
  elseif ($args[$i] -like '--channel=*') { $channel = $args[$i].Substring(10); $rest += $args[$i] }
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
# An existing clone on stable moves to the release only when that loses no local commit.
function Move-ToRelease($d) {
  if ($env:LOADOUT_REF -or $channel -ne 'stable') { return $true }
  $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
  try {
    git -C $d fetch -q --tags origin 2>$null | Out-Null
    $tag = Get-ReleaseTag $d
    if (-not $tag) { Fail-NoRelease; return $false }
    $head = "$(git -C $d rev-parse HEAD 2>$null)"
    $want = "$(git -C $d rev-parse "refs/tags/$tag^{commit}" 2>$null)"
    if ($head -eq $want) { return $true }
    $ahead = "$(git -C $d rev-list --count "refs/tags/$tag..HEAD" 2>$null)"
    if ($ahead -eq '0') {
      git -C $d checkout -q --detach "refs/tags/$tag" 2>$null
      if ($LASTEXITCODE -eq 0) { Write-Host "moved the clone to release $tag"; return $true }
    }
    Write-Host "the clone has changes of its own, so it is left as it is (release $tag was not checked out)"
  } finally { $ErrorActionPreference = $prev }
  return $true
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
# Run inside an existing clone, the one-liner uses that clone instead of cloning again.
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
    if (-not (Move-ToRelease $kit)) { return }
  } elseif (Test-Path $kit) {
    if (-not (Test-Clone $kit)) {
      Fail "$kit exists and is not a clone of agent-loadout; choose another folder with --dir PATH"
      return
    }
    Write-Host "using the existing clone in $kit"
    if (-not (Move-ToRelease $kit)) { return }
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
