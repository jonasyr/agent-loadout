"""configure is the one loadout assistant: it answers from the docs and changes things only through the CLI."""
import re

from loadout import paths

KIT = paths.kit_root()
SKILL = (KIT / "plugins/loadout/skills/configure/SKILL.md").read_text(encoding="utf-8")
DESCRIPTION = re.search(r"^description: (.+)$", SKILL, re.M).group(1)


def test_description_covers_questions_and_changes():
    low = DESCRIPTION.lower()
    for word in ("question", "loadout", "codex", "profile", "restore"):
        assert word in low, word
    assert len(DESCRIPTION) <= 400


def test_answers_come_from_the_docs_in_the_clone():
    assert "loadout kit-path" in SKILL and "docs/README.md" in SKILL


def test_changes_go_through_the_cli_only():
    for cmd in ("loadout configure set target", "loadout profile", "loadout check", "loadout adopt",
                "loadout restore --list", "loadout update"):
        assert cmd in SKILL, cmd
    assert "Never edit" in SKILL


def test_the_always_loaded_rules_route_loadout_requests_to_the_skill():
    tooling = (KIT / "rules/tooling.md").read_text(encoding="utf-8")
    assert "loadout:configure" in tooling


def test_eval_stub_knows_the_agents_and_target_switches():
    stub = (KIT / "plugins/loadout/evals/bin/loadout").read_text(encoding="utf-8")
    assert "Agents:" in stub and "target)" in stub


def test_eval_runner_copies_the_whole_docs_folder():
    run_sh = (KIT / "plugins/loadout/evals/run.sh").read_text(encoding="utf-8")
    assert 'cp -r "$kit/docs" "$stub/kit/docs"' in run_sh


def test_routing_cases_exist():
    for case in ("configure-answer", "configure-target"):
        assert (KIT / f"plugins/loadout/evals/{case}/case.yaml").exists(), case


def test_commands_the_agent_runs_after_a_yes_need_no_terminal():
    # the agent's shell has no terminal: a command that asks again would skip silently
    assert "`loadout update --yes`" in SKILL
    assert "`loadout adopt --apply --groups" in SKILL
    assert "`loadout init <names> --agents" in SKILL and "`--dry-run` first" in SKILL and "with `--yes` instead" in SKILL  # plan, then --yes: no terminal to ask
    assert "also moves the plaintext secrets" not in SKILL  # the workaround is gone
    assert ",secrets`" in SKILL and "include `update` or `install`, add `--yes`" in SKILL
    assert "naming `secrets` is its consent" in SKILL  # adopt.py: a named group is the consent, no --yes
