"""First run in a terminal: one screen with the recommended preferences, Enter takes them all."""
import json

from loadout import bootstrap as b, paths


def _run(answers):
    asked = []

    def ask(q):
        asked.append(q)
        return answers.pop(0) if answers else ""

    b.ensure_personal(ask, interactive=True)
    return asked


def test_enter_takes_the_recommended_preferences_in_one_question(fake_home, fake_runner, capsys):
    asked = _run(["", "Max", "Student", "Python", "", ""])
    pref_questions = [q for q in asked if "[Y/n]" in q or "answer_language" in q]
    assert len(pref_questions) == 1 and "[Y/n]" in pref_questions[0]
    text = capsys.readouterr().out
    assert "answer_language" in text and "conventional" in text  # the summary lists the defaults
    settings = json.loads((paths.personal_root() / "settings.json").read_text(encoding="utf-8"))
    assert settings["effortLevel"] == "medium"
    assert "<!-- loadout:preferences:start -->" in (paths.personal_root() / "rules/me.md").read_text(encoding="utf-8")


def test_n_walks_through_each_preference(fake_home, fake_runner):
    asked = _run(["", "Max", "Student", "Python", "", "n"])
    assert any(q.startswith("answer_language") for q in asked)
    assert any(q.startswith("commit_doc_language") for q in asked)
