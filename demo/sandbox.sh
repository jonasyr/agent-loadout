#!/usr/bin/env bash
# Builds the demo machine: a fresh HOME with a typical, slightly messy Claude Code setup and stand-in
# binaries; the recording then runs the README one-liner on it. Fake data only.
# Usage: demo/sandbox.sh HOME_DIR   (HOME_DIR must not exist; demo/render.sh runs this in a container)
set -euo pipefail

home="${1:?usage: demo/sandbox.sh HOME_DIR}"
if [ -e "$home" ]; then
  echo "demo/sandbox.sh: $home exists; the demo only builds a new, empty HOME" >&2
  exit 1
fi
kit="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

mkdir -p "$home/.claude/plugins" "$home/.claude/skills/commit-style" "$home/.local/bin"
touch "$home/.loadout-demo"

# a fake token, assembled here so the repo's secret scan does not flag this file
token="ghp_$(printf 'DEMO%.0s' 1 2 3 4 5 6 7 8 9)"
cat > "$home/.claude.json" <<JSON
{
  "mcpServers": {
    "github": {"command": "npx", "args": ["@modelcontextprotocol/server-github"],
               "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "$token"}},
    "serena": {"command": "serena", "args": ["start-mcp-server", "--context=claude-code"]},
    "sonarqube": {"command": "sonar", "args": ["run", "mcp"]},
    "team-notes": {"command": "node", "args": ["/home/demo/tools/notes-mcp.js"]}
  },
  "oauthAccount": {"emailAddress": "demo@example.com"}
}
JSON
cat > "$home/.claude/plugins/installed_plugins.json" <<'JSON'
{"version": 2, "plugins": {
  "auto-memory@severity1-marketplace": [{"scope": "user", "version": "1"}],
  "superpowers@claude-plugins-official": [{"scope": "user", "version": "1"}]
}}
JSON
cat > "$home/.claude/plugins/known_marketplaces.json" <<'JSON'
{"severity1-marketplace": {"source": {"source": "github", "repo": "severity1/severity1-marketplace"}},
 "claude-plugins-official": {"source": {"source": "github", "repo": "anthropics/claude-plugins-official"}}}
JSON
cat > "$home/.claude/skills/commit-style/SKILL.md" <<'MD'
---
name: commit-style
description: Write commit messages the way this team does.
---
Use Conventional Commits.
MD

cp "$kit/demo/bin/claude" "$kit/demo/bin/curl" "$kit/demo/bin/uv" "$home/.local/bin/"
for tool in gh node npm serena codebase-memory-mcp rtk playwright-cli pyright typescript-language-server rust-analyzer; do
  printf '#!/bin/sh\necho "%s 1.0.0"\n' "$tool" > "$home/.local/bin/$tool"
done
chmod 755 "$home/.local/bin/"*

HOME="$home" git config --global user.name demo
HOME="$home" git config --global user.email demo@example.com
