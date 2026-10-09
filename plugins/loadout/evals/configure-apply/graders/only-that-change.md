---
type: regex
target: { source: file, path: .loadout-calls.log }
pattern: "configure set (?!plugin chrome-devtools-mcp@claude-plugins-official on\\n)"
match: not_contains
---
