---
type: regex
target: { source: file, path: .loadout-calls.log }
pattern: "(?:^|\\n)release \\S+ .*--notes\\b"
match: not_contains
weight: 3
---
