"""--answers FILE: the starter layer's answers for bootstrap without a terminal (docs/how-to/install-with-an-agent.md)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

ABOUT_KEYS = ("name", "role", "languages", "preferences")
TOP_KEYS = ("about", "preferences")


def _no_secret(where: str, value: str) -> None:
    """The answers end up in the personal layer (often a git repo): a token or key there is refused, never echoed."""
    from . import paths, secrets
    if secrets.redact(value) != value or secrets.high_entropy(value):
        raise ValueError(f"--answers: {where} looks like a secret (a token, key or password); "
                         f"remove it: secrets go in {paths.secrets_file()}, never in the personal layer")


@dataclass
class Answers:
    about: dict = field(default_factory=dict)
    prefs: dict = field(default_factory=dict)


def load(path) -> Answers:
    """The answers in path; ValueError names the first problem. Nothing is changed here."""
    from . import preferences
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"--answers: cannot read {path} ({exc.strerror or exc})") from None
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"--answers: {path.name} is not valid JSON ({exc})") from None
    if not isinstance(data, dict):
        raise ValueError(f"--answers: {path.name} must be a JSON object")
    unknown = [k for k in data if k not in TOP_KEYS]
    if unknown:
        raise ValueError(f"--answers: unknown key {unknown[0]!r} (allowed: {', '.join(TOP_KEYS)})")
    about = data.get("about", {})
    if not isinstance(about, dict):
        raise ValueError("--answers: about must be an object")
    for key, value in about.items():
        if key not in ABOUT_KEYS:
            raise ValueError(f"--answers: unknown key about.{key!r} (allowed: {', '.join(ABOUT_KEYS)})")
        if not isinstance(value, str):
            raise ValueError(f"--answers: about.{key} must be text")
        _no_secret(f"about.{key}", value)
    given = data.get("preferences", {})
    if not isinstance(given, dict):
        raise ValueError("--answers: preferences must be an object")
    known = {p["id"]: p for p in preferences.load()}
    prefs = {}
    for pid, raw in given.items():
        pref = known.get(pid)
        if pref is None:
            raise ValueError(f"--answers: unknown preference {pid!r} (ids: loadout configure show)")
        if pref.get("generator"):
            raise ValueError(f"--answers: {pid} needs a terminal; run `loadout configure prefs` after setup")
        if not isinstance(raw, str):
            raise ValueError(f"--answers: preferences.{pid} must be text, e.g. \"{pref['default']}\"")
        _no_secret(f"preferences.{pid}", raw)
        try:
            prefs[pid] = preferences.parse_choice(pref, raw)
        except ValueError as exc:
            raise ValueError(f"--answers: {exc}") from None
    return Answers({k: v.strip() for k, v in about.items()}, prefs)
