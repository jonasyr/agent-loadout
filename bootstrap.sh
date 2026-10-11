#!/usr/bin/env bash
# Set up loadout on this machine. All logic lives in `loadout bootstrap`.
# From a clone:  ./bootstrap.sh --install
# Without one:   curl -fsSL https://raw.githubusercontent.com/jonasyr/agent-loadout/main/bootstrap.sh | bash -s -- --install
# Nothing here uses sudo. --dir PATH picks where the one-liner clones (default: ./agent-loadout).
set -euo pipefail
repo_url="${LOADOUT_REPO_URL:-https://github.com/jonasyr/agent-loadout}"  # LOADOUT_REPO_URL/LOADOUT_REF: tests only
ref="${LOADOUT_REF:-main}"

dir=""
args=()
while [ $# -gt 0 ]; do
  case "$1" in
    --dir) dir="${2:?--dir needs a path}"; shift 2 ;;
    --dir=*) dir="${1#--dir=}"; shift ;;
    *) args+=("$1"); shift ;;
  esac
done

git_hint() {
  case "$(uname -s)" in
    Darwin) echo "xcode-select --install" ;;
    *) echo "sudo apt install git   (Debian/Ubuntu; other distros: their package manager)" ;;
  esac
}

src="${BASH_SOURCE[0]:-}"
if [ -n "$src" ] && [ -f "$(dirname "$src")/bin/loadout" ]; then
  kit="$(cd "$(dirname "$src")" && pwd)"
else
  if ! command -v git >/dev/null 2>&1; then
    echo "loadout needs git to download itself. Install it, then run this command again:" >&2
    echo "  $(git_hint)" >&2
    exit 1
  fi
  kit="${dir:-$PWD/agent-loadout}"
  if [ -e "$kit" ]; then
    origin="$(git -C "$kit" remote get-url origin 2>/dev/null || true)"
    case "$origin" in
      *jonasyr/agent-loadout*|"$repo_url") echo "using the existing clone in $kit" ;;
      *) echo "$kit exists and is not a clone of agent-loadout; choose another folder with --dir PATH" >&2; exit 1 ;;
    esac
  else
    echo "cloning agent-loadout into $kit"
    git clone -q "$repo_url" "$kit"
    git -C "$kit" checkout -q "$ref"
  fi
fi

export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  echo "installing uv (it also provides Python for loadout)"
  curl -LsSf https://astral.sh/uv/install.sh | UV_NO_MODIFY_PATH=1 sh
fi

cd "$kit"
run=(uv run --no-project --no-config --python ">=3.10" bin/loadout bootstrap ${args[@]+"${args[@]}"})
if [ ! -t 0 ] && { : </dev/tty; } 2>/dev/null; then
  exec "${run[@]}" </dev/tty  # one-liner: stdin is the script pipe, so ask on the terminal
fi
exec "${run[@]}"
