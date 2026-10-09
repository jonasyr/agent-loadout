---
type: tool_used
tool: Bash
# shell writes (>, >>, sed -i, perl -i, tee, cp/mv target, rm) to a doc file other than docs/reference/cli.md
input_match: "\"command\":\\s*\"(?:[^\"\\\\]|\\\\.)*?(?:>>?\\s*|\\b(?:sed|perl)\\s+(?:-[^\\s\"\\\\;&|]*\\s+)*-[a-zA-Z]*i[^\\s\"\\\\;&|]*\\s+(?:[^\\s\"\\\\;&|]+\\s+)*?|\\btee\\s+(?:-a\\s+)?|\\b(?:cp|mv)\\s+(?:-[^\\s\"\\\\;&|]+\\s+)*(?:[^\\s\"\\\\;&|]+\\s+)+|\\brm\\s+(?:-[^\\s\"\\\\;&|]+\\s+)*)(?!docs/reference/cli\\.md)[^\\s\"\\\\;&|<>]*(?:\\.md|docs/[^\\s\"\\\\;&|<>]*)(?=[\\s\"\\\\;&|)]|$)"
min: 0
max: 0
arm: both
---
