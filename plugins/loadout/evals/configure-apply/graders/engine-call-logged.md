---
type: regex
target: { source: file, path: .loadout-calls.log }
pattern: "configure show\\n[\\s\\S]*configure set plugin chrome-devtools-mcp@claude-plugins-official on"
weight: 2
---
