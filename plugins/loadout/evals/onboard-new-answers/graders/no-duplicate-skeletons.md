---
type: regex
target: files
flags: im
pattern: "(?:^|/)(?:AGENTS|CLAUDE)[-_. ]\\w*\\.md$|docs/(?:index|README[-_.]\\w+)\\.md$|docs/adr/README[-_.]\\w+\\.md$"
match: not_contains
---
