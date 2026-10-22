"""Installed vs latest versions of catalog binaries. Every network failure means 'unknown'."""
from __future__ import annotations

import json
import re
import urllib.request

from . import runner


class Version(tuple):
    """(major, minor, patch) plus the prerelease text (`pre`, "" for a release).

    A release compares equal to its plain tuple; a prerelease sorts before its release and never equals it.
    Build metadata (`+...`) is ignored.
    """

    def __new__(cls, parts, pre: str = ""):
        self = super().__new__(cls, parts)
        self.pre = pre
        return self

    def _key(self):
        return (tuple(self), 0 if self.pre else 1, self.pre)

    @staticmethod
    def _other_key(other):
        if isinstance(other, Version):
            return other._key()
        return (tuple(other), 1, "")

    def __eq__(self, other):
        if not isinstance(other, tuple):
            return NotImplemented
        return self._key() == self._other_key(other)

    def __ne__(self, other):
        if not isinstance(other, tuple):
            return NotImplemented
        return not self == other

    def __lt__(self, other):
        if not isinstance(other, tuple):
            return NotImplemented
        return self._key() < self._other_key(other)

    def __le__(self, other):
        if not isinstance(other, tuple):
            return NotImplemented
        return self._key() <= self._other_key(other)

    def __gt__(self, other):
        if not isinstance(other, tuple):
            return NotImplemented
        return self._key() > self._other_key(other)

    def __ge__(self, other):
        if not isinstance(other, tuple):
            return NotImplemented
        return self._key() >= self._other_key(other)

    def __hash__(self):
        return hash(tuple(self)) if not self.pre else hash(self._key())


def parse_version(text: str) -> Version | None:
    m = re.search(r"(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.]+))?", text or "")
    if not m:
        return None
    return Version((int(m.group(1)), int(m.group(2)), int(m.group(3))), m.group(4) or "")


def local_version(entry: dict) -> Version | None:
    cmd = entry.get("version", {}).get("cmd")
    if not cmd:
        return None
    res = runner.run(cmd, timeout=20)
    return parse_version(res.stdout + res.stderr) if res.ok else None


def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "loadout"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def latest_version(entry: dict) -> Version | None:
    src = entry.get("version", {})
    try:
        if "github" in src:
            return parse_version(_fetch_json(f"https://api.github.com/repos/{src['github']}/releases/latest").get("tag_name", ""))
        if "npm" in src:
            return parse_version(_fetch_json(f"https://registry.npmjs.org/{src['npm']}/latest").get("version", ""))
        if "pypi" in src:
            return parse_version(_fetch_json(f"https://pypi.org/pypi/{src['pypi']}/json")["info"]["version"])
    except Exception:  # offline, rate-limited, malformed: unknown
        return None
    return None


def fmt(v: tuple | None) -> str:
    if not v:
        return "?"
    text = ".".join(map(str, v))
    pre = getattr(v, "pre", "")
    return f"{text}-{pre}" if pre else text
