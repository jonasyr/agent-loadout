#!/usr/bin/env bash
# Fixture: a fresh repo right after `loadout init` — only skeletons, README, LICENSE, .gitignore.
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
install_rules
loadout_init_skeleton pantry
printf '# pantry\n' > README.md
printf 'MIT License\n\nCopyright (c) 2026 Eval User\n' > LICENSE
printf '.claude/settings.local.json\n.serena/cache/\n' > .gitignore
git_commit_all "chore: loadout init"
