import pytest

from loadout import catalog


def _e(i, needs=()):
    return {"id": i, "kind": "binary", "needs": list(needs)}


def test_install_order_puts_needs_first_and_keeps_catalog_order_otherwise():
    entries = [_e("claude"), _e("uv"), _e("playwright-cli", ["node"]), _e("node", ["mise"]), _e("mise"), _e("serena", ["uv"])]
    assert [e["id"] for e in catalog.install_order(entries)] == ["claude", "uv", "mise", "node", "playwright-cli", "serena"]


def test_install_order_rejects_cycles_and_unknown_ids():
    with pytest.raises(ValueError):
        catalog.install_order([_e("a", ["b"]), _e("b", ["a"])])
    with pytest.raises(ValueError):
        catalog.install_order([_e("a", ["nope"])])


def test_real_catalog_orders_cleanly():
    ids = [e["id"] for e in catalog.install_order(catalog.binaries())]
    assert ids.index("uv") < ids.index("serena")
    assert ids.index("mise") < ids.index("node") < ids.index("playwright-cli")


def test_mise_reason_names_every_tool_mise_installs():
    entries = catalog.load()
    names = {"node": "Node.js", "gh": "gh", "rust-analyzer": "rust-analyzer", "codex": "Codex"}
    installed = [e["id"] for e in entries if "mise" in e.get("needs", [])]
    reason = next(e for e in entries if e["id"] == "mise")["reason"]
    assert set(installed) <= set(names), installed
    for tool in installed:
        assert names[tool] in reason, tool
