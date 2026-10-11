import json
import re
import subprocess

import pytest

from loadout import paths

ROOT = paths.kit_root()
STATUSES = {"core", "profile", "superseded", "deprecated", "recommended", "alternative", "system", "review"}
KINDS = {"mcp", "plugin", "marketplace", "skill", "hook", "binary"}


def _json(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def test_all_json_files_parse():
    for path in ROOT.rglob("*.json"):
        if ".git" in path.parts:
            continue
        json.loads(path.read_text(encoding="utf-8"))


def _declared_marketplaces():
    return set(_json("settings.base.json")["extraKnownMarketplaces"]) | {"claude-plugins-official"}


def test_settings_base_plugins_reference_declared_marketplaces():
    base = _json("settings.base.json")
    for plugin_id in base["enabledPlugins"]:
        assert plugin_id.split("@")[1] in _declared_marketplaces(), plugin_id
    for name, cfg in base["extraKnownMarketplaces"].items():
        assert cfg.get("autoUpdate") is True, name


def test_profiles_are_well_formed():
    for path in (ROOT / "profiles").glob("*.json"):
        prof = json.loads(path.read_text(encoding="utf-8"))
        assert prof["description"]
        assert set(prof) <= {"description", "settings", "mcp", "install", "commands", "notes"}, path
        for plugin_id in prof.get("install", []):
            assert plugin_id.split("@")[1] in _declared_marketplaces(), plugin_id
        for server in prof.get("mcp", {}).get("mcpServers", {}).values():
            for arg in server.get("args", []):
                assert "@latest" not in arg, f"unpinned version in {path}"


def test_catalog_entries_are_well_formed():
    entries = _json("catalog.json")["entries"]
    ids = [e["id"] for e in entries]
    assert len(ids) == len(set(ids)), "duplicate catalog ids"
    for e in entries:
        assert e["kind"] in KINDS, e["id"]
        assert e["status"] in STATUSES, e["id"]
        assert e["reason"], e["id"]
        assert e["match"].get("names") or e["match"].get("contains"), e["id"]
        if e["status"] == "profile":
            assert (ROOT / "profiles" / f"{e['profile']}.json").exists(), e["id"]
        if e["kind"] == "binary":
            assert "version" in e and "cmd" in e["version"], e["id"]
        if "offer" in e:
            assert set(e["offer"]) <= {"plugin", "mcp", "needs"}, e["id"]
            if "plugin" in e["offer"]:
                assert e["offer"]["plugin"].split("@")[1] in _declared_marketplaces(), e["id"]
            for server in e["offer"].get("mcp", {}).values():
                assert all("@latest" not in a for a in server.get("args", [])), e["id"]


def test_rules_and_templates_exist():
    for name in ("tooling", "docs-policy", "memory-policy", "workflow", "rtk"):
        assert (ROOT / "rules" / f"{name}.md").read_text(encoding="utf-8").strip()
    assert "{{PROJECT_NAME}}" in (ROOT / "templates/project/AGENTS.md").read_text(encoding="utf-8")
    assert (ROOT / "templates/project/CLAUDE.md").read_text(encoding="utf-8").strip() == "@AGENTS.md"


SECRET_PATTERNS = [
    r"gh[pousr]_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}", r"sk-[A-Za-z0-9_-]{20,}",
    r"apk_[A-Za-z0-9_=-]{16,}", r"xox[baprs]-[A-Za-z0-9-]{10,}", r"AKIA[0-9A-Z]{16}",
]


def test_no_secrets_in_tracked_files():
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    for rel in files:
        path = ROOT / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in SECRET_PATTERNS:
            assert not re.search(pattern, text), f"possible secret in {rel}"
    assert "secrets.env" not in files


def test_advisor_mark_is_preapproved():
    """The execution-advisor skill runs it on every evaluation; it must not prompt each time."""
    assert "Bash(loadout advisor-mark:*)" in _json("settings.base.json")["permissions"]["allow"]


_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def _tracked_markdown():
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "*.md", "**/*.md"], capture_output=True, text=True, check=True)
    files = sorted({ROOT / f for f in out.stdout.split()})
    # working documents; eval fixtures and the example's "before" tree contain planted errors, including broken links
    skip = ("docs/superpowers/", "plugins/loadout/evals/")
    return [
        f for f in files
        if not f.relative_to(ROOT).as_posix().startswith(skip) and "/before/" not in f.relative_to(ROOT).as_posix()
    ]


def _anchors(path):
    """GitHub-style heading anchors of a Markdown file."""
    out = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"#{1,6}\s+(.*)", line)
        if m:
            slug = re.sub(r"[^\w\- ]", "", m.group(1).strip().lower()).replace(" ", "-")
            out.add(slug)
    return out


def test_relative_links_resolve():
    broken = []
    for md in _tracked_markdown():
        text = re.sub(r"```.*?```", "", md.read_text(encoding="utf-8"), flags=re.S)  # ignore code blocks
        for target in _LINK.findall(text):
            if re.match(r"[a-z]+:", target) or target.startswith("#") and not target[1:]:
                continue
            path_part, _, anchor = target.partition("#")
            dest = (md.parent / path_part).resolve() if path_part else md
            if not dest.exists():
                broken.append(f"{md.relative_to(ROOT)} -> {target}")
            elif anchor and dest.suffix == ".md" and anchor.lower() not in _anchors(dest):
                broken.append(f"{md.relative_to(ROOT)} -> {target} (no such heading)")
    assert not broken, "\n".join(broken)


def test_no_nested_claude_md():
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True, check=True)
    # eval fixtures and templates/project need the real name: the evals and `loadout init` read it
    allowed = ("plugins/loadout/evals/", "templates/")
    nested = [f for f in out.stdout.split() if f.endswith("CLAUDE.md") and f != "CLAUDE.md" and not f.startswith(allowed)]
    assert not nested, f"nested CLAUDE.md files are loaded by Claude Code; rename them CLAUDE.md.example: {nested}"


def test_claude_md_imports_agents_md():
    assert (ROOT / "CLAUDE.md").read_text(encoding="utf-8").strip() == "@AGENTS.md"
    assert (ROOT / "AGENTS.md").exists()
