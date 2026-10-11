#!/usr/bin/env bash
# Records demo/claude-clip.mp4: the real Claude Code with your loadout setup, in a throwaway project in /tmp.
# Run it yourself: it uses your Claude Code login and a little plan usage (/loadout:onboard starts working).
# Watch the clip before committing it: it shows your plugins and paths. Then run demo/render.sh.
# Needs vhs on this machine and the JetBrains Mono font.
set -euo pipefail
kit="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
command -v vhs >/dev/null || { echo "needs vhs (Arch: sudo pacman -S vhs; others: https://github.com/charmbracelet/vhs)" >&2; exit 1; }
fc-list 2>/dev/null | grep -qi "JetBrains Mono" || { echo "needs the JetBrains Mono font (Arch: sudo pacman -S ttf-jetbrains-mono)" >&2; exit 1; }
cd "$kit"
vhs demo/claude.tape
echo "wrote demo/claude-clip.mp4: watch it, then run demo/render.sh"
