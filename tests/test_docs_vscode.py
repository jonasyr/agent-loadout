"""The VS Code how-to names every check row loadout prints, and the ADR and index exist (spec Part 4)."""
from pathlib import Path

from loadout import codex

ROOT = Path(__file__).resolve().parent.parent
HOWTO = ROOT / "docs/how-to/vscode.md"


def test_howto_names_every_vscode_check_row():
    text = HOWTO.read_text(encoding="utf-8")
    for name in ("VS Code (Codex)", "VS Code (Claude Code)", "Windows window", "Remote-WSL window", "VS Code PATH",
                 "repo .mcp.json", "VS Code settings"):
        assert name in text, name
    assert "Codex CLI alongside VS Code" in text


def test_adr_and_indexes_link_it():
    assert (ROOT / "docs/adr/0032-vscode-extensions-are-a-surface-of-an-agent.md").is_file()
    assert "0032-vscode-extensions-are-a-surface-of-an-agent.md" in (ROOT / "docs/adr/README.md").read_text(encoding="utf-8")
    assert "how-to/vscode.md" in (ROOT / "docs/README.md").read_text(encoding="utf-8")
    assert "vscode.md" in (ROOT / "docs/how-to/setups.md").read_text(encoding="utf-8")
    assert "`vscode.py`" in (ROOT / "AGENTS.md").read_text(encoding="utf-8")


def test_the_hooks_wording_in_the_docs_matches_the_code():
    text = HOWTO.read_text(encoding="utf-8")
    assert "hooks icon" in codex.HOOKS_EXTENSION and "Allow all" in codex.HOOKS_EXTENSION
    assert "hooks icon" in text and "Allow all" in text
    assert "Trust Folder & Continue" in text
    assert "plugins do not load" not in text


def test_agent_page_and_configure_skill_ask_about_vscode():
    page = (ROOT / "docs/how-to/install-with-an-agent.md").read_text(encoding="utf-8")
    assert "VS Code" in page.split("## 3.")[0] and "--without-codex-cli" in page
    skill = (ROOT / "plugins/loadout/skills/configure/SKILL.md").read_text(encoding="utf-8")
    assert "--without-codex-cli" in skill and "docs/how-to/vscode.md" in skill
    assert "--without-codex-cli" in (ROOT / "docs/reference/cli.md").read_text(encoding="utf-8")
    assert "## Codex in VS Code without the CLI" in HOWTO.read_text(encoding="utf-8")


def test_pr3_fixes_are_documented():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    howto = (root / "docs/how-to/vscode.md").read_text(encoding="utf-8")
    cli = (root / "docs/reference/cli.md").read_text(encoding="utf-8")
    trouble = (root / "docs/how-to/troubleshooting.md").read_text(encoding="utf-8")
    skill = (root / "plugins/loadout/skills/configure/SKILL.md").read_text(encoding="utf-8")
    assert "loadout bootstrap --vscode-path" in howto and "wsl --shutdown" in howto and "WSL: Restart" not in howto
    assert "bundled" in howto and "claude plugin" in howto
    assert "profile" in howto and ".vscode/settings.json" in howto
    assert "[--vscode-path]" in cli and "| `--vscode-path` |" in cli
    assert "`binary claude`" in trouble and "--vscode-path" in trouble
    assert "--vscode-path" in skill
