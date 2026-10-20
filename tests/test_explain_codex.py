"""`loadout explain ~/.codex/config.toml` and `~/.codex/hooks.json`: which entries are loadout's and which are
yours, read-only (plan 2026-10-20, item 10)."""
import json

import pytest

from loadout import backup, codex, codex_hooks, paths
from loadout.explain import explain


def _codex_on(on=True):
    paths.personal_root().mkdir(parents=True, exist_ok=True)
    (paths.personal_root() / "targets.json").write_text(json.dumps({"claude": True, "codex": on}))


def _personal_mcp(servers):
    (paths.personal_root() / "mcp.json").write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")


def _cfg():
    return paths.codex_home() / "config.toml"


def _setup():
    _codex_on()
    _personal_mcp({"gh": {"command": "gh-mcp", "env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}"}}})
    codex.apply_config(backup.Backup(description="t"))
    _cfg().write_bytes(_cfg().read_bytes().replace(b'command = "gh-mcp"', b'command = "gh-mcp-mine"')
                       .replace(b'model_reasoning_effort = "medium"', b'model_reasoning_effort = "high"'))


def test_explain_names_loadouts_entries_and_yours_without_writing(fake_home, fake_runner, capsys):
    _setup()
    cfg, record = _cfg().read_bytes(), codex.record_path().read_bytes()
    backups = paths.state_dir() / "backups"
    taken = sorted(backups.iterdir()) if backups.exists() else []
    assert explain(str(_cfg())) == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert any("mcp serena" in l and "loadout's value" in l for l in lines)
    assert any("mcp gh" in l and "changed by you" in l for l in lines)
    assert any("model_reasoning_effort" in l and "changed by you" in l for l in lines)
    assert any("tui.notifications" in l and "loadout's value" in l for l in lines)
    assert "gh-mcp-mine" not in out and "GITHUB_TOKEN" not in out  # names only, never a table's text
    assert _cfg().read_bytes() == cfg and codex.record_path().read_bytes() == record
    assert (sorted(backups.iterdir()) if backups.exists() else []) == taken  # no backup: nothing changed


def test_explain_with_a_tilde_and_a_released_entry(fake_home, fake_runner, capsys, monkeypatch):
    from loadout import maintenance
    monkeypatch.setattr(maintenance, "_spawn_background", lambda: None)
    _setup()
    maintenance.session_start(0)  # records gh and model_reasoning_effort as yours
    assert explain("~/.codex/config.toml", cwd=fake_home) == 0
    lines = capsys.readouterr().out.splitlines()
    assert any("mcp gh" in l and "yours" in l for l in lines)
    assert any("model_reasoning_effort" in l and "yours" in l for l in lines)


def test_explain_hooks_json_names_loadouts_hooks(fake_home, fake_runner, capsys):
    _codex_on()
    codex_hooks.apply(backup.Backup(description="t"))
    data = json.loads(codex_hooks.path().read_text())
    data["hooks"]["SessionEnd"][0]["hooks"][0]["timeout"] = 9  # your edit of one of loadout's entries
    codex_hooks.path().write_text(json.dumps(data, indent=2) + "\n")
    before = codex_hooks.path().read_bytes()
    assert explain(str(codex_hooks.path())) == 0
    lines = capsys.readouterr().out.splitlines()
    assert any("PreToolUse" in l and "serena-hooks remind" in l and "loadout's entry" in l for l in lines)
    assert any("SessionEnd" in l and "serena-hooks cleanup" in l and "changed or removed by you" in l for l in lines)
    assert codex_hooks.path().read_bytes() == before


def test_explain_with_codex_off_reads_no_codex_file(fake_home, fake_runner, capsys, monkeypatch):
    _setup()
    _codex_on(False)
    monkeypatch.setattr(codex, "_tomllib", lambda: pytest.fail("Codex is off: config.toml must not be read"))
    real_read = type(_cfg()).read_bytes

    def guarded(self):
        if paths.inside(self, paths.codex_home()):
            pytest.fail(f"Codex is off: {self} must not be read")
        return real_read(self)
    monkeypatch.setattr(type(_cfg()), "read_bytes", guarded)
    assert explain(str(_cfg())) == 0
    out = capsys.readouterr().out
    assert "Codex is off" in out and "mcp gh" in out and "as recorded" in out
