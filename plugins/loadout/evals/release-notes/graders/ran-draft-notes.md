---
type: regex
target: { source: file, path: .loadout-calls.log }
pattern: "(?:^|\\n)release 0\\.3\\.0 --draft-notes \\S+"
weight: 2
---
