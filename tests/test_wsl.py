import pytest

from loadout import bootstrap as b, check, wsl


@pytest.mark.parametrize("text,expected", [
    ("5.15.153.1-microsoft-standard-WSL2\n", 2),
    ("6.6.36.3-microsoft-standard-wsl2", 2),
    ("4.4.0-19041-Microsoft\n", 1),
    ("6.10.5-arch1-1\n", None),
])
def test_detect(tmp_path, text, expected):
    f = tmp_path / "osrelease"
    f.write_text(text)
    assert wsl.detect(f, platform="linux") == expected


def test_detect_missing_file_and_other_platform(tmp_path):
    assert wsl.detect(tmp_path / "nope", platform="linux") is None
    f = tmp_path / "osrelease"
    f.write_text("5.15.153.1-microsoft-standard-WSL2")
    assert wsl.detect(f, platform="win32") is None


@pytest.fixture
def mnt(tmp_path):
    root = tmp_path / "mnt"
    (root / "c" / "Users" / "me").mkdir(parents=True)
    (root / "cache").mkdir()
    return root


def _prefix(mnt):
    return mnt.as_posix() + "/"


def test_no_problems_on_clean_wsl2(fake_home, fake_runner, mnt, tmp_path):
    assert wsl.problems(2, tmp_path, mount=_prefix(mnt)) == []


def test_wsl1_is_a_problem(fake_home, fake_runner, mnt, tmp_path):
    texts = [p for p, _ in wsl.problems(1, tmp_path, mount=_prefix(mnt))]
    assert any("WSL 1" in t for t in texts)
    fixes = [f for _, f in wsl.problems(1, tmp_path, mount=_prefix(mnt))]
    assert any("wsl --set-version <distro> 2" in f for f in fixes)


def test_cwd_on_windows_drive(fake_home, fake_runner, mnt):
    cwd = mnt / "c" / "Users" / "me"
    found = wsl.problems(2, cwd, mount=_prefix(mnt))
    assert len(found) == 1
    assert "Windows filesystem" in found[0][0] and cwd.as_posix() in found[0][0]
    assert "Linux home" in found[0][1]


def test_dir_named_like_mount_but_not_a_drive_letter_is_fine(fake_home, fake_runner, mnt):
    assert wsl.problems(2, mnt / "cache", mount=_prefix(mnt)) == []


def test_personal_root_on_windows_drive(fake_home, fake_runner, mnt, tmp_path, monkeypatch):
    monkeypatch.setenv("LOADOUT_PERSONAL", str(mnt / "c" / "Users" / "me" / "personal"))
    texts = [p for p, _ in wsl.problems(2, tmp_path, mount=_prefix(mnt))]
    assert any("personal" in t and "Windows filesystem" in t for t in texts)


def test_windows_tools_on_path(fake_home, fake_runner, mnt, tmp_path):
    fake_runner.paths["node"] = (mnt / "c" / "Program Files" / "nodejs" / "node").as_posix()
    fake_runner.paths["git"] = "/usr/bin/git"
    found = wsl.problems(2, tmp_path, mount=_prefix(mnt))
    assert [p for p, _ in found] == [f"node resolves to the Windows program {fake_runner.paths['node']}"]
    assert "appendWindowsPath = false" in found[0][1]


def test_sandbox_packages_missing_only_on_wsl2(fake_home, fake_runner, mnt, tmp_path):
    fake_runner.missing.update({"bwrap", "socat"})
    two = wsl.problems(2, tmp_path, mount=_prefix(mnt))
    assert ("sandbox packages missing: bubblewrap, socat", "`sudo apt-get install bubblewrap socat`") in two
    one = wsl.problems(1, tmp_path, mount=_prefix(mnt))
    assert not any("sandbox packages" in p for p, _ in one)


def test_check_lines_in_wsl(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    monkeypatch.setattr(wsl, "problems", lambda v, cwd, mount="/mnt/": [("repo is slow", "move it")])
    results = check.run_checks()
    names = [r.name for r in results]
    assert "WSL 2" in names
    warn = next(r for r in results if r.name == "WSL" and not r.ok)
    assert warn.severity == "warn" and warn.detail == "repo is slow" and warn.fix == "move it"


def test_check_has_no_wsl_lines_outside_wsl(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: None)
    assert not any(r.name.startswith("WSL") for r in check.run_checks())


def test_report_lines(fake_home, fake_runner, monkeypatch, tmp_path):
    monkeypatch.setattr(wsl, "problems", lambda v, cwd, mount="/mnt/": [("p1", "f1")])
    assert wsl.report_lines(1, tmp_path) == ["WSL 1 detected", "p1", "  fix: f1"]


def test_bootstrap_prints_wsl_problems_and_continues(fake_home, fake_runner, monkeypatch, capsys):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 1)
    monkeypatch.setattr(wsl, "report_lines", lambda v, cwd: ["WSL 1 detected", "p1", "  fix: f1"])
    stop = RuntimeError("stop after the WSL step")

    def halt(*a, **k):
        raise stop

    monkeypatch.setattr(b, "check_prereqs", halt)
    with pytest.raises(RuntimeError):
        b.bootstrap(install=False, yes=True, plugins=False, adopt_step=False, ask=lambda q: "", interactive=False)
    out = capsys.readouterr().out
    assert "== WSL" in out and "p1" in out and "fix: f1" in out  # printed, then bootstrap went on to prerequisites


def test_personal_layer_symlinked_into_windows_drive(fake_home, fake_runner, mnt, tmp_path, monkeypatch):
    link = tmp_path / "personal-link"
    link.symlink_to(mnt / "c" / "Users" / "me", target_is_directory=True)
    monkeypatch.setenv("LOADOUT_PERSONAL", str(link))
    texts = [p for p, _ in wsl.problems(2, tmp_path, mount=_prefix(mnt))]
    assert any("personal" in t and "Windows filesystem" in t for t in texts)


def test_check_survives_a_deleted_current_folder(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)

    def gone():
        raise FileNotFoundError("cwd deleted")

    monkeypatch.setattr(wsl.Path, "cwd", staticmethod(gone))
    assert "WSL 2" in [r.name for r in check.run_checks()]


def test_tool_under_mnt_but_not_a_drive_is_fine(fake_home, fake_runner, mnt, tmp_path):
    fake_runner.paths["git"] = (mnt / "cache" / "bin" / "git").as_posix()
    assert wsl.problems(2, tmp_path, mount=_prefix(mnt)) == []


def test_detect_reads_the_module_osrelease(tmp_path, monkeypatch):
    f = tmp_path / "osrelease"
    f.write_text("5.15.153.1-microsoft-standard-WSL2")
    monkeypatch.setattr(wsl, "OSRELEASE", f)
    assert wsl.detect(platform="linux") == 2


def test_fake_home_hides_the_real_osrelease(fake_home):
    assert wsl.detect(platform="linux") is None
