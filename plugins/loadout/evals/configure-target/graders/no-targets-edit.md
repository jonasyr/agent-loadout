---
type: regex
target: trace
pattern: "\"name\":\\s*\"(?:Write|Edit)\",\\s*\"input\":\\s*\\{\\s*\"file_path\":\\s*\"[^\"]*(?:targets\\.json|\\.codex/)"
match: not_contains
---
