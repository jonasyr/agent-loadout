#!/usr/bin/env bash
# Fixture: existing tasklog repo with an AGENTS.md that has wrong commands/paths
# (`pytest test/`, `python -m tasklog` has no __main__, data dir ~/.tasklog), CLAUDE.md is
# just `@AGENTS.md`, a project .mcp.json and .claude/settings.json that must stay unchanged,
# a Makefile with deploy/clean targets, and no docs/ and no Serena memories.
case_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
. "$case_dir/../lib/common.sh"
install_rules
copy_fixture tasklog
copy_overlay "$case_dir"
printf '.venv/\n__pycache__/\n.claude/settings.local.json\n.serena/cache/\n' > .gitignore
git_commit_all "feat: tasklog 0.3"
