"""`loadout update` re-adds one of loadout's Codex marketplaces whose upgrade hit Codex's fixed 30 s clone timeout
(openai/codex#38770): backed up, rolled back on failure, never while Codex runs."""
import json
from pathlib import Path

import pytest

from loadout import backup, codex, runner

SETTINGS = {
    "enabledPlugins": {"impeccable@impeccable": True},
    "extraKnownMarketplaces": {"impeccable": {"source": {"source": "github", "repo": "pbakaus/impeccable"}}},
}
TIMEOUT = runner.Result(1, "", "Error: Failed to upgrade marketplace `impeccable`: git clone marketplace source "
                               "timed out after 30s")
TABLE = '[marketplaces.impeccable]\nsource_type = "git"\nsource = "https://github.com/pbakaus/impeccable.git"\n'
ADD = ("codex", "plugin", "marketplace", "add", "pbakaus/impeccable")
ADDED = runner.Result(0, json.dumps({"marketplaceName": "impeccable", "alreadyAdded": True}), "")
OK_LINE = ("marketplace impeccable: Codex's upgrade timed out after 30s; removed and added it again "
           "(openai/codex#38770)")
RUNNING_LINE = ("marketplace impeccable: Codex's upgrade timed out after 30s; quit Codex and run loadout update "
                "again to re-add it (openai/codex#38770)")


@pytest.fixture
def setup(fake_home, fake_runner, monkeypatch):
    from loadout import settings_merge
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: SETTINGS)
    monkeypatch.setattr(codex, "codex_running", lambda platform=None: False)
    fake_runner.responses[ADD] = ADDED
    fake_runner.responses[("codex", "plugin", "list")] = runner.Result(
        0, json.dumps({"installed": [{"pluginId": "impeccable@impeccable"}], "available": []}), "")
    fake_runner.responses[("codex", "plugin", "marketplace", "upgrade")] = TIMEOUT
    cfg = fake_home / ".codex/config.toml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text('model = "x"\n\n' + TABLE)
    snap = fake_home / ".codex/.tmp/marketplaces/impeccable"
    snap.mkdir(parents=True)
    (snap / "x").write_text("old")
    return cfg, snap


def _run(**kw):
    bk = backup.Backup(description="t")
    return codex.apply_plugins(bk, refresh=kw.pop("refresh", True), **kw), bk


def _calls(fake_runner, *head):
    return [c for c in fake_runner.calls if tuple(c[:len(head)]) == head]


def _remove_table_on_remove(monkeypatch, fake_runner, cfg, put_back: str | None = None):
    """Play Codex's `marketplace remove`: the table goes; put_back: a running Codex writes the table again."""
    def run(cmd, cwd=None, timeout=300, env=None):
        if list(cmd[:4]) == ["codex", "plugin", "marketplace", "remove"]:
            cfg.write_text('model = "x"\n')
        if list(cmd[:4]) == ["codex", "plugin", "marketplace", "add"] and put_back and len(
                _calls(fake_runner, *ADD)) >= 1:
            cfg.write_text(put_back)
        return fake_runner(cmd, cwd=cwd, timeout=timeout, env=env)
    monkeypatch.setattr(runner, "run", run)


def test_codex_timeout_readds_and_reinstalls(setup, fake_runner):
    cfg, snap = setup
    lines, bk = _run()
    upgrades = _calls(fake_runner, "codex", "plugin", "marketplace", "upgrade")
    assert len(upgrades) == 1, "no retry after Codex's timeout"
    order = [c[:4] for c in fake_runner.calls if c[:3] == ["codex", "plugin", "marketplace"]]
    i = order.index(["codex", "plugin", "marketplace", "upgrade"])
    assert order[i + 1] == ["codex", "plugin", "marketplace", "remove"]
    assert order[i + 2] == ["codex", "plugin", "marketplace", "add"]
    assert ["codex", "plugin", "marketplace", "add", "pbakaus/impeccable", "--json"] in fake_runner.calls
    assert ["codex", "plugin", "add", "impeccable@impeccable", "--json"] in fake_runner.calls
    assert OK_LINE in lines
    assert not any("failed to upgrade" in l for l in lines)
    assert any("restore-file" in s["undo"] and s["undo"]["restore-file"][1] == str(cfg) for s in bk.steps)
    moves = [s["undo"]["move"][0] for s in bk.steps if "move" in s["undo"]]
    assert moves and all(__import__("os").path.exists(m) for m in moves), "restore can put the old snapshot back"


def test_no_readd_while_codex_runs(setup, fake_runner, monkeypatch):
    monkeypatch.setattr(codex, "codex_running", lambda platform=None: True)
    lines, _ = _run()
    assert not _calls(fake_runner, "codex", "plugin", "marketplace", "remove")
    assert RUNNING_LINE in lines
    assert ["codex", "plugin", "add", "impeccable@impeccable", "--json"] not in fake_runner.calls
    assert (setup[1] / "x").exists()


def test_cannot_tell_counts_as_running(setup, fake_runner, monkeypatch):
    monkeypatch.setattr(codex, "codex_running", lambda platform=None: None)
    lines, _ = _run()
    assert not _calls(fake_runner, "codex", "plugin", "marketplace", "remove")
    assert any("could not tell whether Codex runs; quit Codex" in l for l in lines)


def test_table_with_sparse_paths_is_not_readded(setup, fake_runner):
    cfg, _ = setup
    cfg.write_text(cfg.read_text() + 'sparse_paths = ["plugins"]\n')
    lines, _ = _run()
    assert not _calls(fake_runner, "codex", "plugin", "marketplace", "remove")
    assert any(l.startswith("marketplace impeccable: failed to upgrade (")
               and l.endswith("; loadout did not re-add it because your table sets sparse_paths") for l in lines)


def test_failed_readd_rolls_back(setup, fake_runner, monkeypatch):
    cfg, snap = setup
    before = cfg.read_bytes()
    fake_runner.responses[ADD] = [ADDED, runner.Result(1, "", "boom")]
    _remove_table_on_remove(monkeypatch, fake_runner, cfg)
    lines, _ = _run()
    assert _calls(fake_runner, "codex", "plugin", "marketplace", "remove")
    assert cfg.read_bytes() == before
    assert (snap / "x").read_text() == "old"
    assert any(l.startswith("marketplace impeccable: failed to upgrade (")
               and l.endswith("; re-adding it failed too (boom)") for l in lines)
    assert ["codex", "plugin", "add", "impeccable@impeccable", "--json"] not in fake_runner.calls


def test_rollback_leaves_a_config_that_has_the_table_again(setup, fake_runner, monkeypatch):
    cfg, _ = setup
    other = 'model = "y"\n' + TABLE + 'last_updated = "2026-10-25"\n'
    fake_runner.responses[ADD] = [ADDED, runner.Result(1, "", "boom")]
    _remove_table_on_remove(monkeypatch, fake_runner, cfg, put_back=other)
    _run()
    assert cfg.read_text() == other


def test_readd_without_a_snapshot_folder(setup, fake_runner):
    _, snap = setup
    import shutil
    shutil.rmtree(snap)
    lines, bk = _run()
    assert OK_LINE in lines
    assert not [s for s in bk.steps if "move" in s["undo"]]


def test_loadout_runner_timeout_is_not_codex_timeout(setup, fake_runner):
    fake_runner.responses[("codex", "plugin", "marketplace", "upgrade")] = runner.Result(
        124, "", "codex: timed out after 1800s")
    lines, _ = _run()
    assert len(_calls(fake_runner, "codex", "plugin", "marketplace", "upgrade")) == 1
    assert not _calls(fake_runner, "codex", "plugin", "marketplace", "remove")
    assert any(l.startswith("marketplace impeccable: failed to upgrade (") and
               l.endswith("its installed plugins stay at the previous version") for l in lines)


def test_other_upgrade_failure_keeps_todays_behaviour(setup, fake_runner, monkeypatch):
    monkeypatch.setattr(codex, "UPGRADE_RETRY_WAIT", 0)
    fake_runner.responses[("codex", "plugin", "marketplace", "upgrade")] = runner.Result(1, "", "network down")
    lines, _ = _run()
    assert len(_calls(fake_runner, "codex", "plugin", "marketplace", "upgrade")) == 2
    assert not _calls(fake_runner, "codex", "plugin", "marketplace", "remove")
    assert any(l.endswith("its installed plugins stay at the previous version") for l in lines)


def test_frozen_marketplace_is_never_readded(setup, fake_runner, monkeypatch):
    from loadout import settings_merge
    frozen = json.loads(json.dumps(SETTINGS))
    frozen["extraKnownMarketplaces"]["impeccable"]["autoUpdate"] = False
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: frozen)
    _run(auto=True)
    assert not _calls(fake_runner, "codex", "plugin", "marketplace", "upgrade")
    assert not _calls(fake_runner, "codex", "plugin", "marketplace", "remove")


def test_codex_timed_out_and_table_blockers_units(fake_home):
    assert codex._codex_timed_out(TIMEOUT)
    assert not codex._codex_timed_out(runner.Result(124, "", "codex: timed out after 1800s"))
    assert not codex._codex_timed_out(runner.Result(0, "timed out after 30s marketplace", ""))
    assert not codex._codex_timed_out(runner.Result(1, "", "network down"))
    cfg = fake_home / ".codex/config.toml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    assert codex._table_blockers("impeccable", "pbakaus/impeccable") == []  # no file
    cfg.write_text(TABLE + 'ref_name = "v2"\n')
    assert codex._table_blockers("impeccable", "pbakaus/impeccable") == ["ref_name"]
    assert codex._table_blockers("impeccable", "pbakaus/impeccable@v2") == []
    cfg.write_text(TABLE + 'ref_name = "v2"\nsparse_paths = ["a"]\n')
    assert codex._table_blockers("impeccable", "pbakaus/impeccable") == ["ref_name", "sparse_paths"]
    cfg.write_text(TABLE + "sparse_paths = []\n")
    assert codex._table_blockers("impeccable", "pbakaus/impeccable") == []
    cfg.write_text("not = [toml")
    assert codex._table_blockers("impeccable", "pbakaus/impeccable") == []


def test_failed_remove_moves_snapshot_back(setup, fake_runner):
    cfg, snap = setup
    before = cfg.read_bytes()
    fake_runner.responses[("codex", "plugin", "marketplace", "remove")] = runner.Result(1, "", "x")
    lines, _ = _run()
    assert cfg.read_bytes() == before and (snap / "x").read_text() == "old"
    assert any(l.endswith("; re-adding it failed too (x)") for l in lines)


def test_a_failing_snapshot_move_back_still_restores_the_config(setup, fake_runner, monkeypatch):
    import shutil
    cfg, _ = setup
    before = cfg.read_bytes()
    fake_runner.responses[ADD] = [ADDED, runner.Result(1, "", "boom")]
    _remove_table_on_remove(monkeypatch, fake_runner, cfg)
    real = shutil.move

    def move(src, dst, *a, **kw):
        if Path(dst).parts[-2:] == ("marketplaces", "impeccable"):  # the move back, not the backup's move aside
            raise OSError("disk full")
        return real(src, dst, *a, **kw)
    monkeypatch.setattr(shutil, "move", move)
    lines, _ = _run()
    assert cfg.read_bytes() == before, "the user's table comes back even when the snapshot cannot"
    assert any("re-adding it failed too (boom; the old snapshot stays in the backup" in l for l in lines)


def test_a_failing_config_write_back_does_not_abort_the_update(setup, fake_runner, monkeypatch):
    cfg, snap = setup
    fake_runner.responses[ADD] = [ADDED, runner.Result(1, "", "boom")]
    _remove_table_on_remove(monkeypatch, fake_runner, cfg)
    from loadout import jsonio

    real = jsonio.write_atomic_bytes

    def fail(path, *a, **k):
        if path == cfg:
            raise OSError("read-only")
        return real(path, *a, **k)
    monkeypatch.setattr(jsonio, "write_atomic_bytes", fail)
    lines, _ = _run()
    assert (snap / "x").read_text() == "old", "the snapshot still comes back"
    assert any("re-adding it failed too (boom; your config.toml stays in the backup (loadout restore puts it back)"
               in l for l in lines)


USER_CFG = ('model = "x"  # mine\n\n# my marketplaces\n[marketplaces.impeccable]  # big one\n'
            'source_type = "git"\nsource = "https://github.com/pbakaus/impeccable.git"\n'
            'last_updated = "2026-01-01T00:00:00Z"   # old\n\n[other]\nkeep = 1\n')


def _codex_like_add(monkeypatch, fake_runner, cfg, extra=""):
    """Play Codex: remove drops the table (and the comments), add writes a fresh one."""
    def run(cmd, cwd=None, timeout=300, env=None):
        if list(cmd[:4]) == ["codex", "plugin", "marketplace", "remove"]:
            cfg.write_text('model = "x"\n\n[other]\nkeep = 1\n')
        res = fake_runner(cmd, cwd=cwd, timeout=timeout, env=env)
        if list(cmd[:4]) == ["codex", "plugin", "marketplace", "add"] and "--json" in cmd and res.ok and len(
                _calls(fake_runner, *ADD)) >= 2:
            cfg.write_text('model = "x"\n\n[other]\nkeep = 1\n\n[marketplaces.impeccable]\nsource_type = "git"\n'
                           'source = "https://github.com/pbakaus/impeccable.git"\n'
                           'last_updated = "2026-10-25T10:00:00Z"\nlast_revision = "abc123"\n' + extra)
        return res
    monkeypatch.setattr(runner, "run", run)


def test_success_keeps_the_users_text_byte_for_byte(setup, fake_runner, monkeypatch):
    cfg, _ = setup
    cfg.write_text(USER_CFG)
    _codex_like_add(monkeypatch, fake_runner, cfg)
    lines, _ = _run()
    assert OK_LINE in lines
    assert cfg.read_text() == USER_CFG.replace('"2026-01-01T00:00:00Z"', '"2026-10-25T10:00:00Z"').replace(
        'last_updated = "2026-10-25T10:00:00Z"   # old\n', 'last_updated = "2026-10-25T10:00:00Z"   # old\n'
        'last_revision = "abc123"\n')


def test_success_keeps_codexs_file_when_it_wrote_more(setup, fake_runner, monkeypatch):
    cfg, _ = setup
    cfg.write_text(USER_CFG)
    _codex_like_add(monkeypatch, fake_runner, cfg, extra='new_key = "v"\n')
    _run()
    assert 'new_key = "v"' in cfg.read_text(), "the file Codex wrote stays when the user's text cannot carry it"


def test_only_the_newest_snapshot_copy_is_kept(setup, fake_runner, monkeypatch):
    import os
    _, snap = setup
    _, first = _run()
    old = [s["undo"]["move"][0] for s in first.steps if "move" in s["undo"]]
    assert old and all(os.path.exists(m) for m in old)
    snap.mkdir(parents=True, exist_ok=True)
    (snap / "x").write_text("second")
    fake_runner.responses[ADD] = ADDED
    _, second = _run()
    new = [s["undo"]["move"][0] for s in second.steps if "move" in s["undo"]]
    assert new and all(os.path.exists(m) for m in new)
    assert not any(os.path.exists(m) for m in old), "the previous run's copy of the same marketplace is dropped"


def test_success_keeps_a_crlf_users_text(setup, fake_runner, monkeypatch):
    cfg, _ = setup
    crlf = USER_CFG.replace("\n", "\r\n")
    cfg.write_bytes(crlf.encode())
    _codex_like_add(monkeypatch, fake_runner, cfg)
    _run()
    assert cfg.read_bytes() == crlf.replace('"2026-01-01T00:00:00Z"   # old\r\n',
                                            '"2026-10-25T10:00:00Z"   # old\r\nlast_revision = "abc123"\r\n').encode()


def test_a_failing_text_write_after_success_does_not_abort(setup, fake_runner, monkeypatch):
    from loadout import jsonio
    cfg, _ = setup
    cfg.write_text(USER_CFG)
    _codex_like_add(monkeypatch, fake_runner, cfg)
    real = jsonio.write_atomic_bytes

    def fail(path, *a, **k):
        if path == cfg:
            raise PermissionError("held by an editor")
        return real(path, *a, **k)
    monkeypatch.setattr(jsonio, "write_atomic_bytes", fail)
    lines, _ = _run()
    assert any(l.startswith(OK_LINE) for l in lines)
    assert "last_revision" in cfg.read_text(), "Codex's own file stays"


def test_restore_after_a_readd_puts_the_old_snapshot_back(setup, fake_runner, monkeypatch):
    cfg, snap = setup
    before = cfg.read_bytes()

    def run(cmd, cwd=None, timeout=300, env=None):  # Codex's add clones a new snapshot
        res = fake_runner(cmd, cwd=cwd, timeout=timeout, env=env)
        if list(cmd[:4]) == ["codex", "plugin", "marketplace", "add"] and len(_calls(fake_runner, *ADD)) >= 2:
            snap.mkdir(parents=True, exist_ok=True)
            (snap / "x").write_text("new")
        return res
    monkeypatch.setattr(runner, "run", run)
    _, bk = _run()
    assert (snap / "x").read_text() == "new"
    backup.restore(bk.root)
    assert (snap / "x").read_text() == "old", "the old snapshot comes back with the old config"
    assert cfg.read_bytes() == before


@pytest.mark.parametrize("header", ['["marketplaces".impeccable]', "[ 'marketplaces' . \"impeccable\" ]"])
def test_quoted_table_headers_keep_the_users_text(setup, fake_runner, monkeypatch, header):
    cfg, _ = setup
    text = USER_CFG.replace("[marketplaces.impeccable]", header)
    cfg.write_text(text)
    _codex_like_add(monkeypatch, fake_runner, cfg)
    _run()
    assert cfg.read_text().startswith('model = "x"  # mine\n\n# my marketplaces\n' + header + "  # big one\n")


@pytest.mark.parametrize("cfg_text", [
    'model = "x"\n[marketplaces]\nimpeccable = { source_type = "git", source = "https://github.com/pbakaus/impeccable.git" }\n',
    'model = "x"\nmarketplaces.impeccable.source_type = "git"  # mine\n'
    'marketplaces.impeccable.source = "https://github.com/pbakaus/impeccable.git"\n',
])
def test_a_table_whose_text_cannot_be_kept_is_not_readded(setup, fake_runner, cfg_text):
    cfg, _ = setup
    cfg.write_text(cfg_text)
    lines, _ = _run()
    assert not _calls(fake_runner, "codex", "plugin", "marketplace", "remove")
    assert cfg.read_text() == cfg_text
    assert any(l.endswith("; loadout did not re-add it because it could not keep your table's text "
                          "(write it as [marketplaces.impeccable])") for l in lines)


@pytest.mark.parametrize("spelling", ['"last_updated"', "'last_updated'"])
def test_quoted_timestamp_keys_keep_the_users_text(setup, fake_runner, monkeypatch, spelling):
    cfg, _ = setup
    text = USER_CFG.replace("last_updated = ", f"{spelling} = ")
    cfg.write_text(text)
    _codex_like_add(monkeypatch, fake_runner, cfg)
    _run()
    assert cfg.read_text().startswith('model = "x"  # mine\n\n# my marketplaces\n')
    assert f'{spelling} = "2026-10-25T10:00:00Z"   # old' in cfg.read_text()
