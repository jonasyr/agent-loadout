"""searches: what counts as a symbol search in a grep/rg/find command (the measure `loadout usage` reports)."""
import pytest

from loadout import searches


def _symbol(command):
    hit, name, _ = searches.shell_search(command)
    return name if hit else None


def test_alternation_counts_as_symbol_search():
    assert searches.shell_search(r'rg -n "hooks_status\|plugin_hook_commands" cli')[1] == "hooks_status"
    assert searches.shell_search("grep -nE 'alpha_fn|beta_fn' src")[1] == "alpha_fn"
    assert searches.shell_search("rg -n '(record_project|other_name)' src")[1] == "record_project"


def test_every_search_in_a_compound_line_is_seen():
    hit, name, _ = searches.shell_search("sed -n 1,40p a.py; grep -n 'error\\|todo' x.py; rg -n build_parser cli")
    assert hit and name == "build_parser"


def test_common_words_and_doc_filters_still_do_not_count():
    assert searches.shell_search("rg -n error src")[1] is None
    assert searches.shell_search("rg -n build_parser -t md docs")[0] is False


@pytest.mark.parametrize("command", [
    "rtk rg -n record_project src",
    "cd src && grep -rn 'def record_project' .",
    "git grep record_project",
    "cd src; rg record_project",
    "cd src&&grep -rn record_project .",
    "true||rg record_project src 2>/dev/null",
    ["rg", "-n", "record_project", "src"],
    ["bash", "-lc", "rg -n record_project src"],
    ["/bin/zsh", "-c", "grep -rn record_project ."],
])
def test_symbol_searches_in_every_shape(command):
    assert _symbol(command) == "record_project"


@pytest.mark.parametrize("command", [
    "rg -n error", "rg -n TODO", "rg -n 'failed to connect'",
    "rg record_project docs/notes.md CHANGELOG.md",
    "ls src | grep record_project", "cat notes.txt | grep record_project",
    "rg record_project -t md", "rg record_project -g '*.md'", "rg --glob=*.json record_project",
    "find . -name '*.py' -delete", "find . -name '*.py' -exec rm {} +",
    "echo grep record_project", "git commit -m 'grep record_project'",
])
def test_no_symbol_search(command):
    hit, name, paths = searches.shell_search(command)
    assert name is None or not hit or searches.non_code(paths)


def test_a_find_for_code_files_is_a_search_without_a_symbol():
    hit, name, paths = searches.shell_search("find src -name '*.py'")
    assert hit and name is None and paths is searches.FIND



def test_every_symbol_search_in_a_line_is_counted():
    assert searches.count_symbol_searches("rg alpha_fn src; rg beta_fn src && grep -n gamma_fn x.py") == 3
    assert searches.count_symbol_searches("rg -n error src; ls | grep beta_fn; rg beta_fn docs/a.md") == 0
