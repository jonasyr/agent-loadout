---
type: regex
target: trace
pattern: "\\.claude/projects/[^\"]*\\.jsonl|codex/sessions/"
match: not_contains
weight: 2
---
