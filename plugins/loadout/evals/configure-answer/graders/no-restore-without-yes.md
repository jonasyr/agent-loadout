---
type: regex
target: { source: file, path: .loadout-calls.log }
pattern: "(?:^|\\n)restore (?!--list)\\S"
match: not_contains
weight: 2
---
