---
type: regex
target: trace
match: not_contains
weight: 2
pattern: "\"name\":\\s*\"(?:Write|Edit|NotebookEdit)\",\\s*\"input\":\\s*\\{\\s*\"(?:file_path|notebook_path)\":\\s*\"[^\"]*(?:/docs/|/\\.serena/)"
---
