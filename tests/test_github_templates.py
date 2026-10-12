"""Issue forms and the PR template (.github/). Schema checks: `uvx check-jsonschema --builtin-schema vendor.github-issue-forms`."""
import re

import pytest

from loadout import paths
from loadout.__main__ import main

GITHUB = paths.kit_root() / ".github"
FORMS = sorted((GITHUB / "ISSUE_TEMPLATE").glob("[0-9]-*.yml"))
LABELS = {"bug", "enhancement", "catalog", "documentation", "question"}  # these exist on GitHub; a missing one is skipped silently


def _text(path):
    return path.read_text(encoding="utf-8").replace("\r", "")


def test_every_form_applies_one_existing_label():
    assert len(FORMS) == 5
    for form in FORMS:
        found = re.findall(r'^labels: \["([^"]+)"\]$', _text(form), re.M)
        assert len(found) == 1 and found[0] in LABELS, f"{form.name}: {found}"


def test_ids_are_unique_within_each_form():
    for form in FORMS:
        ids = re.findall(r"^    id: (\S+)$", _text(form), re.M)
        assert len(ids) == len(set(ids)), form.name


def test_blank_issues_are_off_and_security_goes_private():
    config = _text(GITHUB / "ISSUE_TEMPLATE" / "config.yml")
    assert "blank_issues_enabled: false" in config
    assert "https://github.com/jonasyr/agent-loadout/security/advisories/new" in config


def _required(form, field_id):
    block = re.search(rf"^    id: {field_id}\n(.*?)(?=^  - type:|\Z)", _text(form), re.M | re.S)
    assert block, f"{form.name}: no field {field_id}"
    return "required: true" in block.group(1)


def test_bug_form_requires_what_a_report_needs():
    bug = GITHUB / "ISSUE_TEMPLATE" / "1-bug.yml"
    for field in ("what", "steps", "platform", "versions", "check"):
        assert _required(bug, field), field
    text = _text(bug)
    assert "loadout --version" in text and "loadout check --verbose" in text and "render: shell" in text


@pytest.mark.parametrize("argv", [["--version"], ["check", "--help"]])
def test_commands_the_bug_form_asks_for_exist(argv, fake_runner, capsys):
    with pytest.raises(SystemExit) as exit_:
        main(argv)
    assert exit_.value.code == 0
    if argv == ["check", "--help"]:
        assert "--verbose" in capsys.readouterr().out


def test_pr_template_asks_for_testing_and_docs_and_stays_short():
    text = _text(GITHUB / "pull_request_template.md")
    assert [h for h in re.findall(r"^## (.+)$", text, re.M)] == ["Summary", "How I tested", "Docs"]
    assert text.count("- [ ]") == 2 and len(text.splitlines()) <= 20
