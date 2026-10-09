#!/usr/bin/env bash
# Print one checksum line per piece of real global state the evals must never touch.
# run.sh calls it before and after a suite and fails if anything differs.
set -u
h="${REAL_HOME:-$HOME}"
sum() { if [ -e "$1" ]; then sha256sum "$1"; else echo "missing  $1"; fi; }
sum "$h/.claude/settings.json"
if [ -e "$h/.claude.json" ]; then
  mcp=$(python3 -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1])).get("mcpServers"), sort_keys=True))' "$h/.claude.json" | sha256sum | cut -d" " -f1)
  echo "$mcp  $h/.claude.json#mcpServers"
fi
p="$h/.config/loadout/personal"
if [ -d "$p" ]; then
  find -L "$p/" -path "$p/.git" -prune -o -type f -print0 | sort -z | xargs -0 -r sha256sum
  echo "personal HEAD $(git -C "$p" rev-parse HEAD 2>/dev/null || echo none)"
fi
