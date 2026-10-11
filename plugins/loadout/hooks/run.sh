#!/usr/bin/env bash
# Run a hook command only if its binary is installed, so a machine without a tool
# simply runs without that hook. With --soft, errors are swallowed (exit 0, no stderr).
# With --python, the next argument is a Python script: run it with python3 (3.10+),
# else through uv, else skip the hook.
soft=0
if [ "${1:-}" = "--soft" ]; then soft=1; shift; fi
if [ "${1:-}" = "--python" ]; then
  shift
  if command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
    set -- python3 "$@"
  elif command -v uv >/dev/null 2>&1; then
    set -- uv run --no-project --python '>=3.10' "$@"
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
