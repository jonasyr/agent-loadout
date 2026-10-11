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
  (cd / && uv python find --system --no-config --no-project '>=3.10' 2>/dev/null) || true
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

main() {
  local repo_url="${LOADOUT_REPO_URL:-https://github.com/jonasyr/agent-loadout}"  # LOADOUT_REPO_URL/LOADOUT_REF: tests only
  local ref="${LOADOUT_REF:-main}"

  local dir="" piped=0 src kit
  local args=()
  while [ $# -gt 0 ]; do
    case "$1" in
      --dir) dir="${2:?--dir needs a path}"; shift 2 ;;
      --dir=*) dir="${1#--dir=}"; shift ;;
      *) args+=("$1"); shift ;;
    esac
  done

  src="${BASH_SOURCE[0]:-}"
  if [ -n "$src" ] && [ -f "$(dirname "$src")/bin/loadout" ]; then
    kit="$(cd "$(dirname "$src")" && pwd)"
  else
    piped=1
    if ! command -v git >/dev/null 2>&1; then
      echo "loadout needs git to download itself. Install it, then run this command again:" >&2
      echo "  $(git_hint)" >&2
      exit 1
    fi
    kit="${dir:-$PWD/agent-loadout}"
    if [ -z "$dir" ] && is_clone "$PWD"; then
      kit="$PWD"
      echo "using the clone in $kit"
    elif [ -e "$kit" ]; then
      if is_clone "$kit"; then
        echo "using the existing clone in $kit"
      else
        echo "$kit exists and is not a clone of agent-loadout; choose another folder with --dir PATH" >&2
        exit 1
      fi
    else
      echo "cloning agent-loadout into $kit"
      git clone -q "$repo_url" "$kit" && git -C "$kit" checkout -q "$ref" || {
        echo "could not download agent-loadout from $repo_url (offline?). Check your connection and run this again." >&2
        exit 1
      }
    fi
  fi

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
    (cd / && uv python install --no-config '>=3.10') >&2 || true
    py="$(find_python)"
  fi
  if [ -z "$py" ]; then
    echo "could not get Python 3.10 or newer through uv (offline?). Check your connection and run this again." >&2
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
