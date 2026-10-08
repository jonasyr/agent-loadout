#!/usr/bin/env bash
# Set up loadout on this machine. All logic lives in `loadout bootstrap`.
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "loadout needs python3 (>= 3.10). Install it and re-run." >&2
  exit 1
fi
exec python3 bin/loadout bootstrap "$@"
