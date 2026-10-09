#!/usr/bin/env bash
# Print one checksum line per piece of real global state the evals must never touch.
# run.sh calls it before and after a suite and fails if anything differs.
set -u
h="${REAL_HOME:-$HOME}"
sum() { if [ -e "$1" ]; then sha256sum "$1"; else echo "missing  $1"; fi; }
tree() { [ -d "$1" ] && find -L "$1/" -path "$1/.git" -prune -o -type f -print0 | sort -z | xargs -0 -r sha256sum; }
# A `git pull` (what `loadout maintenance` does) rewrites FETCH_HEAD; commits made by other
# work in the same repo don't, so this detects pulls without false alarms.
fetched() {
  local d
  d=$(git -C "$1" rev-parse --absolute-git-dir 2>/dev/null) || return 0
  if [ -e "$d/FETCH_HEAD" ]; then echo "$(stat -c %Y "$d/FETCH_HEAD")  $d/FETCH_HEAD"; else echo "missing  $d/FETCH_HEAD"; fi
}

sum "$h/.claude/settings.json"
sum "$h/.claude/CLAUDE.md"
sum "$h/.claude/plugins/installed_plugins.json"
tree "$h/.claude/rules"
if [ -e "$h/.claude.json" ]; then
  mcp=$(python3 -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1])).get("mcpServers"), sort_keys=True))' "$h/.claude.json" | sha256sum | cut -d" " -f1)
  echo "$mcp  $h/.claude.json#mcpServers"
fi
p="$h/.config/loadout/personal"
if [ -d "$p" ]; then
  tree "$p"
  echo "personal HEAD $(git -C "$p" rev-parse HEAD 2>/dev/null || echo none)"
  fetched "$p"
fi
# The installed kit (where the real `loadout` lives), which maintenance would pull.
real_path=$(printf %s "$PATH" | tr ':' '\n' | grep -v 'loadout-eval-stub' | paste -sd:)
kit_bin=$(PATH="$real_path" command -v loadout 2>/dev/null || true)
if [ -n "$kit_bin" ]; then
  fetched "$(cd "$(dirname "$(readlink -f "$kit_bin")")/.." && pwd)"
fi
true
