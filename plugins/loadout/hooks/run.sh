#!/usr/bin/env bash
# Run a hook command only if its binary is installed, so a machine without a tool
# simply runs without that hook. With --soft, errors are swallowed (exit 0, no stderr).
soft=0
if [ "${1:-}" = "--soft" ]; then soft=1; shift; fi
command -v "$1" >/dev/null 2>&1 || exit 0
if [ "$soft" = 1 ]; then
  "$@" 2>/dev/null
  exit 0
fi
exec "$@"
