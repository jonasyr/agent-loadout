"""Installed vs latest versions of catalog binaries. Every network failure means 'unknown'."""
from __future__ import annotations

import json
import re
import urllib.request

from . import runner


def parse_version(text: str) -> tuple | None:
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(x) for x in m.groups()) if m else None


def local_version(entry: dict) -> tuple | None:
    res = runner.run(entry["version"]["cmd"], timeout=20)
    return parse_version(res.stdout + res.stderr) if res.ok else None


def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "loadout"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def latest_version(entry: dict) -> tuple | None:
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
    return ".".join(map(str, v)) if v else "?"
