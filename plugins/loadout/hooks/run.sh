#!/usr/bin/env bash
# Run a hook command only if its binary is installed, so a machine without a tool
# simply runs without that hook. With --soft, errors are swallowed (exit 0, no stderr).
# With --python, the next argument is a Python script: run it with python3 or python (3.11+),
# else with the interpreter uv finds (or installs), else skip the hook.
soft=0
if [ "${1:-}" = "--soft" ]; then soft=1; shift; fi
if [ "${1:-}" = "--python" ]; then
  shift
  py=""
  for cand in python3 python; do  # python.org installs only `python` on Windows
    if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
      py="$cand"; break
    fi
  done
  if [ -n "$py" ]; then
    set -- "$py" "$@"
  elif command -v uv >/dev/null 2>&1; then
    # Hooks run in the open project: uv must not pick up its .venv, uv.toml or pyproject.toml,
    # so the interpreter is looked up from / and then run directly (never `uv run` here).
    find_py() { (cd / && uv python find --system --no-config --no-project '>=3.11' 2>/dev/null); }
    py="$(find_py)"
    if [ -z "$py" ]; then
      if [ "$soft" = 1 ]; then
        (cd / && uv python install --no-config '>=3.11') >/dev/null 2>&1
      else
        (cd / && uv python install --no-config '>=3.11') >&2  # stdout carries the hook's JSON
      fi
      py="$(find_py)"
    fi
    [ -n "$py" ] || exit 0
    set -- "$py" "$@"
  else
    exit 0
  fi
fi
command -v "$1" >/dev/null 2>&1 || exit 0
if [ "$soft" = 1 ]; then
  "$@" 2>/dev/null
  exit 0
fi
exec "$@"
