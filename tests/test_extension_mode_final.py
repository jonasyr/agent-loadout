"""Final-review findings for the extension-mode PR, each pinned by a test that failed first."""
from pathlib import Path

from loadout import bootstrap, codex, codex_hooks, out, paths, runner, vscode

ROOT = Path(__file__).resolve().parent.parent


def test_changed_kit_hooks_do_not_matter_while_the_plugin_is_off(codex_ext, monkeypatch):
    key = f"{codex_hooks.path()}:session_start:0:0"
    monkeypatch.setattr(codex_hooks, "serena_items", lambda: {key: "activate"})
    path = paths.codex_home() / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'[hooks.state]\n"{key}" = {{ trusted_hash = "h" }}\n')
    assert codex.hooks_status(remember=True) == "trusted"
    monkeypatch.setattr(codex, "_hooks_digest", lambda: "the kit's hooks changed")
    assert codex.hooks_status() == "trusted"  # the plugin is not on: its hooks cannot run, nothing to approve


def test_the_cli_version_is_asked_once_per_binary(fake_home, fake_runner, tmp_path):
    exe = tmp_path / "bin" / "codex"
    exe.parent.mkdir()
    exe.write_text("x")
    fake_runner.paths["codex"] = str(exe)
    fake_runner.responses[("codex", "--version")] = runner.Result(0, "codex-cli 0.162.1\n", "")
    for _ in range(3):
        codex.mode()
        codex.program()
    assert sum(1 for c in fake_runner.calls if c == ["codex", "--version"]) == 1


def test_the_extension_starts_the_plugins_mcp_servers_too(codex_ext):
    path = paths.codex_home() / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('[plugins."loadout@agent-loadout"]\nenabled = true\n')
    assert "codebase-memory-mcp" in vscode.mcp_commands("codex")
    path.write_text('[plugins."loadout@agent-loadout"]\nenabled = false\n')
    assert "codebase-memory-mcp" not in vscode.mcp_commands("codex")


def test_next_line_names_the_hooks_icon_next_to_a_broken_cli(codex_ext, fake_runner, capsys, monkeypatch):
    fake_runner.missing.discard("codex")
    fake_runner.responses[("codex", "--version")] = runner.Result(0, "codex-cli 0.150.0\n", "")
    (paths.home() / ".config/loadout/personal").mkdir(parents=True)
    monkeypatch.setattr(out, "VERBOSE", False)
    monkeypatch.setattr(codex, "hooks_status", lambda remember=False: "untrusted")
    bootstrap.bootstrap(install=False, yes=True, plugins=False, adopt_step=False, ask=lambda q: "", interactive=False,
                        agents="codex", codex_cli=False)
    assert "the hooks icon in the prompt bar, then Allow all." in capsys.readouterr().out


def test_no_page_repeats_the_old_extension_claims():
    stale = ("runs no plugin hooks", "(default yes)", "approve them once in the CLI", "installs the recommended Codex CLI",
             "loads no plugins", "has no /hooks", "plugins do not load")
    hits = [(p.relative_to(ROOT).as_posix(), s) for p in (ROOT / "docs").rglob("*.md")
            if "/adr/" not in p.as_posix() and "/superpowers/" not in p.as_posix() and "examples" not in p.parts
            for s in stale if s in p.read_text(encoding="utf-8")]
    assert not hits, hits
