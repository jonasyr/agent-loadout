"""Package-manager-aware updates (mise, Homebrew) and remembered refusals."""
import json

from loadout import catalog, maintenance as m, paths, pkgmgr, runner, versions

MISE = "/home/u/.local/share/mise/installs"


def _entry(eid):
    return next(e for e in catalog.binaries() if e["id"] == eid)


def test_mise_install_path_uses_mise_upgrade_with_catalog_id(fake_home, fake_runner):
    fake_runner.paths["uv"] = f"{MISE}/uv/0.8.23/uv"
    cmds, how = pkgmgr.update_plan(_entry("uv"))
    assert (cmds, how) == ([["mise", "upgrade", "uv"]], "mise")


def test_mise_npm_backend_from_install_dir(fake_home, fake_runner):
    fake_runner.paths["pyright"] = f"{MISE}/npm-pyright/1.1.400/bin/pyright"
    assert pkgmgr.update_plan(_entry("pyright"))[0] == [["mise", "upgrade", "npm:pyright"]]


def test_mise_npm_scoped_package_uses_catalog_npm_name(fake_home, fake_runner):
    fake_runner.paths["playwright-cli"] = f"{MISE}/npm-playwright-cli/0.1.22/bin/playwright-cli"
    assert pkgmgr.update_plan(_entry("playwright-cli"))[0] == [["mise", "upgrade", "npm:@playwright/cli"]]


def test_mise_shim_resolved_with_mise_which(fake_home, fake_runner):
    fake_runner.paths["uv"] = "/home/u/.local/share/mise/shims/uv"
    fake_runner.responses[("mise", "which", "uv")] = runner.Result(0, f"{MISE}/uv/0.8.23/uv\n", "")
    assert pkgmgr.update_plan(_entry("uv"))[0] == [["mise", "upgrade", "uv"]]


def test_mise_override_in_entry(fake_home, fake_runner):
    entry = {**_entry("uv"), "mise": "aqua:astral-sh/uv"}
    fake_runner.paths["uv"] = f"{MISE}/aqua-astral-sh-uv/0.8.23/uv"
    assert pkgmgr.update_plan(entry)[0] == [["mise", "upgrade", "aqua:astral-sh/uv"]]


def test_windows_mise_path(fake_home, fake_runner):
    fake_runner.paths["uv"] = r"C:\Users\u\AppData\Local\mise\installs\uv\0.8.23\uv.exe"
    assert pkgmgr.update_plan(_entry("uv"))[0] == [["mise", "upgrade", "uv"]]


def test_brew_bin_link_into_cellar_uses_formula(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(paths, "platform_key", lambda: "posix")
    fake_runner.paths["gh"] = "/opt/homebrew/bin/gh"
    monkeypatch.setattr(pkgmgr, "_realpath", lambda p: "/opt/homebrew/Cellar/gh/2.60.0/bin/gh")
    assert pkgmgr.update_plan(_entry("gh")) == ([["brew", "upgrade", "gh"]], "brew")


def test_npm_global_under_brew_node_uses_catalog(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(paths, "platform_key", lambda: "posix")
    fake_runner.paths["pyright"] = "/opt/homebrew/bin/pyright"
    monkeypatch.setattr(pkgmgr, "_realpath", lambda p: "/opt/homebrew/lib/node_modules/pyright/index.js")
    fake_runner.responses[("brew", "--prefix")] = runner.Result(0, "/opt/homebrew\n", "")
    assert pkgmgr.update_plan(_entry("pyright")) == ([["npm", "install", "-g", "pyright@latest"]], "catalog")


def test_cask_uses_catalog(fake_home, fake_runner, monkeypatch):
    fake_runner.paths["claude"] = "/opt/homebrew/bin/claude"
    monkeypatch.setattr(pkgmgr, "_realpath", lambda p: "/opt/homebrew/Caskroom/claude-code/2.1.0/claude")
    assert pkgmgr.update_plan(_entry("claude")) == ([["claude", "update"]], "catalog")


def test_no_mise_on_path_means_no_mise(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(paths, "platform_key", lambda: "posix")
    fake_runner.missing.add("mise")
    fake_runner.paths["uv"] = f"{MISE}/uv/0.8.23/uv"
    assert pkgmgr.update_plan(_entry("uv"))[1] == "catalog"


def test_mise_commands_run_in_home_not_cwd(fake_home, fake_runner, monkeypatch):
    seen = []
    fake_runner.paths["uv"] = "/home/u/.local/share/mise/shims/uv"
    real = fake_runner.__call__

    def spy(cmd, cwd=None, timeout=300, env=None):
        seen.append((cmd[:2], cwd))
        return real(cmd, cwd, timeout, env)

    monkeypatch.setattr(runner, "run", spy)
    pkgmgr.mise_tool(_entry("uv"))
    assert (["mise", "which"], str(fake_home)) in seen


def test_brew_cellar_formula_name(fake_home, fake_runner, monkeypatch):
    fake_runner.paths["uv"] = "/home/linuxbrew/.linuxbrew/bin/uv"
    monkeypatch.setattr(pkgmgr, "_realpath", lambda p: "/home/linuxbrew/.linuxbrew/Cellar/uv-formula/0.8/bin/uv")
    assert pkgmgr.update_plan(_entry("uv"))[0] == [["brew", "upgrade", "uv-formula"]]


def test_unmanaged_falls_back_to_catalog(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(paths, "platform_key", lambda: "posix")
    fake_runner.paths["uv"] = "/home/u/.local/bin/uv"
    assert pkgmgr.update_plan(_entry("uv")) == ([["uv", "self", "update"]], "catalog")


def test_claude_defaults_to_claude_update(fake_home, fake_runner):
    fake_runner.paths["claude"] = "/home/u/.local/bin/claude"
    assert pkgmgr.update_plan(_entry("claude"))[0] == [["claude", "update"]]


def test_update_uses_package_manager_command(fake_home, fake_runner, monkeypatch, capsys):
    fake_runner.paths["uv"] = f"{MISE}/uv/0.8.23/uv"
    monkeypatch.setattr(m, "find_outdated", lambda: [(_entry("uv"), (0, 8, 23), (0, 9, 0))])
    monkeypatch.setattr(versions, "local_version", lambda e: (0, 9, 0))
    m.update(yes=True, ask=lambda q: "")
    assert ["mise", "upgrade", "uv"] in fake_runner.calls
    assert ["uv", "self", "update"] not in fake_runner.calls
    assert "via mise" in capsys.readouterr().out


def test_refused_update_is_remembered_and_not_renotified(fake_home, fake_runner, monkeypatch, capsys):
    monkeypatch.setattr(paths, "platform_key", lambda: "posix")
    entry = _entry("uv")
    fake_runner.paths["uv"] = "/home/u/.local/bin/uv"  # not managed: uv self update
    monkeypatch.setattr(m, "find_outdated", lambda: [(entry, (0, 8, 23), (0, 9, 0))])
    monkeypatch.setattr(versions, "local_version", lambda e: (0, 8, 23))  # the updater ran but installed nothing newer
    m.update(yes=True, ask=lambda q: "")
    assert "still 0.8.23" in capsys.readouterr().out
    state = json.loads((paths.state_dir() / "refused-updates.json").read_text())
    assert state == {"uv": "0.9.0"}

    monkeypatch.setattr(m, "pull_if_clean", lambda root: False)
    m.maintain(100.0)
    assert not (paths.state_dir() / "pending-notice").exists()

    monkeypatch.setattr(m, "find_outdated", lambda: [(entry, (0, 8, 23), (0, 9, 1))])  # newer than refused
    m.maintain(100.0 + m.WEEK)
    assert "uv 0.8.23 -> 0.9.1" in (paths.state_dir() / "pending-notice").read_text()


def test_successful_update_clears_refusal(fake_home, fake_runner, monkeypatch):
    entry = _entry("uv")
    (paths.state_dir()).mkdir(parents=True)
    (paths.state_dir() / "refused-updates.json").write_text('{"uv": "0.9.0"}')
    monkeypatch.setattr(m, "find_outdated", lambda: [(entry, (0, 8, 23), (0, 9, 1))])
    monkeypatch.setattr(versions, "local_version", lambda e: (0, 9, 1))
    m.update(yes=True, ask=lambda q: "")
    assert json.loads((paths.state_dir() / "refused-updates.json").read_text()) == {}


def test_adopt_update_group_uses_package_manager(fake_home, fake_runner, monkeypatch):
    from loadout import adopt, inventory
    entry = _entry("uv")
    fake_runner.paths["uv"] = f"{MISE}/uv/0.8.23/uv"
    item = inventory.Item("binary", "uv", "0.8.23 -> 0.9.0", "PATH", {"entry": entry, "state": "outdated"})
    out = adopt.apply([adopt.Verdict(item, "update", "", "uv")], __import__("loadout").backup.Backup(), confirm_cmds=False)
    assert ["mise", "upgrade", "uv"] in fake_runner.calls and "ok" in out[0]


def _mise_json(fake_runner, tool, payload, rc=0):
    fake_runner.responses[("mise", "outdated", tool, "--json")] = runner.Result(rc, json.dumps(payload), "")


def test_find_outdated_asks_mise_for_mise_tools(fake_home, fake_runner, monkeypatch):
    fake_runner.paths["uv"] = f"{MISE}/uv/0.8.23/uv"
    uv = _entry("uv")
    monkeypatch.setattr(m.catalog, "binaries", lambda: [uv])
    monkeypatch.setattr(versions, "latest_version", lambda e: (9, 9, 9))  # must not be consulted
    _mise_json(fake_runner, "uv", {"uv": {"name": "uv", "current": "0.8.23", "latest": "0.9.0"}})
    assert [(e["id"], a, b) for e, a, b in m.find_outdated()] == [("uv", (0, 8, 23), (0, 9, 0))]
    _mise_json(fake_runner, "uv", {})  # minimum_release_age holds 0.9.0 back: mise reports nothing
    assert m.find_outdated() == []


def test_find_outdated_falls_back_when_mise_fails(fake_home, fake_runner, monkeypatch):
    fake_runner.paths["uv"] = f"{MISE}/uv/0.8.23/uv"
    uv = _entry("uv")
    monkeypatch.setattr(m.catalog, "binaries", lambda: [uv])
    monkeypatch.setattr(versions, "local_version", lambda e: (0, 8, 23))
    monkeypatch.setattr(versions, "latest_version", lambda e: (0, 9, 0))
    _mise_json(fake_runner, "uv", {}, rc=1)
    assert [b for _, _, b in m.find_outdated()] == [(0, 9, 0)]


def test_failed_update_is_not_a_refusal(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(paths, "platform_key", lambda: "posix")
    monkeypatch.setattr(m, "find_outdated", lambda: [(_entry("uv"), (0, 8, 23), (0, 9, 0))])
    monkeypatch.setattr(versions, "local_version", lambda e: (0, 8, 23))
    fake_runner.responses[("uv", "self", "update")] = runner.Result(1, "", "network down")
    m.update(yes=True, ask=lambda q: "")
    assert not (paths.state_dir() / "refused-updates.json").exists()


def test_partial_update_is_not_a_refusal(fake_home, fake_runner, monkeypatch, capsys):
    monkeypatch.setattr(paths, "platform_key", lambda: "posix")
    monkeypatch.setattr(m, "find_outdated", lambda: [(_entry("uv"), (0, 8, 23), (0, 9, 2))])
    monkeypatch.setattr(versions, "local_version", lambda e: (0, 9, 0))
    m.update(yes=True, ask=lambda q: "")
    assert "updated to 0.9.0" in capsys.readouterr().out
    assert not m._refused()


def test_refused_file_that_is_not_an_object_is_ignored(fake_home):
    paths.state_dir().mkdir(parents=True)
    (paths.state_dir() / "refused-updates.json").write_text('["uv"]')
    assert m._refused() == {}


def _record_cwd(fake_runner, monkeypatch):
    seen = []

    def spy(cmd, cwd=None, timeout=300, env=None):
        seen.append((list(cmd), cwd))
        return fake_runner(cmd, cwd, timeout, env)

    monkeypatch.setattr(runner, "run", spy)
    return seen


def test_mise_upgrade_runs_in_home_from_update(fake_home, fake_runner, monkeypatch):
    fake_runner.paths["uv"] = f"{MISE}/uv/0.8.23/uv"
    monkeypatch.setattr(m, "find_outdated", lambda: [(_entry("uv"), (0, 8, 23), (0, 9, 0))])
    seen = _record_cwd(fake_runner, monkeypatch)
    m.update(yes=True, ask=lambda q: "")
    assert (["mise", "upgrade", "uv"], str(fake_home)) in seen


def test_mise_upgrade_runs_in_home_from_adopt(fake_home, fake_runner, monkeypatch):
    from loadout import adopt, backup, inventory
    fake_runner.paths["uv"] = f"{MISE}/uv/0.8.23/uv"
    item = inventory.Item("binary", "uv", "", "PATH", {"entry": _entry("uv"), "state": "outdated"})
    seen = _record_cwd(fake_runner, monkeypatch)
    adopt.apply([adopt.Verdict(item, "update", "", "uv")], backup.Backup(), confirm_cmds=False)
    assert (["mise", "upgrade", "uv"], str(fake_home)) in seen


def test_mise_tools_get_no_refusal_bookkeeping(fake_home, fake_runner, monkeypatch):
    entry = _entry("uv")
    fake_runner.paths["uv"] = f"{MISE}/uv/0.8.23/uv"
    paths.state_dir().mkdir(parents=True)
    (paths.state_dir() / "refused-updates.json").write_text('{"uv": "0.9.0"}')
    # a stale entry must not hide what mise itself reports as outdated
    assert m.worth_notifying([(entry, (0, 8, 23), (0, 9, 0))]) == [(entry, (0, 8, 23), (0, 9, 0))]
    monkeypatch.setattr(m, "find_outdated", lambda: [(entry, (0, 8, 23), (0, 9, 0))])
    monkeypatch.setattr(versions, "local_version", lambda e: (0, 8, 23))  # unchanged after mise upgrade
    m.update(yes=True, ask=lambda q: "")
    assert m._refused() == {}
