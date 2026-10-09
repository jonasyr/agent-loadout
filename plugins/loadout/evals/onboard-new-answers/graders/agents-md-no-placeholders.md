---
type: regex
target: { source: file, path: AGENTS.md }
flags: m
pattern: "\\(One paragraph|\\(Hard rules only|\\{\\{PROJECT_NAME\\}\\}|Run `/loadout:onboard` to fill it in|^\\|\\s*(?:Install|Test|Run)\\s*\\|\\s*\\|\\s*$"
match: not_contains
weight: 2
---
