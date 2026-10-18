"""The VS Code how-to names every check row loadout prints, and the ADR and index exist (spec Part 4)."""
from pathlib import Path

from loadout import check

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


def test_the_gap_message_in_the_docs_matches_the_code():
    assert "plugins do not load in VS Code's Codex extension" in check.CODEX_GAP
    assert "plugins do not load" in HOWTO.read_text(encoding="utf-8")
