---
type: regex
target: { source: file, path: .loadout-calls.log }
pattern: "(?:^|\\n)usage (?:--days 14 )?--json|(?:^|\\n)usage --json"
weight: 2
---
