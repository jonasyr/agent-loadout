---
type: regex
target: { source: file, path: .claude/settings.json }
pattern: "^\\{\n  \"permissions\": \\{\n    \"allow\": \\[\"Bash\\(uv run pytest:\\*\\)\", \"Bash\\(uv run tasklog:\\*\\)\"\\]\n  \\}\n\\}\n$(?![\\s\\S])"
weight: 1
---
