"""The README demo records the real CLI, but only in a throwaway sandbox (demo/)."""
import os
import subprocess
import sys

import pytest

from loadout import paths

DEMO = paths.kit_root() / "demo"


def test_tape_records_only_the_sandbox_home():
    tape = (DEMO / "loadout.tape").read_text()
    assert "demo/sandbox.sh /home/demo" in tape and "export HOME=/home/demo" in tape
    assert tape.index("Hide") < tape.index("sandbox.sh") < tape.index("Show")


def test_render_runs_offline_in_a_container():
    render = (DEMO / "render.sh").read_text()
    assert "--network=none" in render and "/src:ro" in render


@pytest.mark.skipif(os.name == "nt", reason="bash script")
def test_sandbox_refuses_an_existing_home(tmp_path):
    (tmp_path / "keep.txt").write_text("mine")
    p = subprocess.run(["bash", str(DEMO / "sandbox.sh"), str(tmp_path)], capture_output=True, text=True, timeout=30)
    assert p.returncode == 1 and "exists" in p.stderr
    assert sorted(x.name for x in tmp_path.iterdir()) == ["keep.txt"]


def test_demo_claude_refuses_outside_the_sandbox(tmp_path):
    (tmp_path / ".claude.json").write_text('{"mcpServers": {"x": {}}}')
    p = subprocess.run([sys.executable, str(DEMO / "bin/claude"), "mcp", "remove", "-s", "user", "x"],
                       env={**os.environ, "HOME": str(tmp_path)}, capture_output=True, text=True, timeout=30)
    assert p.returncode != 0 and "sandbox" in p.stderr
    assert '"x"' in (tmp_path / ".claude.json").read_text()


def test_demo_claude_edits_the_sandbox_like_the_real_cli(tmp_path):
    (tmp_path / ".loadout-demo").touch()
    (tmp_path / ".claude.json").write_text('{"mcpServers": {"x": {}, "y": {}}}')
    subprocess.run([sys.executable, str(DEMO / "bin/claude"), "mcp", "remove", "-s", "user", "x"],
                   env={**os.environ, "HOME": str(tmp_path)}, check=True, timeout=30)
    assert '"x"' not in (tmp_path / ".claude.json").read_text() and '"y"' in (tmp_path / ".claude.json").read_text()

README_URL = "https://raw.githubusercontent.com/jonasyr/agent-loadout/main/bootstrap.sh"


@pytest.mark.skipif(os.name == "nt", reason="sh stubs")
@pytest.mark.parametrize("stub", ["curl", "uv"])
def test_demo_stubs_refuse_outside_the_sandbox(tmp_path, stub):
    p = subprocess.run(["sh", str(DEMO / "bin" / stub), "--version"], env={**os.environ, "HOME": str(tmp_path)},
                       capture_output=True, text=True, timeout=30)
    assert p.returncode != 0 and "sandbox" in p.stderr


@pytest.mark.skipif(os.name == "nt", reason="sh stubs")
def test_demo_curl_serves_only_the_readme_url(tmp_path):
    (tmp_path / ".loadout-demo").touch()
    env = {**os.environ, "HOME": str(tmp_path), "LOADOUT_DEMO_KIT": str(paths.kit_root())}
    ok = subprocess.run(["sh", str(DEMO / "bin/curl"), "-fsSL", README_URL], env=env, capture_output=True, text=True, timeout=30)
    assert ok.returncode == 0 and ok.stdout == (paths.kit_root() / "bootstrap.sh").read_text()
    bad = subprocess.run(["sh", str(DEMO / "bin/curl"), "-fsSL", "https://example.com/x"], env=env,
                         capture_output=True, text=True, timeout=30)
    assert bad.returncode != 0 and bad.stdout == ""


@pytest.mark.skipif(os.name == "nt", reason="sh stubs")
def test_demo_uv_finds_the_real_python(tmp_path):
    (tmp_path / ".loadout-demo").touch()
    p = subprocess.run(["sh", str(DEMO / "bin/uv"), "python", "find", "--system", ">=3.10"],
                       env={**os.environ, "HOME": str(tmp_path)}, capture_output=True, text=True, timeout=30)
    assert p.returncode == 0 and "python3" in p.stdout


def test_demo_claude_lists_mcp_servers_and_plugins(tmp_path):
    (tmp_path / ".loadout-demo").touch()
    (tmp_path / ".claude.json").write_text('{"mcpServers": {"x": {"command": "npx", "args": ["srv"]}}}')
    (tmp_path / ".claude/plugins").mkdir(parents=True)
    (tmp_path / ".claude/plugins/installed_plugins.json").write_text('{"plugins": {"p@m": []}}')
    env = {**os.environ, "HOME": str(tmp_path)}
    run = lambda *a: subprocess.run([sys.executable, str(DEMO / "bin/claude"), *a], env=env,
                                    capture_output=True, text=True, timeout=30).stdout
    assert run("mcp", "list").strip() == "x: npx srv"
    assert run("plugin", "list").strip() == "p@m"


def test_tape_types_the_readme_one_liner():
    readme = (paths.kit_root() / "README.md").read_text()
    line = next(l for l in readme.splitlines() if l.startswith("curl -fsSL") and README_URL in l)
    assert f'Type "{line}"' in (DEMO / "loadout.tape").read_text()


def test_nothing_runs_the_real_claude_clip_recorder():
    for f in ("render.sh", "loadout.tape", "sandbox.sh"):
        assert "record-claude" not in (DEMO / f).read_text()
