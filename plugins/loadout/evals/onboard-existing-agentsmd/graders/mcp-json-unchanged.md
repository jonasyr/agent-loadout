---
type: regex
target: { source: file, path: .mcp.json }
pattern: "^\\{\n  \"mcpServers\": \\{\n    \"tasks-db\": \\{\n      \"command\": \"uvx\",\n      \"args\": \\[\"mcp-server-sqlite\", \"--db-path\", \"dev\\/tasks\\.db\"\\]\n    \\}\n  \\}\n\\}\n$(?![\\s\\S])"
weight: 1
---
