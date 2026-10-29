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
        assert set(prof) <= {"description", "settings", "mcp", "install", "commands", "done_when", "notes", "why"}, path
        entries = {f"{part}.{key}" for part in ("settings", "mcp") for key in prof.get(part, {})}
        why = prof.get("why", {})
        assert set(why) == entries and all(isinstance(t, str) and t for t in why.values()), path
        own = prof.get("settings", {}).get("extraKnownMarketplaces", {})  # a profile may bring its own (ADR 0037)
        for plugin_id in prof.get("install", []):
            assert plugin_id.split("@")[1] in _declared_marketplaces() | set(own), plugin_id
        for name, cfg in own.items():
            assert cfg.get("autoUpdate") is True and cfg["source"].get("repo"), name
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
    text = re.sub(r"^```.*?^```", "", path.read_text(encoding="utf-8"), flags=re.S | re.M)  # comments in code are not headings
    for line in text.splitlines():
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


def test_codebase_memory_installers_skip_agent_config():
    entry = next(e for e in _json("catalog.json")["entries"] if e["id"] == "codebase-memory-mcp")
    for key in ("install", "update"):
        for plat in ("posix", "windows"):
            cmds = entry[key][plat]
            assert cmds, (key, plat)
            for cmd in cmds:
                assert "--skip-config" in " ".join(cmd), (key, plat, cmd)
    assert "manual" not in entry  # Windows has a real install command now


def test_connector_field_only_on_plugins():
    entries = _json("catalog.json")["entries"]
    with_connector = {e["id"]: e for e in entries if "connector" in e}
    assert set(with_connector) >= {"plugin-wiley-scholar-gateway", "plugin-context7"}
    for e in with_connector.values():
        assert e["kind"] == "plugin" and e["connector"].startswith("claude.ai "), e["id"]
    wiley = with_connector["plugin-wiley-scholar-gateway"]
    # kept, not scoped down: the thesis profile does not enable it, so "loadout profile thesis" would drop it
    assert wiley["status"] == "alternative" and "profile" not in wiley
    thesis = _json("profiles/thesis.json")
    assert "wiley-scholar-gateway@life-sciences" not in thesis["settings"]["enabledPlugins"]
    assert "wiley-scholar-gateway@life-sciences" in thesis["notes"]


def test_toolchain_installs_in_user_space():
    entries = {e["id"]: e for e in _json("catalog.json")["entries"]}
    for tool in ("claude", "node", "gh", "rust-analyzer", "mise"):
        for plat in ("posix", "windows"):
            assert entries[tool]["install"][plat], (tool, plat)
    for cmds in (e.get("install", {}) for e in entries.values()):
        for cmd in (c for plat in cmds.values() for c in plat):
            assert "sudo" not in cmd and "sudo" not in " ".join(cmd), cmd
    assert entries["mise"]["helper"] is True
    assert entries["node"]["needs"] == ["mise"] and entries["serena"]["needs"] == ["uv"]
    for tool in ("playwright-cli", "pyright", "typescript-language-server"):
        assert entries[tool]["needs"] == ["node"]
    known = set(entries)
    for e in entries.values():
        assert set(e.get("needs", [])) <= known, e["id"]


VERDICT_PREFIXES = ("mcp-", "plugin-", "marketplace-", "skill-", "skills-", "hook-")


def test_catalog_short_reasons():
    for e in _json("catalog.json")["entries"]:
        if e["id"].startswith(VERDICT_PREFIXES):
            assert e.get("short"), f"{e['id']}: add a short reason"
        if "short" in e:
            s = e["short"]
            assert "\n" not in s and len(s) <= 60 and not s.endswith("."), e["id"]


def test_target_field_only_on_binaries_and_claude_only_plugins():
    for entry in _json("catalog.json")["entries"]:
        if "target" in entry:  # a plugin's target only keeps it out of Codex (catalog.claude_only_plugins)
            assert (entry["kind"] == "binary" and entry["target"] in ("claude", "codex")
                    or entry["kind"] == "plugin" and entry["target"] == "claude"), entry["id"]
