---
type: regex
target: { source: file, path: AGENTS.md }
flags: s
pattern: "^(?=.*pantry)(?=.*expir)(?=.*uv run pytest|.*uv run python -m pytest).*$"
weight: 2
---
