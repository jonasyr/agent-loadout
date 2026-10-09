---
type: tool_used
tool: Bash
# pytest run as a command (not `import pytest`), unless only collected/--help/--version
input_match: "\"command\":\\s*\"(?:(?:[^\"\\\\]|\\\\.)*?[;&|]\\s*)?\\s*(?:\\w+=\\S*\\s+)*(?:uv\\s+run\\s+(?:[^\\s\";&|]+\\s+)*?|python3?\\s+-m\\s+|[^\\s\";&|]*\\.venv/bin/)?(?:pytest\\b(?!(?:[^\"\\\\]|\\\\.)*(?:--collect-only|--co\\b|--help|--version|-h\\b))|make\\s+(?!-(?:n|-dry-run|-just-print)\\b)(?:[^\\s\";&|]+\\s+)*?test\\b)"
min: 0
max: 0
arm: both
---
