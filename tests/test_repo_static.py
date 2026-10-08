import json
import re
import subprocess

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
