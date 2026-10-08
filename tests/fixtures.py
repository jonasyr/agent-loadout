"""A fake of the author's machine as of 2026-10-08 (secrets replaced by fakes built at runtime)."""
import json
from pathlib import Path

FAKE_PAT = "github_pat_" + "A" * 40
FAKE_DEVIN = "apk_user_" + "B" * 40


def _w(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data) if not isinstance(data, str) else data, encoding="utf-8")


def author_machine(home: Path) -> None:
    _w(home / ".claude.json", {
        "mcpServers": {
            "MCP_DOCKER": {"command": "docker", "args": ["mcp", "gateway", "run"], "env": {"DEVIN_API_KEY": FAKE_DEVIN}},
            "github-server": {"type": "stdio", "command": "npx", "args": ["@modelcontextprotocol/server-github@latest", f"GITHUB_PERSONAL_ACCESS_TOKEN={FAKE_PAT}"], "env": {}},
            "omarchy-kb": {"type": "stdio", "command": "docker", "args": ["exec", "-i", "omarchy-mcp-server", "python", "/app/mcp_server/main.py"]},
            "serena": {"type": "stdio", "command": "serena", "args": ["start-mcp-server", "--context=claude-code", "--project-from-cwd"]},
            "codebase-memory-mcp": {"command": "/home/x/.local/bin/codebase-memory-mcp"},
            "sonarqube": {"command": "sonar", "args": ["run", "mcp"]},
        },
        "projects": {"/home/x/code/gitray": {"mcpServers": {"serena": {"command": "serena"}}}},
    })
    _w(home / ".claude/.mcp.json", {"mcpServers": {"codebase-memory-mcp": {"command": "/home/x/.local/bin/codebase-memory-mcp"}}})
    _w(home / ".claude/plugins/installed_plugins.json", {"version": 2, "plugins": {
        pid: [{"scope": "user", "version": "1"}] for pid in [
            "testing-suite@claude-code-templates", "documentation-generator@claude-code-templates",
            "frontend-design@claude-plugins-official", "superpowers@claude-plugins-official",
            "auto-memory@severity1-marketplace", "academic-research-skills@academic-research-skills",
            "sonarqube@claude-plugins-official", "mystery@somewhere"]}})
    _w(home / ".claude/plugins/known_marketplaces.json", {
        "claude-code-templates": {"source": {"source": "git", "url": "https://github.com/davila7/claude-code-templates.git"}},
        "claude-plugins-official": {"source": {"source": "github", "repo": "anthropics/claude-plugins-official"}},
        "severity1-marketplace": {"source": {"source": "github", "repo": "severity1/severity1-marketplace"}},
    })
    _w(home / ".claude/settings.json", {"hooks": {
        "PreToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "rtk hook claude"}]},
            {"matcher": "", "hooks": [{"type": "command", "command": "serena-hooks remind --client=claude-code"}]},
            {"matcher": "Read", "hooks": [{"type": "command", "command": "'/home/x/.claude/hooks/sonar-secrets/build-scripts/pretool-secrets.sh'"}]},
            {"matcher": "Edit", "hooks": [{"type": "command", "command": "my-own-linter"}]},
        ],
        "Stop": [{"hooks": [{"type": "command", "command": "python3 /home/x/.claude/plugins/cache/severity1-marketplace/auto-memory/0.9.2/scripts/trigger.py"}]}],
    }, "effortLevel": "medium"})
    skills = home / ".claude/skills"
    skills.mkdir(parents=True, exist_ok=True)
    agents = home / ".agents/skills/gpt-taste"
    agents.mkdir(parents=True)
    (agents / "SKILL.md").write_text("x")
    (skills / "gpt-taste").symlink_to(agents)
    (skills / "my-skill").mkdir()
    _w(home / ".claude/CLAUDE.md", "@RTK.md\n\n# Skill Check Rule\nAlways check skills.\n")
