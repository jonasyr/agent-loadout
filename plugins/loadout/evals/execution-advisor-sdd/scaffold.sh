#!/usr/bin/env bash
# Fixture: the tasklog project (committed) with a freshly written implementation plan from
# this case's files/ overlay in docs/superpowers/plans/. Nothing is implemented yet.
case_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
. "$case_dir/../lib/common.sh"
install_rules
copy_fixture tasklog
copy_overlay "$case_dir"
printf '.venv/\n__pycache__/\n.claude/settings.local.json\n.serena/cache/\n' > .gitignore
git_commit_all "docs: implementation plan"
