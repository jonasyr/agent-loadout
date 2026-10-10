---
type: regex
target: trace
# the advisor only recommends: no file edits and no subagents before the user chose
pattern: "\"name\":\\s*\"(?:Write|Edit|MultiEdit|NotebookEdit|Agent|Task)\",\\s*\"input\""
match: not_contains
---
