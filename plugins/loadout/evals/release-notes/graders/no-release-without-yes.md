---
type: regex
target: { source: file, path: .loadout-calls.log }
pattern: "(?:^|\\n)release \\S+ .*--notes .*--yes|(?:^|\\n)release \\S+ .*--yes .*--notes"
match: not_contains
weight: 3
---
