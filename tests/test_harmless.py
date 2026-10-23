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



def test_an_input_redirect_names_the_file_read():
    assert not bash("cat < src/a.py | grep foo")
    assert bash("cat < notes.md | grep foo")
    assert not bash("grep foo < src/a.py")




def test_dash_operands_after_double_dash_are_files():
    assert not bash("cat -- -script.py | grep main")


def test_a_piped_grep_with_its_own_path_reads_that_path():
    assert not bash("echo x | grep foo src/a.py")
    assert bash("echo x | grep foo notes.md")



@pytest.mark.parametrize("cmd", ["cd sub && grep foo ../notes.md", "cd sub && sed -n 1,80p notes.md | grep x",
                                 "false && cd sub; cat bin/loadout | grep main", "cd missing || cat x | grep y",
                                 "for f in *.md; do grep x $f; done", "(cd sub; grep x a.md)", "{ grep x a.md; }",
                                 "grep x $(ls docs)", "grep x `ls docs`", "diff <(grep x a.md) b.md"])
def test_a_line_that_is_not_simple_goes_to_serena(cmd):
    assert not bash(cmd)


def test_a_wildcard_read_is_an_unknown_file():
    assert not bash("cat bin/* | grep main")
    assert bash("cat docs/*.md | grep main")


@pytest.mark.parametrize("cmd", ["echo x | grep -efoo src/a.py", "echo x | grep -nefoo src/a.py",
                                 "echo x | grep --regexp=foo src/a.py", "echo x | rg -e foo src/a.py"])
def test_attached_pattern_options_are_recognised(cmd):
    assert not bash(cmd)


def test_an_explicit_path_is_read_whatever_the_type_filter():
    assert not bash("rg -t md needle src/a.py")
    assert not bash("rg -tmd needle src/a.py")
    assert bash("rg -t md needle docs/")
    assert bash("rg -tmd needle")


def test_an_awk_program_is_no_file():
    assert bash("awk '{print $1}' notes.md | grep x")


def test_a_folder_named_like_a_doc_file_is_a_folder(tmp_path):
    (tmp_path / "docs.md").mkdir()
    (tmp_path / "docs.md" / "code.py").write_text("x = 1\n")
    assert not bash("rg needle docs.md", cwd=str(tmp_path))
    assert bash("rg -t md needle docs.md", cwd=str(tmp_path))  # a doc filter limits the folder's walk


def test_a_leading_redirect_makes_the_line_not_simple():
    assert not bash("< src/a.py cat | grep foo")
    assert not bash("cat x.md && < src/a.py cat | grep foo")


def test_a_doc_glob_that_matches_a_folder_is_a_folder(tmp_path):
    (tmp_path / "docs.md").mkdir()
    (tmp_path / "docs.md" / "code.py").write_text("x = 1\n")
    (tmp_path / "notes.md").write_text("n\n")
    assert not bash("rg needle *.md", cwd=str(tmp_path))
    (tmp_path / "docs.md" / "code.py").unlink()
    (tmp_path / "docs.md").rmdir()
    assert bash("rg needle *.md", cwd=str(tmp_path))
