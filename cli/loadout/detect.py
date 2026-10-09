"""Suggest profiles from files in a project."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Iterator

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "build", "dist", "target", "__pycache__", ".gradle"}
WEB_FRAMEWORKS = ("react", "next", "vue", "svelte", "astro")


def _files(project: Path) -> Iterator[Path]:
    for root, dirs, files in os.walk(project):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            yield Path(root) / name


def detect_profiles(project: Path) -> list[str]:
    files = list(_files(project))
    found = []
    if (project / "sonar-project.properties").exists():
        found.append("sonar")
    if any(f.name.startswith("build.gradle") and "com.android" in f.read_text(errors="ignore") for f in files):
        found.append("android")
    pkg = project / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        deps = {}
        for key in ("dependencies", "devDependencies"):
            if isinstance(data.get(key), dict):
                deps.update(data[key])
        if any(name in deps for name in WEB_FRAMEWORKS):
            found.append("web")
    env_example = project / ".env.example"
    if env_example.exists() and re.search(r"^\s*DATABASE_URL\s*=", env_example.read_text(errors="ignore"), re.M):
        found.append("db")
    if any(f.suffix in {".tex", ".bib"} for f in files) or re.search(r"thesis|paper", project.name, re.I):
        found.append("thesis")
    return found
