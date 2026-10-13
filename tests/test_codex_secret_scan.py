"""adopt's plaintext-secret scan looks at ~/.codex/config.toml too (report only)."""
import json

from loadout import adopt, out, paths, secrets

TOKEN = "ghp_" + "Z" * 36  # built here so the repo's secret scan does not flag this file


def _config(text):
    p = paths.codex_home() / "config.toml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_a_plaintext_secret_in_a_codex_server_is_found(fake_home):
    _config(f'[mcp_servers.gh]\ncommand = "gh-mcp"\nargs = ["--token={TOKEN}"]\n[mcp_servers.gh.env]\nGITHUB_TOKEN = "{TOKEN}"\n')
    found = secrets.scan_codex()
    assert {(f.server, f.field) for f in found} == {("gh", "env"), ("gh", "args")}
    assert all(f.location == "~/.codex/config.toml" and not f.fixable for f in found)


def test_a_file_that_does_not_parse_gives_no_findings(fake_home):
    _config("[mcp_servers.gh\n")
    assert secrets.scan_codex() == []


def test_codex_only_adopt_reports_it_without_the_value(fake_home, fake_runner, monkeypatch, capsys):
    monkeypatch.setattr(out, "VERBOSE", True)
    paths.personal_root().mkdir(parents=True)
    (paths.personal_root() / "targets.json").write_text(json.dumps({"claude": False, "codex": True}))
    _config(f'[mcp_servers.gh]\ncommand = "gh-mcp"\n[mcp_servers.gh.env]\nGITHUB_TOKEN = "{TOKEN}"\n')
    adopt.run(False, None, set(), False, ask=lambda q: "", with_versions=False, interactive=False)
    text = capsys.readouterr().out
    assert "~/.codex/config.toml" in text and TOKEN not in text
    assert "env_vars" in text


def test_a_secret_you_add_to_a_table_loadout_wrote_is_found(fake_home, monkeypatch):
    from loadout import codex
    _config('[mcp_servers.serena]\ncommand = "uvx"\n')
    monkeypatch.setattr(codex, "read_record",
                        lambda: {"tables": {"serena": '[mcp_servers.serena]\ncommand = "uvx"'}, "keys": {}})
    assert secrets.scan_codex() == []  # loadout's own table, unchanged
    _config(f'[mcp_servers.serena]\ncommand = "uvx"\n[mcp_servers.serena.env]\nGITHUB_TOKEN = "{TOKEN}"\n')
    assert [(f.server, f.field) for f in secrets.scan_codex()] == [("serena", "env")]


def test_the_codex_hint_fits_the_field():
    def f(field):
        return secrets.Finding(server="s", field=field, key="K", value="v", location="~/.codex/config.toml", fixable=False)
    assert "env_vars" in adopt._codex_hint(f("env"))
    assert "env_http_headers" in adopt._codex_hint(f("headers"))
    assert adopt._codex_hint(f("args")) == "" and adopt._codex_hint(f("url")) == ""
