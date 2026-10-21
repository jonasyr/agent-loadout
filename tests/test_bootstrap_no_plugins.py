"""bootstrap --no-plugins leaves Codex's marketplaces and plugins alone too (live-tour fixes, spec fix 2)."""
import pytest

from loadout import bootstrap, codex, paths, runner


def test_no_plugins_skips_codex_marketplaces_and_plugins(fake_home, fake_runner):
    (fake_home / ".config/loadout/personal").mkdir(parents=True)
    codex.set_enabled(True)
    fake_runner.responses[("codex", "--version")] = runner.Result(0, "codex-cli 0.162.1\n", "")
    assert codex.unavailable() is None  # Codex is on and present
    bootstrap.bootstrap(install=False, yes=True, plugins=False, adopt_step=False,
                        ask=lambda q: pytest.fail("asked"), interactive=False, agents="codex")
    # The health check at the end still reads `codex plugin list`; nothing adds, installs or upgrades.
    assert not [c for c in fake_runner.calls if c[:2] == ["codex", "plugin"] and c[2:3] != ["list"]]
    assert codex.START in (paths.codex_home() / "AGENTS.md").read_text(encoding="utf-8")  # the rules block was written
