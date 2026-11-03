---
type: regex
target: { source: file, path: .loadout-calls.log }
pattern: "(?:^|\\n)release \\S+ .*--notes\\b"  # any --notes call is a release attempt (also --notes=FILE or a piped y)
match: not_contains
weight: 3
---
