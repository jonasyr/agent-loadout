"""done_when: repo-relative paths that show a profile's commands are already done here (Task 4)."""
import json

import pytest

from loadout import profiles


def test_done_when_loaded():
    assert profiles.load_profile("web").done_when == [
        ".claude/skills/playwright-cli",
        ".agents/skills/playwright-cli",
    ]


@pytest.mark.parametrize("bad", ["/abs/path", "a/../b", "..", 7])
def test_done_when_rejects_absolute_and_dotdot(fake_home, bad):
    pdir = fake_home / ".config/loadout/personal/profiles"
    pdir.mkdir(parents=True)
    (pdir / "mine.json").write_text(json.dumps({"description": "m", "done_when": [bad]}))
    with pytest.raises(ValueError, match="done_when"):
        profiles.load_profile("mine")
