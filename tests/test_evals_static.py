"""Static checks for the plugin eval suite in plugins/loadout/evals (no model calls).

Run the suite itself only with plugins/loadout/evals/run.sh (see its header)."""
import json
import os
import re
import shutil
import subprocess

import pytest

from loadout import configure, paths

EVALS = paths.kit_root() / "plugins/loadout/evals"
BROWSER_EVALS = paths.kit_root() / "plugins/loadout/evals-browser"  # opt-in suite
SKILLS = ("onboard", "docs-sync", "docs-audit", "configure")
GRADER_TYPES = {"regex", "tool_used", "tool_order", "file_exists", "llm", "baseline"}
# The stubs and scaffolds are bash scripts; Windows can't run them (same as tests/test_hooks.py).
posix_only = pytest.mark.skipif(os.name == "nt", reason="bash scripts; not run on Windows")


def _cases(*dirs):
    dirs = dirs or (EVALS, BROWSER_EVALS)
    return sorted({p.parent for d in dirs for p in d.glob("*/prompt.md")}
                  | {p.parent for d in dirs for p in d.glob("*/case.yaml")})


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
            assert script.is_file(), f"{script} missing"
            if os.name != "nt":
                assert os.access(script, os.X_OK), f"{script} not executable"


def test_grader_patterns_compile():
    """Patterns are JavaScript regexes; Python's re is close enough to catch typos before a paid run."""
    for g in [*EVALS.glob("*/graders/*.md"), *BROWSER_EVALS.glob("*/graders/*.md")]:
        text = g.read_text(encoding="utf-8")
        for raw in re.findall(r'(?:pattern|input_match):\s*("(?:[^"\\]|\\.)*")', text):
            try:
                re.compile(json.loads(raw))
            except re.error as e:  # pragma: no cover - message for the failing grader
                pytest.fail(f"{g}: {e}")


@posix_only
def test_safety_scripts_are_executable():
    for rel in ("run.sh", "global-state.sh", "bin/loadout", "bin/playwright-cli", "bin/browser-stub"):
        assert os.access(EVALS / rel, os.X_OK), rel


def test_run_sh_always_compares_global_state():
    run_sh = (EVALS / "run.sh").read_text(encoding="utf-8")
    assert "trap finish EXIT" in run_sh and "global-state.sh" in run_sh


def test_no_case_that_can_open_a_browser_runs_by_default():
    for case in _cases(EVALS):
        files = [case / "prompt.md", *(case / "graders").glob("*.md")]
        if (case / "case.yaml").exists():
            files.append(case / "case.yaml")
        for f in files:
            hit = re.search(r"playwright|chromium|firefox|google-chrome|headless|\bbrowser\b", f.read_text(encoding="utf-8"), re.I)
            assert not hit, f"{f} mentions {hit.group(0)!r}: browser cases belong in evals-browser/ (opt-in)"
    run_sh = (EVALS / "run.sh").read_text(encoding="utf-8")
    for b in ("playwright-cli", "chromium", "google-chrome", "firefox"):
        assert b in run_sh, f"run.sh must stub {b}"


def test_routing_case_carries_the_current_tooling_rule():
    """Eval runs don't load ~/.claude/rules, so the case appends rules/tooling.md as a YAML block."""
    text = (BROWSER_EVALS / "rules-ui-verification/prompt.md").read_text(encoding="utf-8")
    block = re.search(r"^append_system_prompt: \|\n((?:  .*\n|\n)+)", text, re.M).group(1)
    appended = "".join(line[2:] if line.strip() else "\n" for line in block.splitlines(keepends=True))
    rule = (paths.kit_root() / "rules/tooling.md").read_text(encoding="utf-8")
    assert appended == rule, "regenerate the case's append_system_prompt from rules/tooling.md"


def test_every_scaffold_goes_through_the_guard():
    for case in _cases():
        m = re.search(r"scaffold_script:\s*(\S+)", (case / "case.yaml").read_text(encoding="utf-8"))
        assert m, case.name
        text = (case / m.group(1)).read_text(encoding="utf-8")
        target = re.search(r"lib/([\w-]+\.sh)", text)
        assert target, f"{case.name}: scaffold must source lib/common.sh (directly or via a lib script)"
        lib = (EVALS / "lib" / target.group(1)).read_text(encoding="utf-8")
        assert target.group(1) == "common.sh" or "common.sh" in lib, case.name


# --- bash stubs and the scaffold guard (POSIX only) ---

def _stub_dir(tmp_path, name="loadout-eval-stub.test"):
    stub = tmp_path / name
    stub.mkdir()
    shutil.copy(EVALS / "bin/loadout", stub / "loadout")
    shutil.copy(EVALS / "bin/playwright-cli", stub / "playwright-cli")
    shutil.copy(EVALS / "bin/browser-stub", stub / "chromium")
    for f in stub.iterdir():
        f.chmod(0o755)
    return stub


def _source_common(home, cwd, path):
    env = {"HOME": str(home), "PATH": path, "TERM": "dumb"}
    return subprocess.run(["bash", "-c", f'. "{EVALS}/lib/common.sh" && echo GUARD-PASSED'],
                          cwd=cwd, env=env, capture_output=True, text=True)


@posix_only
def test_guard_allows_an_eval_run(tmp_path):
    home = tmp_path / "claude-eval-abc123" / "home"
    (home / "cwd").mkdir(parents=True)
    stub = _stub_dir(tmp_path)
    r = _source_common(home, home / "cwd", f"{stub}:{os.environ['PATH']}")
    assert r.returncode == 0 and "GUARD-PASSED" in r.stdout, r.stderr


@posix_only
@pytest.mark.parametrize("problem", ["real-home", "not-eval-home", "no-stub", "stub-not-first", "cwd-outside"])
def test_guard_refuses_outside_an_eval_run(tmp_path, problem):
    home = tmp_path / "claude-eval-abc123" / "home"
    (home / "cwd").mkdir(parents=True)
    cwd = home / "cwd"
    stub = _stub_dir(tmp_path)
    path = f"{stub}:{os.environ['PATH']}"
    if problem == "real-home":
        home = os.path.expanduser("~")
        cwd = tmp_path
    elif problem == "not-eval-home":
        home = tmp_path / "somewhere" / "home"
        (home / "cwd").mkdir(parents=True)
        cwd = home / "cwd"
    elif problem == "no-stub":
        path = os.environ["PATH"]
    elif problem == "stub-not-first":
        path = f"/usr/bin:{stub}:{os.environ['PATH']}"
    elif problem == "cwd-outside":
        cwd = tmp_path
    r = _source_common(home, cwd, path)
    assert r.returncode == 70 and "GUARD-PASSED" not in r.stdout
    assert "refusing to scaffold" in r.stderr


@posix_only
def test_browser_stub_never_starts_a_browser(tmp_path):
    r = subprocess.run([str(EVALS / "bin/browser-stub"), "--headless", "--screenshot"], cwd=tmp_path)
    assert r.returncode == 127
    assert "browser-stub --headless --screenshot" in (tmp_path / ".browser-calls.log").read_text()


@posix_only
def test_stub_ids_match_the_real_configure_show(fake_home, tmp_path):
    """The stub's `configure show` output must only use ids the real engine prints."""
    out = subprocess.run([str(EVALS / "bin/loadout"), "configure", "show"], cwd=tmp_path,
                         capture_output=True, text=True, check=True).stdout
    stub_ids = set(re.findall(r"id: (\S+ \S+)", out))
    real_ids = set(re.findall(r"id: (\S+ \S+)", configure.show()))
    assert stub_ids and stub_ids <= real_ids, stub_ids - real_ids
    assert (tmp_path / ".loadout-calls.log").read_text() == "configure show\n"


@posix_only
def test_stub_ignores_hooks(tmp_path):
    subprocess.run([str(EVALS / "bin/loadout"), "hook-session-start"], cwd=tmp_path, check=True)
    assert not (tmp_path / ".loadout-calls.log").exists()
