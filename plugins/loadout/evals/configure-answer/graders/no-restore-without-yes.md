---
type: regex
target: { source: file, path: .loadout-calls.log }
pattern: "^restore (?!--list)\\S"
match: not_contains
weight: 2
---
