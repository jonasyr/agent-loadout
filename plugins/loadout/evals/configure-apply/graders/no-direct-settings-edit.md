---
type: regex
target: trace
pattern: "\"name\":\\s*\"(?:Write|Edit)\",\\s*\"input\":\\s*\\{\\s*\"file_path\":\\s*\"[^\"]*(?:settings(?:\\.local)?\\.json|\\.claude\\.json|\\.mcp\\.json|loadout/personal)|\"name\":\\s*\"Bash\",\\s*\"input\":\\s*\\{\\s*\"command\":\\s*\"[^\"]*(?:claude\\s+(?:mcp|plugin)\\s+(?:add|install|enable|remove)|(?:>|tee|sed\\s+-i|jq\\b[^\"]*>)[^\"]*(?:settings\\.json|\\.claude\\.json))"
match: not_contains
weight: 2
---
