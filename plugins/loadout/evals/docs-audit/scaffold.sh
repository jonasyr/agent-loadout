#!/usr/bin/env bash
# Fixture: tasklog (see fixtures/tasklog) with docs, AGENTS.md and Serena memories that
# contain planted errors. The graders check that each one is flagged:
#   P1 README: `export --format xml` (only json|csv exist)          -> wrong
#   P2 README: link to docs/usage.md (file does not exist)          -> broken link
#   P3 README: roadmap "[ ] JSON export" (implemented, the default)  -> stale
#   P4 docs/reference/cli.md: export default `csv` (code: json)     -> stale/wrong
#   P5 docs/configuration.md: env var TASKLOG_DIR (code: TASKLOG_HOME) -> wrong
#   P6 docs/architecture.md: class TaskRepository (code: Store)     -> wrong
#   P7 AGENTS.md: `uv run pytest test/` (dir is tests/), `make lint` (no Makefile) -> wrong
#   P8 .serena/memories/project_overview.md: copies the CLI reference (duplicated) and says
#      titles may be 200 characters (code and docs: 120)            -> duplicated/contradictory
# Genuinely ambiguous (must be asked, not decided):
#   A1 `list --all` "also shows archived tasks" (docs + memory) while the code parses --all
#      but ignores it, with a TODO saying the intent is undecided.
case_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
. "$case_dir/../lib/common.sh"
install_rules
copy_fixture tasklog
copy_overlay "$case_dir"
printf '.venv/\n__pycache__/\n.claude/settings.local.json\n.serena/cache/\n' > .gitignore
git_commit_all "feat: tasklog 0.3"
