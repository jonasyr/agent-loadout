#!/usr/bin/env bash
# Runs the Codex part of loadout against the real codex CLI in a throwaway HOME and CODEX_HOME, then lists what Codex
# sees. Never touches your real ~/.codex. Needs codex on PATH and network access (marketplaces are git clones).
# Usage: dev/codex-sandbox.sh   (KEEP=1 keeps the sandbox folder)
set -euo pipefail
kit="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
sandbox="$(mktemp -d)"
[ -n "${KEEP:-}" ] || trap 'rm -rf "$sandbox"' EXIT
export HOME="$sandbox/home" CODEX_HOME="$sandbox/home/.codex" LOADOUT_PERSONAL="$sandbox/home/.config/loadout/personal"
mkdir -p "$CODEX_HOME" "$LOADOUT_PERSONAL/rules"
printf '# About me\n\n- Answers: concise.\n' > "$LOADOUT_PERSONAL/rules/me.md"
printf '{"codex": true}\n' > "$LOADOUT_PERSONAL/targets.json"
PYTHONPATH="$kit/cli" python3 - <<'PY'
from loadout import backup, codex
for line in codex.apply_all(backup.Backup(description="sandbox")):
    print(line)
PY
echo "--- plugins"; codex plugin list --json
echo "--- mcp"; codex mcp list --json
echo "--- AGENTS.md (head)"; head -5 "$CODEX_HOME/AGENTS.md"
echo "--- config.toml"; cat "$CODEX_HOME/config.toml"
echo "sandbox: $sandbox"
