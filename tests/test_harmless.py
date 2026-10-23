"""plugins/loadout/hooks/harmless.py: which searches Serena's reminder cannot help with."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins" / "loadout" / "hooks"))
import harmless  # noqa: E402


def bash(cmd, cwd="/r"):
    return harmless.skips_remind({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": cwd})


@pytest.mark.parametrize("cmd", ["gh pr view 59 | grep -i codex",
                                 'bin/loadout check --verbose 2>&1 | grep -E "auto_index"'])
def test_pipe_filter_is_harmless(cmd):
    assert bash(cmd)


@pytest.mark.parametrize("cmd", ["cat a.py | grep foo", "sed -n 1,80p src/a.ts | grep bar"])
def test_pipe_from_code_read_goes_to_serena(cmd):
    assert not bash(cmd)
    assert bash("cat notes.md | grep x")


@pytest.mark.parametrize("cmd", ["grep -n x .gitignore", "grep -n '^#' docs/a.md | tail -3",
                                 "rg x pyproject.toml config.yaml", "grep x .env.local"])
def test_config_and_doc_files_are_harmless(cmd):
    assert bash(cmd)


@pytest.mark.parametrize("cmd", ["rg foo -t md", "grep -rn x --include='*.yml' ."])
def test_doc_filter_is_harmless(cmd):
    assert bash(cmd)


@pytest.mark.parametrize("cmd", ["grep -n x ~/.codex/config.toml", "rg foo /tmp/x/a.rs", "grep x ../other/a.py"])
def test_outside_project_is_harmless(cmd):
    assert bash(cmd)


def test_relative_paths_resolve_against_cwd():
    assert not bash("grep x ./../r/a.py")


@pytest.mark.parametrize("cmd", ['grep -n "class FakeRunner" tests/conftest.py', "rg foo src/", "grep -r x .",
                                 "rg foo", "grep x a.vue"])
def test_code_searches_go_to_serena(cmd):
    assert not bash(cmd)


@pytest.mark.parametrize("cmd", ["grep x a.md; grep y b.py", "sed -n 1,80p a.py; grep -n x notes.md"])
def test_mixed_line_goes_to_serena(cmd):
    assert not bash(cmd)


@pytest.mark.parametrize("cmd", ['grep x "$f"', "grep x $(git ls-files)"])
def test_variable_operand_goes_to_serena(cmd):
    assert not bash(cmd)
    assert bash("rg foo -- -weird.md")


def test_unparseable_line_goes_to_serena():
    assert not bash('grep "x a.md')


@pytest.mark.parametrize("cmd", ["ls -la", "git status"])
def test_line_without_search_is_not_skipped(cmd):
    assert not bash(cmd)


def test_read_tool():
    def read(p):
        return harmless.skips_remind({"tool_name": "Read", "tool_input": {"file_path": p}, "cwd": "/r"})
    assert read("/tmp/x/a.rs")
    assert not read("/r/a.py")
    assert read("/r/a.md")


def test_grep_tool():
    def grep(**ti):
        return harmless.skips_remind({"tool_name": "Grep", "tool_input": {"pattern": "x", **ti}, "cwd": "/r"})
    assert grep(glob="*.md")
    assert not grep(path="/r/src")
    assert grep(path="/home/u/.codex")


def test_codex_argv_and_cmd_forms():
    assert harmless.skips_remind({"tool_name": "Bash", "tool_input": {"cmd": "gh x | grep y"}, "cwd": "/r"})
    assert harmless.skips_remind({"tool_name": "Bash", "tool_input": {"command": ["bash", "-lc", "grep x a.md"]},
                                  "cwd": "/r"})


def test_missing_cwd_or_other_tool_is_not_skipped():
    assert not harmless.skips_remind({"tool_name": "Bash", "tool_input": {"command": "grep x a.md"}})
    assert not harmless.skips_remind({"tool_name": "Glob", "tool_input": {"pattern": "*.md"}, "cwd": "/r"})


def test_redirect_fd_is_not_a_path():
    assert bash("grep x a.md 2>&1")


def test_non_code_matches_loadout_usage():
    from loadout import searches
    assert harmless.NON_CODE == searches.NON_CODE
