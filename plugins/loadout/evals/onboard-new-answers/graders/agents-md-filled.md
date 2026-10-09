---
type: regex
target: { source: file, path: AGENTS.md }
flags: s
pattern: "^(?!.*\\(One paragraph)(?!.*\\{\\{PROJECT_NAME\\}\\})(?=.*pantry)(?=.*expir)(?=.*uv run pytest|.*uv run python -m pytest).*$"
weight: 2
---
