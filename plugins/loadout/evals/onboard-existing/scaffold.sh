#!/usr/bin/env bash
# Fixture: existing Python project with real code, a CLAUDE.md with real content and no
# AGENTS.md (what `loadout init` leaves behind in that situation), plus a Makefile with
# targets that must never be run during onboarding (deploy, clean).
case_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
. "$case_dir/../lib/common.sh"
install_rules
copy_fixture tasklog
copy_overlay "$case_dir"
printf '.venv/\n__pycache__/\n.claude/settings.local.json\n.serena/cache/\n' > .gitignore
git_commit_all "feat: tasklog 0.3"
