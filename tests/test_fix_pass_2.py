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
    for _ in range(3):  # best of three: a busy machine must not fail a linear-time check
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
