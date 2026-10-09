"""Static checks for the plugin eval suite in plugins/loadout/evals (no model calls).

Run the suite itself with plugins/loadout/evals/run.sh (see its header)."""
import os
import re
import subprocess

import pytest

from loadout import configure, paths

EVALS = paths.kit_root() / "plugins/loadout/evals"
SKILLS = ("onboard", "docs-sync", "docs-audit", "configure")
GRADER_TYPES = {"regex", "tool_used", "tool_order", "file_exists", "llm", "baseline"}


BROWSER_EVALS = paths.kit_root() / "plugins/loadout/evals-browser"  # opt-in suite


def _cases():
    return sorted({p.parent for d in (EVALS, BROWSER_EVALS) for p in d.glob("*/prompt.md")}
                  | {p.parent for d in (EVALS, BROWSER_EVALS) for p in d.glob("*/case.yaml")})


def _frontmatter(path):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n?(.*)", text, re.S)
    assert m, f"{path}: missing frontmatter"
    keys = dict(re.findall(r"^([a-z_]+):\s*(.*)$", m.group(1), re.M))
    return keys, m.group(2)


def test_every_skill_has_cases():
    names = {c.name for c in _cases()}
    for skill in SKILLS:
        assert any(n.startswith(skill) for n in names), f"no eval case for {skill}"


@pytest.mark.parametrize("case", _cases(), ids=lambda p: p.name)
def test_case_files_are_well_formed(case):
    graders = sorted((case / "graders").glob("*.md"))
    assert graders, f"{case.name}: a case without graders fails to load"
    for g in graders:
        keys, _ = _frontmatter(g)
        assert keys.get("type") in GRADER_TYPES, f"{g}: unknown grader type"
    keys, body = _frontmatter(case / "prompt.md")
    assert body.strip(), f"{case.name}: empty prompt"
    case_yaml = case / "case.yaml"
    if case_yaml.exists():
        text = case_yaml.read_text(encoding="utf-8")
        assert 'schema_version: "1.1"' in text and f"name: {case.name}" in text
        m = re.search(r"scaffold_script:\s*(\S+)", text)
        if m:
            script = case / m.group(1)
            assert script.is_file() and os.access(script, os.X_OK), f"{script} missing or not executable"


def test_safety_scripts_are_executable():
    for rel in ("run.sh", "global-state.sh", "bin/loadout", "bin/playwright-cli", "bin/browser-stub"):
        assert os.access(EVALS / rel, os.X_OK), rel


def test_no_case_that_can_open_a_browser_runs_by_default():
    for case in _cases():
        if "browser" in (case / "case.yaml").read_text(encoding="utf-8") if (case / "case.yaml").exists() else False:
            assert case.parent == BROWSER_EVALS, f"{case.name} must live in evals-browser/ (opt-in)"
    run_sh = (EVALS / "run.sh").read_text(encoding="utf-8")
    for b in ("playwright-cli", "chromium", "google-chrome", "firefox"):
        assert b in run_sh, f"run.sh must stub {b}"


def test_browser_stub_never_starts_a_browser(tmp_path):
    r = subprocess.run([str(EVALS / "bin/browser-stub"), "--headless", "--screenshot"], cwd=tmp_path)
    assert r.returncode == 127
    assert "browser-stub --headless --screenshot" in (tmp_path / ".browser-calls.log").read_text()


def test_routing_case_carries_the_current_tooling_rule():
    """Eval runs don't load ~/.claude/rules, so the case appends rules/tooling.md as a YAML block."""
    text = (BROWSER_EVALS / "rules-ui-verification/prompt.md").read_text(encoding="utf-8")
    block = re.search(r"^append_system_prompt: \|\n((?:  .*\n|\n)+)", text, re.M).group(1)
    appended = "".join(line[2:] if line.strip() else "\n" for line in block.splitlines(keepends=True))
    rule = (paths.kit_root() / "rules/tooling.md").read_text(encoding="utf-8")
    assert appended == rule, "regenerate the case's append_system_prompt from rules/tooling.md"


def test_stub_ids_match_the_real_configure_show(fake_home, tmp_path):
    """The stub's `configure show` output must only use ids the real engine prints."""
    out = subprocess.run([str(EVALS / "bin/loadout"), "configure", "show"], cwd=tmp_path,
                         capture_output=True, text=True, check=True).stdout
    stub_ids = set(re.findall(r"id: (\S+ \S+)", out))
    real_ids = set(re.findall(r"id: (\S+ \S+)", configure.show()))
    assert stub_ids and stub_ids <= real_ids, stub_ids - real_ids
    assert (tmp_path / ".loadout-calls.log").read_text() == "configure show\n"


def test_stub_ignores_hooks(tmp_path):
    subprocess.run([str(EVALS / "bin/loadout"), "hook-session-start"], cwd=tmp_path, check=True)
    assert not (tmp_path / ".loadout-calls.log").exists()
