"""apply-settings never touches Claude Code's settings while Claude Code is turned off."""
import json

from loadout import paths
from loadout.__main__ import main


def test_apply_settings_skips_when_claude_code_is_off(fake_home, fake_runner, capsys):
    paths.personal_root().mkdir(parents=True)
    (paths.personal_root() / "targets.json").write_text(json.dumps({"claude": False, "codex": True}))
    assert main(["apply-settings"]) == 0
    assert not (fake_home / ".claude" / "settings.json").exists()
    assert "Claude Code is turned off" in capsys.readouterr().out


def test_apply_settings_still_merges_when_claude_code_is_on(fake_home, fake_runner):
    paths.personal_root().mkdir(parents=True)
    assert main(["apply-settings"]) == 0
    assert (fake_home / ".claude" / "settings.json").exists()
