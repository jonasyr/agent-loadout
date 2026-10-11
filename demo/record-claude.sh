#!/usr/bin/env bash
# Records demo/claude-clip.mp4: the real Claude Code with your loadout setup, in a new project at /tmp/loadout-demo/my-app.
# Run it yourself: it uses your Claude Code login and a little plan usage (/loadout:onboard asks its first question).
# Watch the clip before committing it: it shows your plugins and paths. Then run demo/render.sh.
# Needs vhs on this machine and the JetBrains Mono font.
set -euo pipefail
kit="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
demo=/tmp/loadout-demo
command -v vhs >/dev/null || { echo "needs vhs (Arch: sudo pacman -S vhs; others: https://github.com/charmbracelet/vhs)" >&2; exit 1; }
fc-list : family 2>/dev/null | grep -i "JetBrains Mono" >/dev/null || { echo "needs the JetBrains Mono font (Arch: sudo pacman -S ttf-jetbrains-mono)" >&2; exit 1; }
# the same path every run, so Claude Code's folder trust is asked only once; only a folder this script made is replaced
if [ -e "$demo" ] && [ ! -f "$demo/.loadout-demo-clip" ]; then
  echo "$demo exists and was not made by this script; move it away first" >&2
  exit 1
fi
rm -rf "$demo"
mkdir -p "$demo/my-app"
touch "$demo/.loadout-demo-clip"
(cd "$demo/my-app" && git init -q && loadout init --yes --no-install >/dev/null && git add -A && git commit -qm "loadout init")
cd "$kit"
vhs demo/claude.tape
echo "wrote demo/claude-clip.mp4: watch it, then run demo/render.sh"
