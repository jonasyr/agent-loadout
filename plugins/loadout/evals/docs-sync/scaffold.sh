#!/usr/bin/env bash
# Fixture: tasklog with accurate, layered docs (committed), then an uncommitted feature
# change: the title limit goes from 120 to 200 characters. Only docs/reference/cli.md
# owns that fact. docs/architecture.md carries an unrelated stale sentence ("oldest
# first"; the code sorts newest first) that docs-sync must not silently rewrite.
case_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
. "$case_dir/../lib/common.sh"
install_rules
copy_fixture tasklog
copy_overlay "$case_dir"
printf '.venv/\n__pycache__/\n.claude/settings.local.json\n.serena/cache/\n' > .gitignore
git_commit_all "feat: tasklog 0.3"
git checkout -q -b feature/longer-titles
sed -i 's/^MAX_TITLE_LEN = 120$/MAX_TITLE_LEN = 200/' src/tasklog/store.py
grep -q '^MAX_TITLE_LEN = 200$' src/tasklog/store.py
