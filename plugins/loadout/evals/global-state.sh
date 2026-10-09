#!/usr/bin/env bash
# Print one checksum line per piece of real global state the evals must never touch.
# run.sh calls it before and after a suite and fails if anything differs.
# Deliberately not covered, because the user's normal work changes them during a run and
# would cause false alarms: ~/.claude/rules (symlinked into the kit checkout),
# plugins/installed_plugins.json and known_marketplaces.json (marketplace auto-update),
# and the kit/personal FETCH_HEAD (the user's own sessions run `loadout maintenance`).
set -u
h="${REAL_HOME:-$HOME}"
sum() { if [ -e "$1" ]; then sha256sum "$1"; else echo "missing  $1"; fi; }

sum "$h/.claude/settings.json"
sum "$h/.claude/CLAUDE.md"
if [ -e "$h/.claude.json" ]; then
  mcp=$(python3 -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1])).get("mcpServers"), sort_keys=True))' "$h/.claude.json" | sha256sum | cut -d" " -f1)
  echo "$mcp  $h/.claude.json#mcpServers"
fi
p="$h/.config/loadout/personal"
if [ -d "$p" ]; then
  find -L "$p/" -path "$p/.git" -prune -o -type f -print0 | sort -z | xargs -0 -r sha256sum
  echo "personal HEAD $(git -C "$p" rev-parse HEAD 2>/dev/null || echo none)"
fi
true
