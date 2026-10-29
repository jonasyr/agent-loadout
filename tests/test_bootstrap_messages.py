"""bootstrap messages say something new: what to do after a failed install, no repeated lines."""
from loadout import bootstrap, catalog, out, runner


def _failing_entry(fake_runner):
    entry = next(e for e in catalog.binaries() if e["status"] in ("core", "recommended") and not e.get("helper")
                 and not e.get("needs") and catalog.platform_cmds(e, "install"))
    fake_runner.missing.add(entry["id"])
    for cmd in catalog.platform_cmds(entry, "install"):
        fake_runner.responses[tuple(cmd[:2])] = runner.Result(1, "", "network down")
    return entry


def test_failed_install_does_not_say_rerun_with_install(fake_home, fake_runner):
    entry = _failing_entry(fake_runner)
    notes = []
    bootstrap.check_prereqs(True, lambda q: "", notes=notes)
    line = next(n for n in notes if n.startswith("missing") and entry["id"] in n)
    assert "re-run with --install" not in line
    assert entry.get("manual", bootstrap.INSTALL_FAILED_HINT) in line or "fix that" in line or "by hand" in line


def test_missing_without_install_still_says_rerun(fake_home, fake_runner):
    _failing_entry(fake_runner)
    notes = []
    bootstrap.check_prereqs(False, lambda q: "", notes=notes)
    assert any("re-run with --install" in n for n in notes if n.startswith("missing"))


def test_this_machine_does_not_repeat_missing(fake_home, fake_runner, monkeypatch, capsys):
    monkeypatch.setattr(out, "VERBOSE", False)
    (fake_home / ".config/loadout/personal").mkdir(parents=True)
    fake_runner.missing.add("serena")
    bootstrap.bootstrap(install=False, yes=True, plugins=False, adopt_step=False, ask=lambda q: "", interactive=False)
    text = capsys.readouterr().out
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if "This machine" in l)
    end = next(i for i, l in enumerate(lines) if "Prerequisites" in l)
    assert "missing and no --install" not in "\n".join(lines[start:end])


def test_report_prints_a_problem_once(capsys):
    bootstrap._report("codebase-memory", "could not read auto_index (config get failed)",
                      ["codebase-memory: could not read auto_index (config get failed)"])
    assert capsys.readouterr().out.count("could not read auto_index") == 1
