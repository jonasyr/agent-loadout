import pytest

from loadout import secrets

PAT = "ghp_" + "a1B2" * 8
HEX = "0123456789abcdef" * 3
B64 = "Ab3dE6gH9jK2mN5pQ8sT1vW4yZ7bC0eF3hI6kL9n"


@pytest.mark.parametrize("text,leak", [
    (f"npx server-github GITHUB_PERSONAL_ACCESS_TOKEN={PAT}", PAT),
    ("server --api-key=sk-" + "q" * 30, "sk-" + "q" * 30),
    ("server --token abcdefgh12345", "abcdefgh12345"),
    ("https://mcp.example.com/sse?api_key=s3cr3tv4lue99&x=1", "s3cr3tv4lue99"),
    ('{"headers": {"Authorization": "Bearer abcdefghijklmnop"}}', "abcdefghijklmnop"),
    (f"tool --config CACHE={HEX}", HEX),
    (f"tool SEED={B64}", B64),
    ('{"env": {"DB_PASSWORD": "p4ss word;x$y!"}}', "p4ss word;x$y!"),
])
def test_redact_masks_secrets(text, leak):
    out = secrets.redact(text)
    assert leak not in out
    assert "***" in out


def test_redact_leaves_ordinary_text():
    text = "serena start-mcp-server --context=claude-code --project-from-cwd https://x.dev/mcp?page=2"
    assert secrets.redact(text) == text


def test_high_entropy_only_for_keyed_values():
    assert secrets.looks_secret("CACHE", HEX, keyed_arg=True)
    assert not secrets.looks_secret("3", HEX)
    assert not secrets.looks_secret("MODE", "a" * 40, keyed_arg=True)  # no mix of cases/digits


# --- secrets.env format and scan coverage (R-D) ---
import json
import os
import subprocess

from loadout import adopt, backup, bootstrap, paths, runner

NASTY = "p4ss word;touch PWNED $HOME `id` \"q\" 'single' #hash"


def _server_with(home, value, key="DB_PASSWORD"):
    (home / ".claude.json").write_text(json.dumps({"mcpServers": {"db": {"command": "x", "env": {key: value}}}}))


def test_quote_roundtrip():
    for value in ["plain", NASTY, "it's", "''", "a\\b"]:
        name, parsed = secrets.parse_env_line("X=" + secrets.quote(value))
        assert (name, parsed) == ("X", value)


@pytest.mark.skipif(os.name == "nt", reason="sources with sh")
def test_fix_secrets_output_sources_cleanly_in_sh(fake_home, fake_runner, tmp_path):
    _server_with(fake_home, NASTY)
    found = secrets.scan(json.loads((fake_home / ".claude.json").read_text()))
    adopt.fix_secrets(found, backup.Backup())
    work = tmp_path / "work"
    work.mkdir()
    script = f'set -a; . "{paths.secrets_file()}"; set +a; printf %s "$DB_DB_PASSWORD"'
    proc = subprocess.run(["sh", "-c", script], cwd=work, capture_output=True, text=True, env={"PATH": "/usr/bin:/bin", "HOME": str(fake_home)})
    assert proc.stderr == ""
    assert proc.stdout == NASTY
    assert not (work / "PWNED").exists()


def test_fix_secrets_skips_values_with_newlines(fake_home, fake_runner):
    _server_with(fake_home, "line1-secret-value\nline2")
    found = secrets.scan(json.loads((fake_home / ".claude.json").read_text()))
    out = adopt.fix_secrets(found, backup.Backup())
    assert any("newline" in line for line in out)
    assert not [c for c in fake_runner.calls if c[:3] == ["claude", "mcp", "add-json"]]


def test_secrets_file_created_private_and_recorded(fake_home, fake_runner):
    _server_with(fake_home, "x" * 20)
    found = secrets.scan(json.loads((fake_home / ".claude.json").read_text()))
    bk = backup.Backup()
    adopt.fix_secrets(found, bk)
    if os.name != "nt":
        assert paths.secrets_file().stat().st_mode & 0o777 == 0o600
    assert any(s["undo"].get("created") == str(paths.secrets_file()) for s in bk.steps)


def test_var_name_collision_gets_suffix(fake_home, fake_runner):
    paths.secrets_file().parent.mkdir(parents=True)
    paths.secrets_file().write_text("DB_DB_PASSWORD='other-value-123456'\n")
    _server_with(fake_home, "y" * 20)
    found = secrets.scan(json.loads((fake_home / ".claude.json").read_text()))
    out = adopt.fix_secrets(found, backup.Backup())
    env = secrets.load_env(paths.secrets_file())
    assert env["DB_DB_PASSWORD"] == "other-value-123456"
    assert env["DB_DB_PASSWORD_2"] == "y" * 20
    assert "${DB_DB_PASSWORD_2}" in [c for c in fake_runner.calls if c[:3] == ["claude", "mcp", "add-json"]][0][-1]


def test_scan_all_reports_other_locations(fake_home):
    pat = "ghp_" + "Q" * 30
    (fake_home / ".claude.json").write_text(json.dumps({
        "mcpServers": {"web": {"type": "http", "url": "https://x.dev/mcp?api_key=abcdef123456789&page=2"},
                       "broken": "not-a-dict"},
        "projects": {"/p/app": {"mcpServers": {"gh": {"command": "x", "env": {"GITHUB_TOKEN": pat}}}}},
    }))
    (fake_home / ".claude").mkdir()
    (fake_home / ".claude/.mcp.json").write_text(json.dumps({"mcpServers": {"m": {"command": "x", "headers": {"X-Api-Key": "k" * 20}}}}))
    (fake_home / ".claude/settings.json").write_text(json.dumps({"env": {"ANTHROPIC_API_KEY": "sk-ant-" + "z" * 30}}))
    paths.personal_root().mkdir(parents=True)
    (paths.personal_root() / "mcp.json").write_text(json.dumps({"mcpServers": {"p": {"command": "x", "args": ["TOKEN=" + "t" * 20]}}}))
    found = secrets.scan_all()
    where = {(f.server, f.field, f.location.split(" ")[0]) for f in found}
    assert ("web", "url", "~/.claude.json") in where
    assert ("gh", "env", "~/.claude.json") in where
    assert ("m", "headers", "~/.claude/.mcp.json") in where
    assert ("settings.json", "env", "~/.claude/settings.json") in where
    assert any(f.server == "p" and "mcp.json" in f.location for f in found)
    assert not any(f.fixable for f in found)


def test_scan_keyed_arg_high_entropy():
    cfg = {"mcpServers": {"s": {"command": "x", "args": ["CACHE_ID=" + "0123456789abcdef" * 3]}}}
    assert [f.key for f in secrets.scan(cfg)] == ["CACHE_ID"]


# --- shell / PowerShell loaders (R-D, R-H) ---

def test_rc_block_goes_to_shell_rc_even_when_other_rc_exists(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(paths, "platform_key", lambda: "posix")
    monkeypatch.setenv("SHELL", "/bin/zsh")
    (fake_home / ".bashrc").write_text("# old bashrc\n")
    bk = backup.Backup()
    bootstrap.setup_secrets(bk)
    assert bootstrap.RC_MARKER in (fake_home / ".zshrc").read_text()
    assert bootstrap.RC_MARKER in (fake_home / ".bashrc").read_text()
    created = {s["undo"].get("created") for s in bk.steps}
    assert str(fake_home / ".zshrc") in created and str(paths.secrets_file()) in created
    assert str(fake_home / ".bashrc") not in created


def test_rc_append_survives_non_utf8_rc(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(paths, "platform_key", lambda: "posix")
    monkeypatch.setenv("SHELL", "/bin/bash")
    (fake_home / ".bashrc").write_bytes(b"# caf\xe9\n")
    bootstrap.setup_secrets(backup.Backup())
    raw = (fake_home / ".bashrc").read_bytes()
    assert raw.startswith(b"# caf\xe9\n") and bootstrap.RC_MARKER.encode() in raw


def _windows(monkeypatch, fake_runner, fake_home, policy="RemoteSigned", pwsh=True):
    monkeypatch.setattr(paths, "platform_key", lambda: "windows")
    ps51 = fake_home / "Documents/WindowsPowerShell/Microsoft.PowerShell_profile.ps1"
    ps7 = fake_home / "Documents/PowerShell/Microsoft.PowerShell_profile.ps1"
    fake_runner.responses[("powershell", "-NoProfile", "-Command", "$PROFILE")] = runner.Result(0, f"{ps51}\r\n", "")
    fake_runner.responses[("pwsh", "-NoProfile", "-Command", "$PROFILE")] = runner.Result(0, f"{ps7}\r\n", "")
    fake_runner.responses[("powershell", "-NoProfile", "-Command", "Get-ExecutionPolicy")] = runner.Result(0, policy + "\r\n", "")
    if not pwsh:
        fake_runner.missing.add("pwsh")
    return ps51, ps7


def test_powershell_block_written_to_both_profiles(fake_home, fake_runner, monkeypatch):
    ps51, ps7 = _windows(monkeypatch, fake_runner, fake_home)
    out = bootstrap.setup_secrets(backup.Backup())
    for prof in (ps51, ps7):
        text = prof.read_text(encoding="utf-8")
        assert bootstrap.RC_MARKER in text and "& {" in text
    assert not any("Restricted" in line for line in out)
    bootstrap.setup_secrets(backup.Backup())
    assert ps51.read_text(encoding="utf-8").count(bootstrap.RC_MARKER) == 1


def test_powershell_profile_utf16_is_kept(fake_home, fake_runner, monkeypatch):
    ps51, _ = _windows(monkeypatch, fake_runner, fake_home, pwsh=False)
    ps51.parent.mkdir(parents=True)
    ps51.write_bytes("# mein Profil ü\r\n".encode("utf-16"))
    bootstrap.setup_secrets(backup.Backup())
    raw = ps51.read_bytes()
    assert raw[:2] in (b"\xff\xfe", b"\xfe\xff")
    text = raw.decode("utf-16")
    assert text.startswith("# mein Profil ü") and bootstrap.RC_MARKER in text


def test_powershell_restricted_policy_prints_note(fake_home, fake_runner, monkeypatch):
    _windows(monkeypatch, fake_runner, fake_home, policy="Restricted")
    out = bootstrap.setup_secrets(backup.Backup())
    assert any("Set-ExecutionPolicy -Scope CurrentUser RemoteSigned" in line for line in out)
    assert not [c for c in fake_runner.calls if "Set-ExecutionPolicy" in " ".join(c)]


def test_powershell_block_parses_quoted_format():
    block = bootstrap.PS_BLOCK
    assert "Replace(\"'\\''\", \"'\")" in block
    assert "$Matches[1]" in block and "SetEnvironmentVariable" in block


@pytest.mark.skipif(not (__import__("shutil").which("pwsh") or __import__("shutil").which("powershell")),
                    reason="needs PowerShell (runs on the Windows CI runner)")
def test_powershell_block_loads_values(tmp_path):
    import shutil
    env_file = tmp_path / "secrets.env"
    env_file.write_text("LOADOUT_T1=" + secrets.quote(NASTY) + "\n# c\nLOADOUT_T2='plain'\n", encoding="utf-8")
    block = bootstrap.PS_BLOCK.replace("Join-Path $HOME '.config/loadout/secrets.env'", f"'{env_file}'")
    script = tmp_path / "t.ps1"
    script.write_text(block + "\n[Console]::Out.Write($env:LOADOUT_T1 + '|' + $env:LOADOUT_T2)\n", encoding="utf-8-sig")
    exe = shutil.which("pwsh") or shutil.which("powershell")
    # -ExecutionPolicy Bypass applies to this one process only; -NoProfile keeps the real profile out of it
    proc = subprocess.run([exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.stdout == NASTY + "|plain", proc.stderr


def test_rewrite_returns_var_config_and_lines():
    from loadout import secrets
    cfg = {"command": "x", "env": {"API_KEY": "k" * 20}}
    found = secrets.scan({"mcpServers": {"srv": cfg}})
    known = {}
    new, lines, names = secrets.rewrite("srv", cfg, found, known)
    assert new["env"]["API_KEY"] == "${SRV_API_KEY}"
    assert cfg["env"]["API_KEY"] == "k" * 20          # original untouched
    assert lines == ["SRV_API_KEY='" + "k" * 20 + "'\n"] and names == ["SRV_API_KEY"]
    assert known == {"SRV_API_KEY": "k" * 20}


def test_rewrite_never_overwrites_a_different_value():
    from loadout import secrets
    cfg = {"command": "x", "env": {"API_KEY": "k" * 20}}
    found = secrets.scan({"mcpServers": {"srv": cfg}})
    new, lines, names = secrets.rewrite("srv", cfg, found, {"SRV_API_KEY": "other"})
    assert names == ["SRV_API_KEY_2"] and new["env"]["API_KEY"] == "${SRV_API_KEY_2}"


def test_append_env_creates_private_file_and_records_it(fake_home):
    import os, stat
    from loadout import backup, paths, secrets
    bk = backup.Backup()
    secrets.append_env(paths.secrets_file(), ["A='1'\n"], bk)
    assert paths.secrets_file().read_text() == "A='1'\n"
    if os.name != "nt":
        assert stat.S_IMODE(paths.secrets_file().stat().st_mode) == 0o600
    assert any("created" in s["undo"] for s in bk.steps)


def test_replace_user_server_records_undo_and_reports_ok(fake_home, fake_runner):
    from loadout import backup, personal_mcp
    bk = backup.Backup()
    assert personal_mcp.replace_user_server("srv", {"command": "a"}, {"command": "b"}, bk) == "ok"
    assert ["claude", "mcp", "remove", "-s", "user", "srv"] in fake_runner.calls
    assert [s["undo"]["run"][2] for s in bk.steps] == ["add-json", "remove"]


def test_replace_user_server_cmd_shim_removes_nothing(fake_home, fake_runner, monkeypatch):
    from loadout import backup, personal_mcp, runner
    monkeypatch.setattr(runner, "would_refuse", lambda cmd: True)
    res = personal_mcp.replace_user_server("srv", {"command": "a"}, {"command": "b"}, backup.Backup())
    assert res.startswith("manual: ")
    assert [c for c in fake_runner.calls if c[:1] == ["claude"]] == []


def test_redact_is_linear_on_long_token_runs():
    import time
    from loadout import secrets
    start = time.monotonic()
    secrets.redact("x" * 200_000)
    assert time.monotonic() - start < 1.0
    assert secrets.redact("a.API_KEY=" + "k" * 20) == "a.API_KEY=***"


def _timed_redact(text):
    import time
    t0 = time.perf_counter()
    secrets.redact(text)
    return time.perf_counter() - t0


@pytest.mark.parametrize("make", [
    lambda: "-" * 50_000,
    lambda: "a." * 20_000,
    lambda: __import__("base64").urlsafe_b64encode(os.urandom(75_000)).decode(),   # 100 KB of base64url
    lambda: "-" + "key" * 33_000,
], ids=["dashes", "dotted", "b64url", "keykey"])
def test_redact_has_no_redos(make):
    assert _timed_redact(make()) < 1.0


def test_flag_and_url_anchors_keep_matches():
    assert "abcdefgh123" not in secrets.redact("cmd --api-key abcdefgh123")
    assert "abcdefgh123" not in secrets.redact("x -token abcdefgh123")
    assert "hunter2pass" not in secrets.redact("see postgres://u:hunter2pass@h/db")
    assert "hunter2pass" not in secrets.redact("DSN=Postgres+Psycopg://u:hunter2pass@h/db")


JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"


@pytest.mark.parametrize("text,leak", [
    ("-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXk", "BEGIN OPENSSH PRIVATE KEY"),
    ("-----BEGIN PRIVATE KEY-----", "BEGIN PRIVATE KEY"),
    ("pay sk_live_" + "a1" * 12, "sk_live_" + "a1" * 12),
    ("rk_test_" + "Z" * 20, "rk_test_" + "Z" * 20),
    ("glpat-" + "a" * 20, "glpat-" + "a" * 20),
    ("AIza" + "b" * 35, "AIza" + "b" * 35),
    ("npm_" + "a1" * 18, "npm_" + "a1" * 18),
    ("hf_" + "aB1" * 12, "hf_" + "aB1" * 12),
    (JWT, JWT),
    ("password: hunter2hunter2", "hunter2hunter2"),
    ("  api_key: 'Zx9qqqqqqqqqqqqqqq'", "Zx9qqqqqqqqqqqqqqq"),
    ("DB_PASS=hunter2hunter", "hunter2hunter"),
    ("export AUTH_TOKEN=\"abcdefgh1\"", "abcdefgh1"),
    ("[db]\npasswd = s3cretpassword\n", "s3cretpassword"),
    ("- client_secret: abcdefgh12", "abcdefgh12"),
    ("{'api_key': 'abcdefghijkl1234'}", "abcdefghijkl1234"),
])
def test_redact_new_patterns(text, leak):
    out = secrets.redact(text)
    assert leak not in out and "***" in out


@pytest.mark.parametrize("text", [
    "password: ${DB_PASSWORD}", "api_key: <your key here>", "token: $GITHUB_TOKEN", "password: short",
    "author: jonas.weirauch@example.com", "keywords: retrieval,chunking", "{'name': 'loadout-kit-x'}",
    "description: Use when the token budget matters",
    '    "key": "attribution",', "        key = decision_key(v.item)", 'SECRET_KEY = re.compile(r"KEY|TOKEN")',
])
def test_redact_line_rule_leaves_placeholders(text):
    assert secrets.redact(text) == text


@pytest.mark.parametrize("make", [
    lambda: "key" * 33_000 + ": " + "v" * 10,
    lambda: ("a_key" + " " * 5) * 20_000,
    lambda: "'" * 100_000,
    lambda: "password:" * 20_000,
], ids=["longkey", "keys-spaces", "quotes", "colons"])
def test_new_rules_are_linear(make):
    assert _timed_redact(make()) < 1.0
