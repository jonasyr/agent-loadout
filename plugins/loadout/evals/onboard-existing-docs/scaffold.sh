#!/usr/bin/env bash
# Fixture: existing tasklog repo that already has layered docs (docs/, AGENTS.md,
# CLAUDE.md = @AGENTS.md) and a Serena memory - the same files as the docs-sync case,
# without its uncommitted change. Onboarding must leave docs and memories alone and
# recommend /loadout:docs-audit instead of rewriting them.
case_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
. "$case_dir/../lib/common.sh"
install_rules
copy_fixture tasklog
copy_overlay "$EVALS_DIR/docs-sync"
printf '.venv/\n__pycache__/\n.claude/settings.local.json\n.serena/cache/\n' > .gitignore
git_commit_all "feat: tasklog 0.3"
