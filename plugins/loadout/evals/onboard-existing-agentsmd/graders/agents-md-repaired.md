---
type: regex
target: { source: file, path: AGENTS.md }
flags: s
weight: 2
pattern: "^(?!.*pytest test/)(?!.*~/\\.tasklog\\b)(?!.*\\|\\s*Run\\s*\\|\\s*`python -m tasklog`)(?!.*pip install -e)(?=.*tests/|.*uv run pytest)(?=.*TASKLOG_HOME|.*\\.local/share/tasklog).*$"
---
