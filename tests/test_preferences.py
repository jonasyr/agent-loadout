"""Structured working preferences: preferences.json, the managed me.md block, settings, automode generator."""
import json
import os
import shutil
from pathlib import Path

import pytest

from loadout import configure, paths, preferences, runner
from loadout.__main__ import main

ROOT = paths.kit_root()
IDS = ["answer_language", "commit_style", "ai_attribution", "answer_style", "destructive_actions",
       "effort_level", "extended_thinking", "agent_push_notifications", "automode_trust", "commit_doc_language"]
DEFAULTS = {"answer_language": "match", "commit_style": "conventional", "ai_attribution": "off",
            "answer_style": "concise", "destructive_actions": "ask", "effort_level": "medium",
            "extended_thinking": "yes", "agent_push_notifications": "yes", "automode_trust": "generate",
            "commit_doc_language": "english"}
ATTRIBUTION_OFF = {"commit": "", "pr": "", "sessionUrl": False}
AUTHOR_ME = """# About me (Max)

- CS student; also builds TypeScript web apps.
- Ask before removing or replacing anything I set up; explain trade-offs and give a recommendation backed by research or evidence.
- Before responding to any request, check the available skills and invoke one if there is even a small chance it applies.
- Language: answer in English by default; if I write in another language (e.g. German), answer in that language.
- Commits: ALWAYS use Conventional Commits (`type(scope): subject`, e.g. feat, fix, docs, chore, refactor, test). NEVER add a `Co-Authored-By` trailer (or any AI attribution line) to any commit or PR, in any repo.
"""
AUTHOR_SETTINGS = {
    "alwaysThinkingEnabled": True, "effortLevel": "medium", "tui": "fullscreen", "agentPushNotifEnabled": True,
    "autoMode": {"environment": ["### Org-wide", "**Source control**: my own repos on github.com/max/*"]},
    "permissions": {"allow": ["Bash(hyprctl keyword:*)"]},
    "attribution": ATTRIBUTION_OFF,
}


def _me():
    return paths.personal_root() / "rules" / "me.md"


def _settings():
    p = paths.personal_root() / "settings.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _layer(me=None, settings=None):
    root = paths.personal_root()
    (root / "rules").mkdir(parents=True, exist_ok=True)
    if me is not None:
        _me().write_text(me, encoding="utf-8")
    (root / "settings.json").write_text(json.dumps(settings or {}), encoding="utf-8")


def _block(text):
    lines = text.splitlines()
    return lines[lines.index(preferences.START) + 1:lines.index(preferences.END)]


def _content_lines(text):
    return sorted(l for l in text.splitlines() if l.strip() and l.strip() not in (preferences.START, preferences.END))


# --- preferences.json ---

def test_preferences_json_is_well_formed():
    prefs = preferences.load()
    assert [p["id"] for p in prefs] == IDS
    for p in prefs:
        values = [o["value"] for o in p["options"]]
        assert p["question"] and all(o["label"] for o in p["options"]), p["id"]
        assert p["default"] == DEFAULTS[p["id"]] and p["default"] in values, p["id"]
        target = p["target"]
        if "me_md" in target:
            assert set(target["me_md"]) == set(values), p["id"]
        else:
            assert target["setting"] and (set(target["values"]) == set(values) or p.get("generator")), p["id"]
    attribution = preferences.by_id("ai_attribution")["target"]
    assert attribution == {"setting": "attribution", "values": {"off": ATTRIBUTION_OFF, "on": None}}
    assert preferences.by_id("automode_trust")["target"]["setting"] == "autoMode.environment"
    assert preferences.by_id("automode_trust")["generator"] == "automode"


# --- first run: defaults ---

def test_first_run_non_interactive_writes_defaults_and_skips_automode(fake_home, fake_runner):
    _layer(me="# About me\n")
    preferences.ask_all(lambda q: pytest.fail("non-interactive must not ask"), fill_defaults=True, interactive=False)
    text = _me().read_text()
    assert text.startswith("# About me\n")
    block = _block(text)
    assert len(block) == 5
    for pid in ("answer_language", "commit_style", "answer_style", "destructive_actions", "commit_doc_language"):
        assert preferences.by_id(pid)["target"]["me_md"][DEFAULTS[pid]] in block
    assert _settings() == {"attribution": ATTRIBUTION_OFF, "effortLevel": "medium",
                           "alwaysThinkingEnabled": True, "agentPushNotifEnabled": True}
    assert fake_runner.calls == []


def test_rerun_keeps_everything_and_writes_nothing(fake_home, fake_runner):
    _layer(me="# About me\n")
    preferences.ask_all(lambda q: "", fill_defaults=True, interactive=False)
    me_before, settings_before = _me().read_bytes(), _settings()
    preferences.ask_all(lambda q: "", fill_defaults=False, interactive=True)
    assert _me().read_bytes() == me_before and _settings() == settings_before


def test_keep_mode_leaves_unset_preferences_unset(fake_home, fake_runner):
    _layer(me="# About me\n")
    preferences.ask_all(lambda q: "", fill_defaults=False, interactive=True)
    assert _me().read_text() == "# About me\n"
    assert _settings() == {}


def test_interactive_answers_by_value_and_number(fake_home, fake_runner):
    _layer(me="# About me\n")
    answers = {"answer_language": "german", "commit_doc_language": "2", "effort_level": "high"}

    def ask(q):
        return next((a for k, a in answers.items() if q.startswith(k)), "")

    preferences.ask_all(ask, fill_defaults=False, interactive=True)
    block = _block(_me().read_text())
    assert preferences.by_id("answer_language")["target"]["me_md"]["german"] in block
    assert preferences.by_id("commit_doc_language")["target"]["me_md"]["project"] in block
    assert _settings() == {"effortLevel": "high"}


# --- managed block ---

def test_set_choice_replaces_only_the_block(fake_home, fake_runner):
    _layer(me="# About me\n\n- free text I wrote\n")
    preferences.set_choice("answer_style", "concise")
    preferences.set_choice("answer_style", "detailed")
    text = _me().read_text()
    assert "- free text I wrote" in text
    assert _block(text) == [preferences.by_id("answer_style")["target"]["me_md"]["detailed"]]
    _me().write_text(text + "\n- another note\n")
    preferences.set_choice("commit_style", "free")
    text = _me().read_text()
    assert "- free text I wrote" in text and text.rstrip().endswith("- another note")
    assert len(_block(text)) == 2


def test_free_text_option(fake_home, fake_runner):
    _layer(me="# About me\n")
    preferences.set_choice("answer_language", "other:French")
    assert "- Language: always answer in French." in _block(_me().read_text())
    state = preferences.detect()["answer_language"]
    assert (state.value, state.text) == ("other", "French")
    with pytest.raises(ValueError, match="text"):
        preferences.set_choice("answer_language", "other")


def test_set_choice_validates(fake_home, fake_runner):
    _layer(me="# About me\n")
    with pytest.raises(ValueError, match="answer_language"):
        preferences.set_choice("no_such_pref", "x")
    with pytest.raises(ValueError, match="low.*medium.*high"):
        preferences.set_choice("effort_level", "extreme")
    assert _settings() == {}


def test_migration_moves_equivalent_lines_into_block_with_backup(fake_home, fake_runner):
    _layer(me=AUTHOR_ME)
    states = preferences.detect()
    assert states["answer_language"].value == "match"
    assert states["commit_style"].value == "conventional"
    assert states["destructive_actions"].value == "ask"
    bk = preferences.Backup(description="test")
    preferences.set_choice("answer_style", "detailed", bk=bk)
    text = _me().read_text()
    block = _block(text)
    language = next(l for l in AUTHOR_ME.splitlines() if l.startswith("- Language"))
    assert language in block and text.count(language) == 1
    assert any("Conventional Commits" in l for l in block)
    assert preferences.by_id("answer_style")["target"]["me_md"]["detailed"] in block
    assert "- Before responding to any request" in text.split(preferences.START)[0]
    assert any("restore-file" in s["undo"] for s in bk.steps)


def test_changing_a_migrated_answer_replaces_its_line(fake_home, fake_runner):
    _layer(me=AUTHOR_ME)
    preferences.set_choice("answer_language", "english")
    text = _me().read_text()
    assert "if I write in another language" not in text
    assert preferences.by_id("answer_language")["target"]["me_md"]["english"] in _block(text)


# --- settings targets ---

def test_settings_targets(fake_home, fake_runner):
    _layer(me="# About me\n")
    preferences.set_choice("ai_attribution", "off")
    preferences.set_choice("extended_thinking", "no")
    assert _settings() == {"attribution": ATTRIBUTION_OFF, "alwaysThinkingEnabled": False}
    preferences.set_choice("ai_attribution", "on")
    assert "attribution" not in _settings()
    assert _me().read_text() == "# About me\n"  # settings-only changes never touch me.md


def test_value_equal_to_kit_default_needs_no_override(fake_home, fake_runner, monkeypatch):
    _layer(me="# About me\n")
    monkeypatch.setattr(preferences, "_kit_settings", lambda: {"effortLevel": "high"})
    preferences.set_choice("effort_level", "low")
    assert _settings()["effortLevel"] == "low"
    preferences.set_choice("effort_level", "high")
    assert "effortLevel" not in _settings()
    assert preferences.detect()["effort_level"].value == "high"


# --- adopt prefill from an existing ~/.claude/settings.json ---

def test_prefill_from_existing_settings_changes_nothing(fake_home, fake_runner):
    _layer(me="# About me\n")
    claude = paths.claude_home()
    claude.mkdir()
    (claude / "settings.json").write_text(json.dumps({
        "effortLevel": "high", "includeCoAuthoredBy": False, "alwaysThinkingEnabled": False,
        "autoMode": {"environment": ["mine"]}, "agentPushNotifEnabled": True}))
    # values the kit applied earlier are not the user's own
    paths.state_dir().mkdir(parents=True)
    (paths.state_dir() / "managed-settings.json").write_text(json.dumps({"agentPushNotifEnabled": True}))
    states = preferences.detect()
    assert states["effort_level"].value == "high" and states["effort_level"].source == "existing settings"
    assert states["ai_attribution"].value == "off"
    assert states["extended_thinking"].value == "no"
    assert states["automode_trust"].is_set
    assert not states["agent_push_notifications"].is_set
    preferences.ask_all(lambda q: "", fill_defaults=True, interactive=False)
    assert _settings() == {"agentPushNotifEnabled": True}


# --- automode generator ---

def _repos(fake_home, fake_runner):
    code = fake_home / "Documents" / "Code"
    for name, marker, url in (("a", "package.json", "git@github.com:alice/a.git"),
                              ("b", "Cargo.toml", "https://user:tok@github.com/bob/b")):
        (code / name / ".git").mkdir(parents=True)
        (code / name / marker).write_text("{}")
        fake_runner.responses[("git", "-C", str(code / name), "remote", "get-url", "origin")] = runner.Result(0, url + "\n", "")
    (code / "notes").mkdir()
    return code


def test_automode_draft_shape(fake_home, fake_runner):
    lines = preferences.generate_automode(_repos(fake_home, fake_runner))
    text = "\n".join(lines)
    assert "github.com/alice/*" in text and "github.com/bob/*" in text and "tok" not in text
    assert "regardless of visibility" in text and "`prod`" in text and "IaC" in text
    assert "paste" in text and ".env" in text and "secrets.env" in text and "~/.claude.json" in text
    assert "**Primary use of Claude Code**" in text and "~/Documents/Code" in text
    routine = next(l for l in lines if l.startswith("**Routine**"))
    assert "npm" in routine and "cargo" in routine and "gh" in routine


def test_automode_needs_explicit_confirmation(fake_home, fake_runner, capsys):
    _repos(fake_home, fake_runner)
    _layer(me="# About me\n")
    answers = iter(["", "", ""])  # default folder, default owners, then Enter at the confirmation = no
    preferences.set_choice("automode_trust", "generate", ask=lambda q: next(answers), interactive=True)
    assert "autoMode" not in _settings()
    assert "github.com/alice/*" in capsys.readouterr().out  # the draft was shown in full
    answers = iter(["", "alice", "y"])
    preferences.set_choice("automode_trust", "generate", ask=lambda q: next(answers), interactive=True)
    source = next(l for l in _settings()["autoMode"]["environment"] if l.startswith("**Source control**"))
    assert "github.com/alice/*" in source and "bob" not in source


def test_automode_trusts_only_the_most_frequent_owner_by_default(fake_home, fake_runner):
    code = _repos(fake_home, fake_runner)
    (code / "c" / ".git").mkdir(parents=True)
    fake_runner.responses[("git", "-C", str(code / "c"), "remote", "get-url", "origin")] = runner.Result(0, "git@github.com:alice/c.git\n", "")
    _layer(me="# About me\n")
    answers = iter(["", "", "y"])
    preferences.set_choice("automode_trust", "generate", ask=lambda q: next(answers), interactive=True)
    source = next(l for l in _settings()["autoMode"]["environment"] if l.startswith("**Source control**"))
    assert "github.com/alice/*" in source and "bob" not in source


def test_automode_non_interactive_is_skipped(fake_home, fake_runner):
    _repos(fake_home, fake_runner)
    _layer(me="# About me\n")
    with pytest.raises(ValueError, match="terminal"):
        preferences.set_choice("automode_trust", "generate", interactive=False)
    preferences.set_choice("automode_trust", "skip")
    assert fake_runner.calls == [] and _settings() == {}


def test_first_run_interactive_offers_automode(fake_home, fake_runner):
    _repos(fake_home, fake_runner)
    _layer(me="# About me\n")

    def ask(q):
        return "y" if "Save this" in q else ""

    preferences.ask_all(ask, fill_defaults=True, interactive=True)
    assert _settings()["autoMode"]["environment"]


# --- the author's layer is a no-op ---

def _assert_noop(fake_home, src_me, src_settings):
    states = preferences.detect()
    for pid in ("answer_language", "commit_style", "ai_attribution", "destructive_actions", "effort_level",
                "extended_thinking", "agent_push_notifications", "automode_trust"):
        assert states[pid].is_set, pid
    bk = preferences.Backup(description="test")
    preferences.ask_all(lambda q: "", fill_defaults=False, interactive=True, bk=bk)
    assert _settings() == src_settings
    text = _me().read_text()
    assert _content_lines(text) == _content_lines(src_me)
    assert len(_block(text)) == 3
    assert any("restore-file" in s["undo"] for s in bk.steps)
    before = _me().read_bytes()
    bk2 = preferences.Backup(description="test")
    preferences.ask_all(lambda q: "", fill_defaults=False, interactive=True, bk=bk2)
    assert _me().read_bytes() == before and bk2.empty and _settings() == src_settings


def test_author_like_layer_is_a_noop(fake_home, fake_runner):
    _layer(me=AUTHOR_ME, settings=AUTHOR_SETTINGS)
    _assert_noop(fake_home, AUTHOR_ME, AUTHOR_SETTINGS)


AUTHOR_LAYER = Path(os.environ.get("LOADOUT_AUTHOR_PERSONAL", "/home/jonas/Documents/Code/loadout-personal"))


@pytest.mark.skipif(not (AUTHOR_LAYER / "rules" / "me.md").is_file(), reason="author's personal layer not on this machine")
def test_real_author_layer_copy_is_a_noop(fake_home, fake_runner, tmp_path, monkeypatch):
    copy = tmp_path / "personal-copy"
    shutil.copytree(AUTHOR_LAYER, copy, ignore=shutil.ignore_patterns(".git"))
    monkeypatch.setenv("LOADOUT_PERSONAL", str(copy))
    me = (copy / "rules" / "me.md").read_text(encoding="utf-8")
    settings = json.loads((copy / "settings.json").read_text(encoding="utf-8"))
    _assert_noop(fake_home, me, settings)


# --- CLI and wizard ---

def test_cli_set_pref_choice_and_show(fake_home, fake_runner, capsys):
    _layer(me="# About me\n")
    assert main(["configure", "set", "pref-choice", "effort_level", "high"]) == 0
    assert _settings() == {"effortLevel": "high"}
    assert main(["configure", "set", "pref-choice", "effort_level", "nope"]) == 1
    assert "low" in capsys.readouterr().err
    text = configure.show()
    assert "id: pref-choice effort_level" in text and "high" in text
    assert "id: pref-choice answer_language" in text


def test_wizard_first_run_asks_preferences_after_about_you(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(configure, "apply_all", lambda ask, **k: None)
    paths.personal_root().mkdir(parents=True)
    seen = []

    def ask(q):
        seen.append(q)
        return ""

    configure.wizard(ask, first_run=True, interactive=True)
    about = next(i for i, q in enumerate(seen) if "Your name" in q)
    first_pref = next(i for i, q in enumerate(seen) if q.startswith("answer_language"))
    assert about < first_pref
    assert len(_block(_me().read_text())) == 5
    assert _settings()["effortLevel"] == "medium"
