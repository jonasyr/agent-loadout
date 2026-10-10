"""Fix pass 2 for the adopt/own tools (regressions found by the re-review)."""
import json

import pytest

from loadout import adopt, backup, inventory, own, paths, settings_merge as sm
from fixtures import author_machine


@pytest.fixture
def machine(fake_home, fake_runner):
    author_machine(fake_home)
    return fake_home


def _verdicts():
    return inventory.classify(inventory.collect(with_versions=False))


def _get(kind, name):
    return next(v for v in _verdicts() if v.item.kind == kind and v.item.name == name)


def _settings():
    return json.loads((paths.claude_home() / "settings.json").read_text())


# 1. hook groups: three-way merge keyed by event + matcher + command set

H = {"type": "command", "command": "echo hi"}


def test_changed_field_of_an_applied_group_is_updated_in_place():
    old = {"matcher": "Bash", "hooks": [H]}
    new = {"matcher": "Bash", "hooks": [{**H, "timeout": 10}]}
    other = {"matcher": "Read", "hooks": [{"type": "command", "command": "x"}]}
    current = {"hooks": {"PreToolUse": [old, other]}}
    prev = {"hooks": {"PreToolUse": [old]}}
    desired = {"hooks": {"PreToolUse": [new]}}
    out = sm.merge_settings(current, desired, prev)
    assert out == {"hooks": {"PreToolUse": [new, other]}}
    snap = sm.effective_desired(current, desired, prev)
    assert snap == desired
    assert sm.merge_settings(out, desired, snap) == out


def test_user_copy_never_applied_is_skipped_and_survives_removal():
    mine = {"matcher": "Bash", "hooks": [H]}
    current = {"hooks": {"PreToolUse": [mine]}}
    desired = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{**H, "timeout": 3}]}]}}
    out = sm.merge_settings(current, desired, {})
    assert out == current
    snap = sm.effective_desired(current, desired, {})
    assert "hooks" not in snap
    assert sm.merge_settings(out, {}, snap) == current


def test_applied_group_no_longer_desired_removed_only_if_unchanged():
    g = {"matcher": "Bash", "hooks": [H]}
    assert sm.merge_settings({"hooks": {"Stop": [g]}}, {}, {"hooks": {"Stop": [g]}}) == {}
    edited = {"matcher": "Bash", "hooks": [{**H, "timeout": 9}]}
    assert sm.merge_settings({"hooks": {"Stop": [edited]}}, {}, {"hooks": {"Stop": [g]}}) == {"hooks": {"Stop": [edited]}}


def test_timeout_edit_keeps_hook(machine):
    p = paths.personal_root() / "settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "kit-added"}]}]}}))
    sm.apply_settings()
    p.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "kit-added", "timeout": 5}]}]}}))
    sm.apply_settings()
    s = json.dumps(_settings())
    assert "kit-added" in s, "hook vanished after editing its timeout"
    assert s.count("kit-added") == 1
    assert '"timeout": 5' in s


def test_machine_a_recorded_hook_removed_with_personal_layer(machine):
    v = _get("hook", "PreToolUse:Edit")
    bk = backup.Backup()
    adopt.apply_own([(v, own.Choice("global"))], bk)
    snap = json.loads((paths.state_dir() / "managed-settings.json").read_text())
    assert "my-own-linter" in json.dumps(snap.get("hooks", {}))
    assert json.dumps(_settings()).count("my-own-linter") == 1
    (paths.personal_root() / "settings.json").write_text("{}")
    sm.apply_settings()
    assert "my-own-linter" not in json.dumps(_settings().get("hooks", {})), "recorded hook lingers on machine A"


def test_machine_a_restore_puts_snapshot_back(machine):
    snap_path = paths.state_dir() / "managed-settings.json"
    v = _get("hook", "PreToolUse:Edit")
    bk = backup.Backup()
    adopt.apply_own([(v, own.Choice("global"))], bk)
    backup.restore(bk.root)
    assert not snap_path.exists() or "my-own-linter" not in snap_path.read_text()
    assert "my-own-linter" in json.dumps(_settings()["hooks"])


# 2. line rule: keyword must end the key, value must look like a secret

import time

from loadout import secrets

NOT_SECRET = [
    "auth: required", "token_budget: unlimited", "primary_key: user_id_and_date", "sort-key: created_at_desc",
    "cache.key: request.url.path",
    "auth_url: https://example.com/oauth/authorize", "token_endpoint: https://example.com/token",
    "key_path: ~/.ssh/id_rsa.pub", "  - pass: lint-and-format",
    "api_key: YOUR_API_KEY", "password: process.env.DB_PASSWORD", "secret_key = settings.SECRET_KEY",
    'TOKEN_FILE="$HOME/.config/x"', 'AUTH_HEADER="Authorization: Bearer $TOKEN"', "passwd_file=/etc/passwd",
]
IS_SECRET = [
    "password: hunter2hunter2", "api_key: 9f8e7d6c5b4a3f2e1d0c", "DB_PASS=s3cr3tP4ssw0rd",
    "token: ghp_" + "A1b2" * 9, 'secret: "aB3dE5fG7hJ9kL1m"',
]


@pytest.mark.parametrize("text", NOT_SECRET)
def test_line_rule_leaves_ordinary_config(text):
    assert secrets.redact(text) == text


@pytest.mark.parametrize("text", IS_SECRET)
def test_line_rule_still_flags_secrets(text):
    assert secrets.redact(text) != text


def _t(text):
    best = None
    for _ in range(5):  # best of five: a busy machine must not fail a linear-time check
        t = time.perf_counter()
        secrets.redact(text)
        d = time.perf_counter() - t
        best = d if best is None else min(best, d)
    return best


@pytest.mark.parametrize("make", [
    lambda: "password: x\n" * (100_000 // 12),
    lambda: ("password: " + "aB1" * 30 + "\n") * (100_000 // 101),
    lambda: "a_" * 50_000 + "key: v",
    lambda: "-" * 100_000,
    lambda: "key." * 25_000 + ": x",
    lambda: '"a":' * 25_000,
    lambda: ("password: " + "x" * 20 + "\n") * (100_000 // 31),
], ids=["password-x-lines", "secret-lines", "long-key", "dashes", "dotted-key", "json-many", "key-colon-lines"])
def test_line_rule_linear(make):
    assert _t(make()) < 0.5


SKILL_MD = """---
name: api-helper
description: Calls the example API with auth handled by the environment
---
# Config examples

```yaml
auth: required
token_budget: unlimited
primary_key: user_id_and_date
sort-key: created_at_desc
cache.key: request.url.path
auth_url: https://example.com/oauth/authorize
token_endpoint: https://example.com/token
key_path: ~/.ssh/id_rsa.pub
steps:
  - pass: lint-and-format
api_key: YOUR_API_KEY
```

```js
const password = process.env.DB_PASSWORD
password: process.env.DB_PASSWORD
```

```python
secret_key = settings.SECRET_KEY
```

```sh
TOKEN_FILE="$HOME/.config/x"
AUTH_HEADER="Authorization: Bearer $TOKEN"
passwd_file=/etc/passwd
```
"""


def test_realistic_skill_is_recorded(machine):
    skill = machine / ".claude/skills/my-skill"
    (skill / "SKILL.md").write_text(SKILL_MD)
    rec = own.record_global(_get("skill", "my-skill"), backup.Backup())
    assert rec.ok, rec.lines
    assert (paths.personal_root() / "skills/my-skill/SKILL.md").exists()


# 3. NUL-heavy binary files: scan the UTF-16 and the UTF-8 view

TOKEN = "ghp_" + "A" * 36


def _skill_file(machine, name, data):
    (machine / ".claude/skills/my-skill" / name).write_bytes(data)
    return own.record_global(_get("skill", "my-skill"), backup.Backup())


def test_nul_heavy_binary_with_ascii_token_refused(machine):
    rec = _skill_file(machine, "blob.bin", b"\0" * 3000 + b"token=ghp_" + b"A" * 36)
    assert not rec.ok and "secret" in rec.lines[0]


def test_odd_offset_ascii_token_in_nul_heavy_file_refused(machine):
    rec = _skill_file(machine, "blob.bin", b"\0" * 3001 + b"token=ghp_" + b"A" * 36)
    assert not rec.ok and "secret" in rec.lines[0]


@pytest.mark.parametrize("enc", ["utf-16", "utf-16-le", "utf-16-be"])
def test_utf16_file_with_token_refused(machine, enc):
    rec = _skill_file(machine, "notes.txt", f"export GITHUB_TOKEN={TOKEN}\n".encode(enc))
    assert not rec.ok and "secret" in rec.lines[0]


def test_harmless_binary_still_recorded(machine):
    rec = _skill_file(machine, "icon.bin", bytes(range(256)) * 20 + b"\0" * 4000)
    assert rec.ok, rec.lines


# 4. private filename list

@pytest.mark.parametrize("path", ["scripts/id_generator.py", "docs/credentials.md", ".env.example", ".env.sample",
                                  ".env.template", "id_card.md", "credentials_guide.txt"])
def test_private_list_allows_ordinary_files(path):
    assert not secrets.private_path(path)


@pytest.mark.parametrize("path", ["id_rsa", "id_rsa.pub", "keys/id_dsa", "id_ecdsa_sk", "id_ed25519", "credentials",
                                  "aws/credentials.json", "credentials.csv", ".env", ".env.local", "sub/.env.production",
                                  ".git-credentials", ".vault-token", ".password-store/github.gpg", "x.pem", ".netrc"])
def test_private_list_refuses_private_files(path):
    assert secrets.private_path(path)


def test_skill_with_docs_credentials_md_is_recorded(machine):
    skill = machine / ".claude/skills/my-skill"
    (skill / "docs").mkdir()
    (skill / "docs/credentials.md").write_text("How to set up credentials in your CI.\n")
    (skill / "scripts").mkdir()
    (skill / "scripts/id_generator.py").write_text("print(1)\n")
    (skill / ".env.example").write_text("API_KEY=\n")
    rec = own.record_global(_get("skill", "my-skill"), backup.Backup())
    assert rec.ok, rec.lines


@pytest.mark.parametrize("name", [".git-credentials", ".vault-token"])
def test_skill_with_new_private_names_refused(machine, name):
    (machine / ".claude/skills/my-skill" / name).write_text("x\n")
    rec = own.record_global(_get("skill", "my-skill"), backup.Backup())
    assert not rec.ok and "private file" in rec.lines[0]


from loadout import configure, runner as runner_mod


def _git_personal(fake_runner, status):
    root = paths.personal_root()
    (root / ".git").mkdir(parents=True)
    fake_runner.responses[("git", "-C", str(root), "status")] = runner_mod.Result(0, status, "")


@pytest.mark.parametrize("status", ["?? .git-credentials\n", "?? skills/x/.vault-token\n", "?? .password-store/a.gpg\n"])
def test_offer_commit_refuses_new_private_names(fake_home, fake_runner, capsys, status):
    _git_personal(fake_runner, status)
    configure.offer_commit(lambda q: pytest.fail("asked"))
    assert "not offering to commit" in capsys.readouterr().out


def test_offer_commit_allows_templates_and_docs(fake_home, fake_runner, capsys):
    _git_personal(fake_runner, "?? skills/x/.env.example\n?? skills/x/docs/credentials.md\n?? skills/x/scripts/id_generator.py\n")
    asked = []
    configure.offer_commit(lambda q: asked.append(q) or "n")
    assert asked and "not offering" not in capsys.readouterr().out


# 2b. regression baseline: every corpus secret flagged at main (04cb6b6) or before the first fix pass (43d0c4f)
# is still flagged now. The corpus is all real-looking secrets, so all of it must be flagged now.

import importlib.util
import subprocess
import sys
from pathlib import Path

_B64 = "aB3/dE+fG7hJ9kL1mN0pQ2rS4tU6vW8x=="
SECRET_CORPUS = [
    f"api_key: {_B64}", f"api_key = {_B64}", f'"api_key": "{_B64}"',
    "password: correcthorsebatterystaple", "passphrase = correcthorsebatterystaple",
    "token: abc.def.ghi123456", "secret: 'Xy9kLm2Qp8Rs4Tv6'", 'secret: "aB3dE5fG7hJ9kL1m"',
    "export DB_PASSWORD=Tr0ub4dor3xyz", "export DB_PASSWORD=correcthorsebatterystaple", "DB_PASS=s3cr3tP4ssw0rd",
    '{"apiKey": "Zx9qQ8wW7eE6rR5tT4yY"}', '{"password": "correcthorsebatterystaple"}', "{'api_key': 'abcdefghijkl1234'}",
    "postgres://admin:hunter2hunter2@db.example.com/app", "https://user:S3cr3tPass@example.com",
    "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9abcdef", "Authorization: Basic dXNlcjpwYXNzd29yZA==",
    "Authorization: token ghp_" + "A1b2" * 9, "Authorization: token 0123456789abcdef0123",
    "API_KEY=9f8e7d6c5b4a3f2e1d0c9b8a", "GITHUB_TOKEN=Zx9qQ8wW7eE6rR5tT4yY", "--api-key Zx9qQ8wW7eE6rR5tT4yY",
    "server --token abcdefgh12345", "x -token abcdefgh123", "password: hunter2hunter2", "api_key: 9f8e7d6c5b4a3f2e1d0c",
    "ghp_" + "a1B2" * 9, "gho_" + "a1B2" * 9, "github_pat_" + "A1" * 20, "sk-" + "a1B2" * 8, "apk_" + "a1B2" * 6,
    "xoxb-" + "1234567890-abc", "AKIA" + "ABCDEFGHIJKLMNOP", "-----BEGIN RSA PRIVATE KEY-----",
    "sk_live_" + "a1" * 12, "rk_test_" + "Z" * 20, "glpat-" + "a" * 20, "AIza" + "b" * 35, "npm_" + "a1" * 18,
    "hf_" + "aB1" * 12, "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
]


@pytest.mark.parametrize("text", SECRET_CORPUS)
def test_corpus_secret_flagged_now(text):
    assert secrets.redact(text) != text


def _old_redact(rev, tmp_path):
    root = Path(__file__).resolve().parents[1]
    try:
        src = subprocess.run(["git", "-C", str(root), "show", f"{rev}:cli/loadout/secrets.py"],
                             capture_output=True, text=True, check=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        pytest.skip(f"git history for {rev} not available")
    path = tmp_path / f"secrets_{rev}.py"
    path.write_text(src)
    spec = importlib.util.spec_from_file_location(f"secrets_{rev}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod.redact


@pytest.mark.parametrize("rev", ["04cb6b6", "43d0c4f"])
def test_nothing_flagged_before_is_unflagged_now(rev, tmp_path):
    old = _old_redact(rev, tmp_path)
    lost = [t for t in SECRET_CORPUS if old(t) != t and secrets.redact(t) == t]
    assert lost == []


# 5. interpreter flags that take a value do not shift script detection

import os


@pytest.fixture
def scripts(fake_home, fake_runner):
    (fake_home / "bin").mkdir()
    for name in ("a.js", "h.js", "h.py", "h.sh"):
        (fake_home / "bin" / name).write_text("x\n")
    return fake_home


def _hooks_dir():
    d = paths.personal_root() / "hooks"
    return sorted(p.name for p in d.iterdir()) if d.exists() else []


@pytest.mark.parametrize("cmd,script", [
    ("node --require ~/bin/a.js ~/bin/h.js", "h.js"),
    ("node -r ~/bin/a.js ~/bin/h.js", "h.js"),
    ("python3 -X dev ~/bin/h.py", "h.py"),
    ("python3 -W ignore ~/bin/h.py", "h.py"),
    ("bash -o pipefail ~/bin/h.sh", "h.sh"),
    ("env -u FOO bash ~/bin/h.sh", "h.sh"),
    ("env -u FOO node --require ~/bin/a.js ~/bin/h.js", "h.js"),
])
def test_value_flags_skip_their_value(scripts, cmd, script):
    hook, notes = own._portable_hook({"type": "command", "command": cmd}, backup.Backup(), "x")
    assert _hooks_dir() == [script], (hook, notes)
    assert f"$HOME/.claude/hooks/personal/{script}" in hook["command"]
    if "a.js" in cmd:
        assert any("a.js is a file under your home folder" in n for n in notes), notes


@pytest.mark.parametrize("cmd", ["python3 -c 'print(1)' ~/bin/h.py", "node -e 1 ~/bin/h.js", "bash -c ~/bin/h.sh",
                                 "python3 -m mod ~/bin/h.py", "env -S 'node ~/bin/a.js' ~/bin/h.js"])
def test_inline_code_flags_record_as_is(scripts, cmd):
    hook, notes = own._portable_hook({"type": "command", "command": cmd}, backup.Backup(), "x")
    assert _hooks_dir() == [] and hook["command"] == cmd
    assert own.COMPLEX_NOTE in notes


@pytest.mark.parametrize("cmd,script", [
    ("deno run --allow-read ~/bin/h.js", "h.js"), ("deno --quiet run -A ~/bin/h.js", "h.js"),
    ("bun run ~/bin/h.js", "h.js"), ("python3 -u ~/bin/h.py", "h.py"), ("bash -e ~/bin/h.sh", "h.sh"),
    ("node --require=~/bin/a.js ~/bin/h.js", "h.js"),
])
def test_boolean_flags_and_run_still_find_the_script(scripts, cmd, script):
    hook, notes = own._portable_hook({"type": "command", "command": cmd}, backup.Backup(), "x")
    assert _hooks_dir() == [script], (hook, notes)


# 6. the eval stub prints what the real `loadout configure set own` prints

STUB = Path(__file__).resolve().parents[1] / "plugins/loadout/evals/bin/loadout"


def _stub_machine(home):
    def w(rel, data):
        p = home / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data))
    w(".claude.json", {"mcpServers": {"my-postgres": {"command": "npx", "args": ["-y", "my-postgres-mcp"]}}})
    w(".claude/plugins/installed_plugins.json",
      {"version": 2, "plugins": {"notes-helper@my-marketplace": [{"scope": "user", "version": "1.0.0"}]}})
    w(".claude/plugins/known_marketplaces.json", {"my-marketplace": {"source": {"source": "github", "repo": "me/m"}}})
    w(".claude/settings.json", {"enabledPlugins": {"notes-helper@my-marketplace": True}})


@pytest.mark.parametrize("name", ["notes-helper@my-marketplace", "my-postgres"])
@pytest.mark.parametrize("choice", ["global", "project:mine", "leave", "remove"])
def test_eval_stub_matches_real_set_own(fake_home, fake_runner, capsys, tmp_path, name, choice):
    from loadout import configure as cfg
    _stub_machine(fake_home)
    cfg.set_own(name, choice)
    real = [l for l in capsys.readouterr().out.splitlines() if not l.startswith(("linked ", "backup: "))]
    env = {**os.environ, "HOME": str(fake_home)}
    stub = subprocess.run(["bash", str(STUB), "configure", "set", "own", name, choice], cwd=tmp_path, env=env,
                          capture_output=True, text=True, timeout=30).stdout.splitlines()
    assert stub == real


# 7. --own and configure set own exit 1 when a removal was not done

def _nosrc_market(home):
    p = home / ".claude/plugins/known_marketplaces.json"
    data = json.loads(p.read_text())
    data["nosrc-market"] = {"source": {}}
    p.write_text(json.dumps(data))


def _adopt_own(spec):
    return adopt.run(True, None, set(), False, ask=lambda q: "", with_versions=False, interactive=False, own_spec=spec)


def test_own_exit_1_when_marketplace_removal_skipped(machine, capsys):
    _nosrc_market(machine)
    assert _adopt_own("nosrc-market=remove") == 1
    assert "skipped (no source" in capsys.readouterr().out


def test_own_exit_1_when_mcp_not_removed(machine, monkeypatch, capsys):
    from loadout import runner as r
    monkeypatch.setattr(r, "would_refuse", lambda cmd: True)
    assert _adopt_own("omarchy-kb=remove") == 1
    assert "not removed" in capsys.readouterr().out


def test_own_exit_1_when_project_scope_down_fails(machine, fake_runner, capsys):
    fake_runner.responses[("claude", "mcp", "remove")] = runner_mod.Result(1, "", "boom")
    assert _adopt_own("omarchy-kb=project:mine") == 1


def test_own_exit_0_when_removal_done(machine, fake_runner):
    assert _adopt_own("omarchy-kb=remove") == 0


def test_set_own_exit_1_when_marketplace_removal_skipped(machine, capsys):
    _nosrc_market(machine)
    assert configure.set_own("nosrc-market", "remove") == 1


def test_set_own_exit_1_when_mcp_not_removed(machine, monkeypatch):
    from loadout import runner as r
    monkeypatch.setattr(r, "would_refuse", lambda cmd: True)
    assert configure.set_own("omarchy-kb", "remove") == 1


# 8. a refused hook leaves nothing in <personal>/hooks/

def test_refused_hook_copies_no_script(machine):
    (machine / "bin").mkdir()
    script = machine / "bin/h.sh"
    script.write_text("#!/bin/sh\necho hi\n")
    os.chmod(script, 0o755)
    s = _settings()
    s["hooks"]["PreToolUse"].append({"matcher": "Write", "hooks": [
        {"type": "command", "command": str(script), "headers": {"Authorization": "Bearer abcdefghijklmnop"}}]})
    (paths.claude_home() / "settings.json").write_text(json.dumps(s))
    rec = own.record_global(_get("hook", "PreToolUse:Write"), backup.Backup())
    assert not rec.ok and "secret" in rec.lines[0]
    assert _hooks_dir() == []


def test_accepted_hook_still_copies_script(machine):
    (machine / "bin").mkdir()
    script = machine / "bin/h.sh"
    script.write_text("#!/bin/sh\necho hi\n")
    os.chmod(script, 0o755)
    s = _settings()
    s["hooks"]["PreToolUse"].append({"matcher": "Write", "hooks": [{"type": "command", "command": str(script)}]})
    (paths.claude_home() / "settings.json").write_text(json.dumps(s))
    rec = own.record_global(_get("hook", "PreToolUse:Write"), backup.Backup())
    assert rec.ok, rec.lines
    assert _hooks_dir() == ["h.sh"]


# 9. the refusal names the expanded private path

@pytest.mark.parametrize("cmd", ['"$HOME"/.ssh/id_rsa', "cat \"${HOME}\"/.ssh/id_rsa", "cat ~/.ssh/id_rsa"])
def test_refusal_shows_expanded_path(fake_home, fake_runner, cmd):
    with pytest.raises(own.Collision) as exc:
        own._portable_hook({"type": "command", "command": cmd}, backup.Backup(), "x")
    assert f"({fake_home}/.ssh/id_rsa)" in str(exc.value)
