"""adopt: a tool only Codex has goes into a personal profile, like a Claude Code one."""
import json

import pytest

from loadout import adopt, backup, codex, own, paths, targets
from loadout.inventory import Item, Verdict
from loadout.jsonio import load_json


@pytest.fixture
def codex_on(fake_home, monkeypatch):
    monkeypatch.setattr(targets, "codex_enabled", lambda: True)
    monkeypatch.setattr(targets, "claude_enabled", lambda: False)
    monkeypatch.setattr(codex, "apply_config", lambda bk, dry_run=False: [])
    monkeypatch.setattr(codex, "apply_skills", lambda bk: [])
    cfg = paths.codex_home() / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('[mcp_servers.mine]\ncommand = "m"\n')


def _skill(name="solo", link=False, tmp=None):
    path = paths.agents_skills() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if link:
        path.symlink_to(tmp, target_is_directory=True)
    else:
        path.mkdir()
        (path / "SKILL.md").write_text("---\nname: solo\ndescription: x\n---\n")
    return Verdict(Item("skill", name, name, str(path), {}), "own", "")


def _mcp(cfg=None, problem=""):
    return Verdict(Item("mcp", "mine", "m", codex.CONFIG_LOCATION, {"config": cfg, "problem": problem}), "own", "")


def test_codex_skill_folder_and_server_offer_project(codex_on, tmp_path):
    assert "project" in own.options(_skill().item)
    assert "project" in own.options(_mcp({"type": "stdio", "command": "m"}).item)
    target = tmp_path / "shared"
    target.mkdir()
    assert "project" not in own.options(_skill("linked", link=True, tmp=target).item)


def test_codex_skill_to_project_is_copied_and_moved_out(codex_on, fake_runner):
    v = _skill()
    bk = backup.Backup(description="t")
    out, _ = adopt.apply_own([(v, own.Choice("project", "mine"))], bk)
    assert (paths.personal_root() / "profiles" / "skills" / "solo" / "SKILL.md").is_file()
    assert load_json(paths.personal_root() / "profiles" / "mine.json")["skills"] == ["solo"]
    assert not (paths.agents_skills() / "solo").exists()
    assert any("~/.agents/skills" in l for l in out)


def test_codex_server_to_project_goes_into_the_profile_and_out_of_codex(codex_on, fake_runner):
    v = _mcp({"type": "stdio", "command": "m"})
    bk = backup.Backup(description="t")
    adopt.apply_own([(v, own.Choice("project", "mine"))], bk)
    profile = load_json(paths.personal_root() / "profiles" / "mine.json")
    assert profile["mcp"]["mcpServers"]["mine"] == {"type": "stdio", "command": "m"}
    assert ["codex", "mcp", "remove", "mine"] in fake_runner.calls
    assert any("config.toml" in s.get("label", "") for s in bk.steps)


def test_codex_server_that_cannot_be_expressed_is_refused(codex_on, fake_runner):
    rec = own.record_project(_mcp(None, "mcp mine: startup_timeout_sec has no Claude Code equivalent"),
                             "mine", backup.Backup(description="t"))
    assert not rec.ok and "startup_timeout_sec" in rec.lines[0]
    assert not (paths.personal_root() / "profiles" / "mine.json").exists()


def test_codex_server_already_in_the_profile_is_refused(codex_on, fake_runner):
    path = paths.personal_root() / "profiles" / "mine.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"mcp": {"mcpServers": {"mine": {"type": "stdio", "command": "other"}}}}))
    rec = own.record_project(_mcp({"type": "stdio", "command": "m"}), "mine", backup.Backup(description="t"))
    assert not rec.ok and "already exists" in rec.lines[0]


def test_codex_server_whose_secret_would_be_renamed_is_refused_like_global(codex_on, fake_runner):
    """Codex forwards a variable only under its own name: API_KEY cannot become ${MINE_API_KEY}."""
    token = "ghp_" + "Z" * 36
    v = _mcp({"type": "stdio", "command": "m", "env": {"API_KEY": token}})
    rec = own.record_project(v, "mine", backup.Backup(description="t"))
    assert not rec.ok and "own name" in rec.lines[0] and token not in rec.lines[0]
    assert not (paths.personal_root() / "profiles" / "mine.json").exists()
    assert not paths.secrets_file().exists()
