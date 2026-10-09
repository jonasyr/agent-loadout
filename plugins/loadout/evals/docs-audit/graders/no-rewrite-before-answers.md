---
type: regex
target: trace
pattern: "\"name\":\\s*\"(?:Write|Edit|NotebookEdit)\",\\s*\"input\":\\s*\\{\\s*\"(?:file_path|notebook_path)\":\\s*\"(?![^\"]*(?:/\\.loadout/|/\\.gitignore\"))"
match: not_contains
weight: 2
---
