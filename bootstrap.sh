#!/usr/bin/env bash
# Set up loadout on this machine. All logic lives in `loadout bootstrap`.
# From a clone:  ./bootstrap.sh --install
# Without one:   curl -fsSL https://raw.githubusercontent.com/jonasyr/agent-loadout/main/bootstrap.sh | bash -s -- --install
# Run inside an existing clone, the one-liner uses that clone instead of cloning again.
# Nothing here uses sudo. --dir PATH picks where the one-liner clones (default: ./agent-loadout).
set -euo pipefail

curl_hint() {
  case "$(uname -s)" in
    Darwin) echo "macOS ships curl; check that /usr/bin is on your PATH" ;;
    *) echo "sudo apt install curl   (Debian/Ubuntu; other distros: their package manager)" ;;
  esac
}

find_python() {
  (cd / && uv python find --system --no-config --no-project '>=3.11' 2>/dev/null) || true
}

git_hint() {
  case "$(uname -s)" in
    Darwin) echo "xcode-select --install" ;;
    *) echo "sudo apt install git   (Debian/Ubuntu; other distros: their package manager)" ;;
  esac
}

norm() {  # strip trailing slash and .git so URL spellings compare equal
  local o="${1%/}"; o="${o%.git}"; printf '%s' "${o%/}"
}

is_clone() {  # exact origin, bin/loadout present, and the folder itself is the repo root
  local d="$1" origin top phys
  [ -f "$d/bin/loadout" ] || return 1
  origin="$(norm "$(git -C "$d" remote get-url origin 2>/dev/null || true)")"
  case "$origin" in
    https://github.com/jonasyr/agent-loadout|git@github.com:jonasyr/agent-loadout|ssh://git@github.com/jonasyr/agent-loadout) ;;
    *) [ -n "$origin" ] && [ "$origin" = "$(norm "$repo_url")" ] || return 1 ;;
  esac
  top="$(git -C "$d" rev-parse --show-toplevel 2>/dev/null || true)"
  phys="$(cd "$d" && pwd -P)"
  [ -n "$top" ] && [ "$top" = "$phys" ]
}

pick_tag() {  # the newest annotated vX.Y.Z tag at or above 0.2.0 whose tagger date is 3 days old; same rule as channels.py
  local dir="$1" now name type when LC_ALL=C
  now="$(date +%s)"
  while read -r name type when; do
    name="${name#refs/tags/}"
    [[ "$name" =~ ^v(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})$ ]] || continue
    [ "$type" = tag ] || continue
    [ "${BASH_REMATCH[1]}" -gt 0 ] || [ "${BASH_REMATCH[2]}" -ge 2 ] || continue
    case "$when" in ''|*[!0-9]*) continue ;; esac
    [ $((now - when)) -ge 259200 ] || continue
    printf '%s' "$name"
    return 0
  done < <(git -C "$dir" for-each-ref --sort=-v:refname --format='%(refname) %(objecttype) %(taggerdate:unix)' refs/tags 2>/dev/null)
  return 1
}

refresh_clone() {  # a reused clone on main with a clean tree gets the commits pushed since; a release clone stays put
  local dir="$1"
  if [ "${LOADOUT_NO_AUTO_PULL:-}" = 1 ] || [ -n "${LOADOUT_REF:-}" ]; then return 0; fi
  [ "$(git -C "$dir" symbolic-ref -q --short HEAD 2>/dev/null)" = main ] || return 0
  [ -z "$(git -C "$dir" status --porcelain --untracked-files=no 2>/dev/null)" ] || return 0
  echo "updating the clone (git pull --ff-only)"
  GIT_TERMINAL_PROMPT=0 git -C "$dir" pull -q --ff-only ||
    echo "could not update the clone in $dir; going on with the code it has (loadout update tries again)" >&2
}

no_release() {
  echo "no stable release is ready yet; wait a few days, or install dev:" >&2
  echo "  curl -fsSL https://raw.githubusercontent.com/jonasyr/agent-loadout/main/bootstrap.sh | bash -s -- --install --channel dev" >&2
  exit 1
}

main() {
  local repo_url="${LOADOUT_REPO_URL:-https://github.com/jonasyr/agent-loadout}"  # LOADOUT_REPO_URL/LOADOUT_REF: tests only
  local ref="${LOADOUT_REF:-main}"

  local dir="" piped=0 src kit channel=stable tag given=0
  local args=()
  while [ $# -gt 0 ]; do
    case "$1" in
      --channel) channel="${2:?--channel needs stable or dev}"; given=1; args+=("$1" "$2"); shift 2 ;;
      --channel=*) channel="${1#--channel=}"; given=1; args+=("$1"); shift ;;
      --dir) dir="${2:?--dir needs a path}"; shift 2 ;;
      --dir=*) dir="${1#--dir=}"; shift ;;
      *) args+=("$1"); shift ;;
    esac
  done

  case "$channel" in stable|dev) ;; *) echo "--channel: use stable or dev" >&2; exit 2 ;; esac

  # Only a fresh clone picks a release here. An existing clone stays where it is: `loadout bootstrap --channel
  # stable`, `loadout channel stable` and `loadout update` move it, with the undo in a backup.
  # run from a file, $0 is that file; piped, bash 5.2 sets BASH_SOURCE to "main" and 5.3 leaves it empty
  src="${BASH_SOURCE[0]:-}"
  if [ -n "$src" ] && [ "$src" = "$0" ] && [ -f "$src" ] && [ -f "$(dirname "$src")/bin/loadout" ]; then
    kit="$(cd "$(dirname "$src")" && pwd)"
  else
    piped=1
    # macOS: /usr/bin/git exists without the Command Line Tools but cannot run
    if ! command -v git >/dev/null 2>&1 || ! git --version >/dev/null 2>&1; then
      echo "loadout needs git to download itself. Install it, then run this command again:" >&2
      echo "  $(git_hint)" >&2
      exit 1
    fi
    kit="${dir:-$PWD/agent-loadout}"
    if [ -z "$dir" ] && is_clone "$PWD"; then
      kit="$PWD"
      echo "using the clone in $kit"
      refresh_clone "$kit"
    elif [ -e "$kit" ]; then
      if is_clone "$kit"; then
        echo "using the existing clone in $kit"
        refresh_clone "$kit"
      else
        echo "$kit exists and is not a clone of agent-loadout; choose another folder with --dir PATH" >&2
        exit 1
      fi
    else
      echo "cloning agent-loadout into $kit"
      git clone -q "$repo_url" "$kit" || {
        echo "could not download agent-loadout from $repo_url (offline?). Check your connection and run this again." >&2
        exit 1
      }
      if [ -n "${LOADOUT_REF:-}" ] || [ "$channel" = dev ]; then
        git -C "$kit" checkout -q "$ref" || { echo "could not check out $ref in $kit" >&2; exit 1; }
      elif tag="$(pick_tag "$kit")"; then
        git -C "$kit" checkout -q --detach "refs/tags/$tag" || { echo "could not check out $tag in $kit" >&2; exit 1; }
        echo "using release $tag"
        [ "$given" = 1 ] || args+=(--channel stable)  # a new install records its channel; a re-run forwards nothing
      else
        rm -rf "$kit"  # the clone this run just made; nothing of the user's
        no_release
      fi
    fi
  fi

  # created before any installer does: with Ubuntu's umask 002 it would be group-writable,
  # and codebase-memory-mcp refuses to install into such a folder
  [ -d "$HOME/.local/bin" ] || { mkdir -p "$HOME/.local/bin" && chmod 755 "$HOME/.local/bin"; }
  export PATH="$HOME/.local/bin:$PATH"
  if ! command -v uv >/dev/null 2>&1; then
    if ! command -v curl >/dev/null 2>&1; then
      echo "loadout needs curl to download uv. Install it, then run this again:" >&2
      echo "  $(curl_hint)" >&2
      exit 1
    fi
    echo "installing uv (it also provides Python for loadout)"
    curl -LsSf https://astral.sh/uv/install.sh | UV_NO_MODIFY_PATH=1 sh || true
    export PATH="$HOME/.local/bin:$PATH"
    if ! command -v uv >/dev/null 2>&1; then
      echo "could not install uv (offline?). Install it from https://docs.astral.sh/uv/ and run this again." >&2
      exit 1
    fi
  fi

  # Look Python up from / and run it directly: uv started in a project folder would use its .venv.
  local py
  py="$(find_python)"
  if [ -z "$py" ]; then
    (cd / && uv python install --no-config '>=3.11') >&2 || true
    py="$(find_python)"
  fi
  if [ -z "$py" ]; then
    echo "could not get Python 3.11 or newer through uv (offline?). Check your connection and run this again." >&2
    exit 1
  fi

  cd "$kit"
  local run=("$py" bin/loadout bootstrap ${args[@]+"${args[@]}"})
  if [ "$piped" = 1 ] && [ ! -t 0 ] && { : </dev/tty; } 2>/dev/null; then
    exec "${run[@]}" </dev/tty  # one-liner: stdin is the script pipe, so ask on the terminal
  fi
  exec "${run[@]}"
}

# Last line: a download cut off halfway defines nothing and runs nothing.
main "$@"
