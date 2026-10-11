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
