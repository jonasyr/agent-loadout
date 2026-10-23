"""plugins/loadout/hooks/harmless.py: which searches Serena's reminder cannot help with."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins" / "loadout" / "hooks"))
import harmless  # noqa: E402


@pytest.fixture(autouse=True)
def no_project_dir(monkeypatch):
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)  # set when the suite runs inside Claude Code


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


@pytest.mark.parametrize("cmd", ["rg x -g '!*.lock' .", "rg x -g '!package-lock.json'", "rg -t md -t py foo src",
                                 "grep -rn x --include=*.md --include=*.py ."])
def test_a_filter_only_limits_when_every_inclusion_is_a_doc_type(cmd):
    assert not bash(cmd)
    assert bash("rg -t md -t yaml foo .")


def test_a_negated_grep_tool_glob_is_no_doc_filter():
    assert not harmless.skips_remind({"tool_name": "Grep", "tool_input": {"pattern": "x", "glob": "!*.md"},
                                      "cwd": "/r"})


@pytest.mark.parametrize("cmd", ["{ cat src/a.py; } | grep foo", "for f in src/*.py; do cat $f; done | grep def",
                                 "cat src/a.py; gh pr view 1 | grep x"])
def test_a_code_read_anywhere_before_a_pipe_goes_to_serena(cmd):
    assert not bash(cmd)


def test_after_a_cd_relative_paths_are_judged_by_suffix_only():
    assert not bash("cd sub && grep foo ../a.py")
    assert bash("cd sub && grep foo ../notes.md")
    assert bash("cd sub && grep foo /tmp/x/a.py")


def test_the_claude_project_dir_is_the_project(monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/r")
    assert not bash("grep foo ../other/a.py", cwd="/r/sub")  # a sibling folder of the project, not outside it
    assert bash("grep foo /elsewhere/a.py", cwd="/r/sub")


def test_an_extensionless_code_file_of_the_project_goes_to_serena(tmp_path):
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "loadout").write_text("#!/usr/bin/env python3\n")
    (tmp_path / "Makefile").write_text("all:\n")
    assert not bash("cat bin/loadout | grep main", cwd=str(tmp_path))
    assert not bash("cat bin/loadout", cwd=str(tmp_path))
    assert bash("cat Makefile | grep all", cwd=str(tmp_path))  # a config name stays harmless
    assert bash("sed -n 1,80p notes.md | grep x", cwd=str(tmp_path))  # a sed script is no file


def test_after_a_cd_extensionless_files_are_looked_up_in_the_new_folder(tmp_path):
    (tmp_path / "sub" / "bin").mkdir(parents=True)
    (tmp_path / "sub" / "bin" / "loadout").write_text("#!/bin/sh\n")
    assert not bash("cd sub && cat bin/loadout | grep main", cwd=str(tmp_path))
    assert not bash('cd "$D" && cat bin/x | grep main', cwd=str(tmp_path))  # an unknown folder: code
    assert bash("cd sub && sed -n 1,80p notes.md | grep x", cwd=str(tmp_path))


def test_an_input_redirect_names_the_file_read():
    assert not bash("cat < src/a.py | grep foo")
    assert bash("cat < notes.md | grep foo")
    assert not bash("grep foo < src/a.py")


def test_a_cd_that_can_fail_leaves_the_folder_unknown(tmp_path):
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "loadout").write_text("#!/bin/sh\n")
    assert not bash("cd missing || cat bin/loadout | grep main", cwd=str(tmp_path))


def test_several_cds_leave_the_folder_unknown(tmp_path):
    (tmp_path / "sub" / "bin").mkdir(parents=True)
    (tmp_path / "sub" / "bin" / "loadout").write_text("#!/bin/sh\n")
    assert not bash("cd sub || cd ..; cat bin/loadout | grep main", cwd=str(tmp_path))
    assert bash("cd sub || cd ..; sed -n 1,80p notes.md | grep x", cwd=str(tmp_path))  # a sed script is no file


def test_dash_operands_after_double_dash_are_files():
    assert not bash("cat -- -script.py | grep main")
