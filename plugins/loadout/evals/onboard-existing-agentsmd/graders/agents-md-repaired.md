---
type: regex
target: { source: file, path: AGENTS.md }
weight: 2
# wrong commands/paths must be gone where AGENTS.md uses them (command cells, the old data-location
# sentence); warnings such as "not ~/.tasklog" or "don't use pip install -e" are fine
pattern: "^(?![\\s\\S]*(?:^|\\n)\\|[^|\\n]*\\|\\s*`?(?:pip install -e|pytest test/|python -m tasklog)\\b)(?![\\s\\S]*Data lives in `~/\\.tasklog)(?=[\\s\\S]*(?:tests/|uv run pytest))(?=[\\s\\S]*(?:TASKLOG_HOME|\\.local/share/tasklog))"
---
