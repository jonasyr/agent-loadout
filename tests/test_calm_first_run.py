"""A calmer first run: in-place progress for slow steps, no unexplained lines, a short init summary."""
import io

import pytest

from loadout import bootstrap, configure, inventory, out, own, paths, project, runner


@pytest.fixture
def calm(monkeypatch):
    monkeypatch.setattr(out, "VERBOSE", False)


class Tty(io.StringIO):
    def isatty(self):
        return True


def test_progress_replaces_itself_on_a_terminal(calm, monkeypatch):
    term = Tty()
    monkeypatch.setattr("sys.stdout", term)
    out.progress("  plugin a@b (1 of 2)…")
    out.progress("  plugin c@d (2 of 2)…")
    out.status("Plugins", "2 kit plugins ready")
    text = term.getvalue()
    assert "\n  plugin" not in text  # never a line of its own
    assert text.rstrip("\n").endswith("Plugins            2 kit plugins ready")
    final = text.split("\r")[-1]  # what stays on screen: the status line, the progress cleared
    assert "plugin c@d" not in final


def test_progress_is_a_normal_line_off_a_terminal_and_with_verbose(monkeypatch, capsys):
    monkeypatch.setattr(out, "VERBOSE", False)
    out.progress("  plugin a@b (1 of 1)…")  # capsys: not a terminal (logs, CI)
    assert capsys.readouterr().out == "  plugin a@b (1 of 1)…\n"
    term = Tty()
    monkeypatch.setattr("sys.stdout", term)
    monkeypatch.setattr(out, "VERBOSE", True)
    out.progress("  plugin a@b (1 of 1)…")
    assert term.getvalue() == "  plugin a@b (1 of 1)…\n"


def test_setup_plugins_counts_its_steps(fake_home, fake_runner):
    paths.personal_root().mkdir(parents=True)
    fake_runner.responses[("claude", "plugin", "marketplace", "list")] = runner.Result(0, "", "")
    said = []
    bootstrap.setup_plugins(say=said.append)
    total = len(said)
    assert total > 2
    assert said[0].endswith(f"(1 of {total})…") and said[-1].endswith(f"({total} of {total})…")
    assert sum("can take a few minutes" in line for line in said) == 0


def test_quick_preferences_do_not_print_the_auto_mode_line(fake_home, calm, capsys):
    paths.personal_root().mkdir(parents=True)
    from loadout.backup import Backup
    configure.ask_preferences(lambda q: "", fill_defaults=True, interactive=True, bk=Backup(description="t"), quick=True)
    assert "auto mode" not in capsys.readouterr().out


def test_quick_preferences_name_auto_mode_with_verbose(fake_home, monkeypatch, capsys):
    monkeypatch.setattr(out, "VERBOSE", True)
    paths.personal_root().mkdir(parents=True)
    from loadout.backup import Backup
    configure.ask_preferences(lambda q: "", fill_defaults=True, interactive=True, bk=Backup(description="t"), quick=True)
    assert "auto mode" in capsys.readouterr().out


def _init_web(tmp_path, fake_runner):
    proj = tmp_path / "app"
    proj.mkdir()
    (proj / ".git").mkdir()
    (proj / "package.json").write_text('{"dependencies": {"react": "19"}}')
    return proj, project.init(proj, ["web"], yes=True, install=True, dry_run=False, ask=lambda q: "", interactive=False)


def test_init_prints_a_short_summary(fake_home, fake_runner, calm, tmp_path, capsys):
    proj, rc = _init_web(tmp_path, fake_runner)
    text = capsys.readouterr().out
    assert rc == 0
    lines = [line for line in text.splitlines() if line.strip()]
    assert any(line.startswith("✓ Profile web") for line in lines), text
    assert any(line.startswith("✓ Scaffold") and "AGENTS.md" in line for line in lines), text
    assert "running:" not in text and str(proj) not in text and "note (web)" not in text
    assert lines[-1].startswith("next: ")
    assert len(lines) <= 5, text


def test_init_shows_a_failed_command_in_calm_mode(fake_home, fake_runner, calm, tmp_path, capsys):
    fake_runner.responses[("playwright-cli",)] = runner.Result(1, "", "no network")
    _, rc = _init_web(tmp_path, fake_runner)
    text = capsys.readouterr().out
    assert rc == 1
    assert "failed: no network" in text
    assert any(line.startswith("! Profile web") for line in text.splitlines()), text


def test_init_with_verbose_keeps_the_details(fake_home, fake_runner, tmp_path, capsys):
    proj, _ = _init_web(tmp_path, fake_runner)  # the autouse fixture sets VERBOSE
    text = capsys.readouterr().out
    assert "running: playwright-cli" in text and "created AGENTS.md" in text and "note (web)" in text


def test_own_tools_prompt_is_short_and_capitalised(capsys):
    asked = []
    item = inventory.Item("mcp", "team-notes")
    own.ask_choices([inventory.Verdict(item, "own", "")], lambda q: asked.append(q) or "c" if len(asked) == 0 else "")
    assert asked[0].startswith("Your own tools: ")
    legend = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert legend and all(len(line) <= 80 for line in legend), legend


def test_profile_verbose_flag_prints_the_details(fake_home, fake_runner, calm, tmp_path, monkeypatch, capsys):
    from loadout.__main__ import main
    proj = tmp_path / "app"
    proj.mkdir()
    monkeypatch.chdir(proj)
    assert main(["profile", "--verbose", "web"]) == 0
    assert "running: playwright-cli" in capsys.readouterr().out
