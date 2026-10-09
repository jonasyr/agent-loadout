---
type: regex
target: trace
weight: 2
pattern: "\"file_path\":\\s*\"[^\"]*docs/adr/0001-[^\"]*\\.md\",\\s*\"content\":\\s*\"(?=(?:[^\"\\\\]|\\\\.)*?#+ *Context\\b)(?=(?:[^\"\\\\]|\\\\.)*?#+ *Decision\\b)(?=(?:[^\"\\\\]|\\\\.)*?#+ *Consequences\\b)(?=(?:[^\"\\\\]|\\\\.)*?Status(?:[^\"\\\\]|\\\\.){0,40}?[Aa]ccepted)"
---
