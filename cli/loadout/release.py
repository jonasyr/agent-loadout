"""`loadout release` (maintainer): cut a release from main, or withdraw one. Every check runs before anything is
written, committed, tagged or pushed; the release commit may touch only the three release files."""
from __future__ import annotations

import datetime
import json
import os
import re
import shlex
import tempfile
from pathlib import Path
from typing import Callable

from . import channels, paths, runner
from .jsonio import load_json, save_json
from .out import printable

RELEASE_FILES = ("pyproject.toml", "CHANGELOG.md", "release-status.json")
ASSETS = ("bootstrap.sh", "bootstrap.ps1")
_VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", re.ASCII)
_ANY_TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", re.ASCII)  # below the floor too
_PR = re.compile(r"(.*\S)\s+\(#([0-9]+)\)")
_MERGE_PR = re.compile(r"Merge pull request #([0-9]+) from \S+")
_CONVENTIONAL = re.compile(r"([a-z]+)(?:\(([^)]*)\))?(!)?:\s*(.*)", re.DOTALL)
_SUMMARY = "<!-- one to three sentences for users: what this release brings -->"
_SECTIONS = ("Breaking", "Added", "Changed", "Fixed", "Security")
_LEFT_OUT = ("docs", "chore", "test", "ci", "build", "style")
_CAP = 15


def _say(text: str) -> int:
    print(f"loadout release: {text}")
    return 1


def _git(root: Path, *args: str, timeout: float = 60) -> runner.Result:
    return runner.run(["git", "-C", str(root), *args], timeout=timeout, env=channels._git_env())


def _out(res: runner.Result) -> str:
    return res.stdout.strip() if res.ok else ""


def _parse(version: str) -> tuple[int, int, int] | None:
    m = _VERSION.fullmatch(version) if isinstance(version, str) else None
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def _checkout(root: Path) -> str | None:
    """A refusal text, or None when this is the kit's own clean main, level with origin/main."""
    try:
        inside = Path.cwd().resolve().is_relative_to(root.resolve())
    except OSError:
        inside = False
    if not (root / ".git").exists() or not (root / "pyproject.toml").is_file() or not inside:
        return f"run it from the kit checkout (a git clone of agent-loadout), not from {printable(str(Path.cwd()))}"
    if _out(_git(root, "rev-parse", "--abbrev-ref", "HEAD")) != "main":
        return "the branch is not main; nothing changed"
    status = _git(root, "status", "--porcelain")
    if not status.ok or status.stdout.strip():
        return "the working tree is not clean; commit or remove the changes first"
    if not _git(root, "fetch", "origin", "main", timeout=120).ok:
        return "could not fetch origin/main; nothing changed"
    head = _out(_git(root, "rev-parse", "HEAD"))
    if not head or head != _out(_git(root, "rev-parse", "origin/main")):
        return "HEAD differs from origin/main; pull or push first"
    return None


def _tags(root: Path) -> set[str] | None:
    """Release tags known here or on origin; None when origin cannot be read."""
    local = _git(root, "tag", "--list")
    remote = channels.remote_tags(root)
    if not local.ok or remote is None:
        return None
    return {t for t in {*local.stdout.split(), *remote} if channels.parse_tag(t)}


def _newest(tags: set[str]) -> str | None:
    return max(tags, key=lambda t: channels.parse_tag(t), default=None)


def _staged_ok(root: Path, allowed: tuple[str, ...]) -> str | None:
    res = _git(root, "diff", "--cached", "--name-only")
    if not res.ok:
        return "could not read the staged diff"
    extra = [n for n in res.stdout.splitlines() if n.strip() and n.strip() not in allowed]
    return f"the staged diff touches {printable(', '.join(extra))}, not only {', '.join(allowed)}" if extra else None


def _undo_files(root: Path, files: tuple[str, ...]) -> None:
    _git(root, "restore", "--source=HEAD", "--staged", "--worktree", "--", *files)


def _ci_green(root: Path, sha: str) -> bool:
    res = runner.run(["gh", "run", "list", "--commit", sha, "--workflow", "ci.yml", "--limit", "1",
                      "--json", "conclusion,status"], cwd=str(root), timeout=60)
    if not res.ok:
        return False
    try:
        runs = json.loads(res.stdout)
    except ValueError:
        return False
    return (isinstance(runs, list) and len(runs) == 1 and isinstance(runs[0], dict)
            and runs[0].get("status") == "completed" and runs[0].get("conclusion") == "success")


def _gh_ready() -> str | None:
    if not runner.have("gh"):
        return "gh (the GitHub CLI) is not installed"
    if not runner.run(["gh", "auth", "status"], timeout=30).ok:
        return "gh auth status failed; run gh auth login"
    return None


def base_tag(root: Path) -> str | None:
    """The newest vX.Y.Z tag of any version (also one below the release floor), local or on origin."""
    local = _git(root, "tag", "--list")
    remote = channels.remote_tags(root)
    names = {*(local.stdout.split() if local.ok else ()), *(remote or ())}
    found = [(tuple(int(g) for g in m.groups()), n) for n in names if (m := _ANY_TAG.fullmatch(n))]
    return max(found)[1] if found else None


def pr_subjects(root: Path, prev: str | None) -> list[tuple[str, int | None]]:
    """(subject, PR number or None) of what landed on main since prev, first-parent: squash merges (`... (#N)`),
    merge commits (`Merge pull request #N from ...`, the title is the first body line) and plain conventional commits."""
    span = f"{prev}..HEAD" if prev else "HEAD"
    res = _git(root, "log", "--first-parent", "--format=%s%x00%b%x1e", span)
    if not res.ok:
        raise RuntimeError(f"git log {span} failed: {printable(res.stderr.strip())}")
    found: list[tuple[str, int | None]] = []
    for record in res.stdout.split("\x1e"):
        subject, _, body = record.strip("\n").partition("\0")
        subject = subject.strip()
        if m := _PR.fullmatch(subject):
            found.append((m[1], int(m[2])))
        elif m := _MERGE_PR.fullmatch(subject):
            title = next((line.strip() for line in body.splitlines() if line.strip()), "")
            if title:
                found.append((title, int(m[1])))
        elif _CONVENTIONAL.fullmatch(subject):
            found.append((subject, None))
    return found


def _classify(subject: str) -> tuple[str | None, str]:
    """(section or None when left out, description) of one PR subject."""
    m = _CONVENTIONAL.fullmatch(subject)
    if not m:
        return "Changed", subject
    kind, scope, bang, desc = m[1], m[2] or "", m[3], m[4].strip() or subject
    if bang or "BREAKING CHANGE" in subject:
        return "Breaking", desc
    if kind == "feat":
        return "Added", desc
    if kind == "fix":
        secure = scope == "security" or re.search(r"secret|security", subject, re.IGNORECASE)
        return ("Security" if secure else "Fixed"), desc
    if kind in ("refactor", "perf"):
        return "Changed", desc
    return (None if kind in _LEFT_OUT else "Changed"), desc


def _compare_link(version: str, slug: str, prev: str | None) -> str:
    base = f"https://github.com/{slug}"
    return f"{base}/compare/{prev}...v{version}" if prev else f"{base}/releases/tag/v{version}"


def notes_section(version: str, today: str, prs: list[tuple[str, int | None]], slug: str, prev: str | None) -> str:
    """The Keep a Changelog section for the merged PRs."""
    groups: dict[str, list[str]] = {name: [] for name in _SECTIONS}
    for subject, number in prs:
        name, desc = _classify(subject)
        if name:
            groups[name].append(f"- {printable(desc)}" + (f" (#{number})" if number else ""))
    parts = [f"## [{version}] - {today}", _SUMMARY]
    shown = [(name, bullets) for name, bullets in groups.items() if bullets]
    if not shown:
        parts.append("- No user-facing changes.")
    for name, bullets in shown:
        if len(bullets) > _CAP:
            bullets = [*bullets[:_CAP], f"- \u2026and {len(bullets) - _CAP} more (see the compare link)"]
        parts.append(f"### {name}\n\n" + "\n".join(bullets))
    parts.append(f"[{version}]: {_compare_link(version, slug, prev)}")
    return "\n\n".join(parts) + "\n"


def _link_line(version: str) -> re.Pattern:
    return re.compile(rf"\[{re.escape(version)}\]: (\S+)\s*")


def _release_body(section: str, version: str, fallback_link: str) -> str:
    """The GitHub Release body: the section without its heading and compare-link line, plus the changelog link."""
    link, lines = fallback_link, []
    pattern = _link_line(version)
    for line in section.strip().splitlines()[1:]:
        m = pattern.fullmatch(line)
        if m:
            link = m[1]
        else:
            lines.append(line)
    return "\n".join(lines).strip() + f"\n\n**Full changelog:** {link}\n"


def _notes_problem(text: str, version: str) -> str | None:
    lines = text.strip().splitlines()
    if not lines or not lines[0].startswith(f"## [{version}] - "):
        return f"the notes file must start with '## [{version}] - '"
    if not any(line.strip() for line in lines[1:]):
        return "the notes file has nothing under its heading"
    return None


def _edit(section: str, tmp: Path) -> str | None:
    """The section after $EDITOR; None when the editor failed."""
    path = tmp / "section.md"
    path.write_text(section, encoding="utf-8")
    cmd = shlex.split(os.environ["EDITOR"]) + [str(path)]
    if runner.run_interactive(cmd, timeout=3600) != 0:
        return None
    return path.read_text(encoding="utf-8")


def _set_version(root: Path, version: str) -> None:
    path = root / "pyproject.toml"
    text = path.read_text(encoding="utf-8")
    path.write_text(re.sub(r'(?m)^version = "[^"]*"', f'version = "{version}"', text, count=1), encoding="utf-8")


def _prepend_changelog(root: Path, section: str) -> None:
    path = root / "CHANGELOG.md"
    text = path.read_text(encoding="utf-8") if path.exists() else "# Changelog\n"
    head, _, rest = text.partition("\n")
    if not head.startswith("# "):
        head, rest = "# Changelog", text
    tail = f"\n{rest.strip()}\n" if rest.strip() else ""
    path.write_text(f"{head}\n\n{section.strip()}\n{tail}", encoding="utf-8")


def _status_path(root: Path) -> Path:
    return root / "release-status.json"


def _step(root: Path, what: str, res: runner.Result, where: str) -> int | None:
    if res.ok:
        return None
    return _say(f"{what} failed: {printable((res.stderr or res.stdout).strip())}; {where}")


def cut(version: str, urgent: bool, yes: bool, edit: bool, ask: Callable[[str], str],
        draft_notes: Path | None = None, notes: Path | None = None) -> int:
    if notes is not None and (edit or draft_notes is not None):
        return _say("--notes cannot be combined with --edit or --draft-notes; nothing changed")
    root = paths.kit_root()
    refusal = _checkout(root)
    if refusal:
        return _say(refusal)
    if (new := _parse(version)) is None:
        return _say(f"{printable(str(version))} is not a version like X.Y.Z")
    tags = _tags(root)
    if tags is None:
        return _say("could not read the release tags from origin; nothing changed")
    newest = _newest(tags)
    if newest and new <= channels.parse_tag(newest):
        return _say(f"{version} is not newer than the newest tag {newest}")
    if new < channels.FLOOR:
        return _say(f"{version} is below the floor {'.'.join(map(str, channels.FLOOR))}")
    refusal = _gh_ready()
    if refusal:
        return _say(refusal)
    sha = _out(_git(root, "rev-parse", "HEAD"))
    if not _ci_green(root, sha):
        return _say(f"the newest ci.yml run for {sha[:7]} is not completed and successful")
    if edit and not os.environ.get("EDITOR", "").strip():
        return _say("--edit needs $EDITOR")
    tag = f"v{version}"
    prev = base_tag(root)
    slug = channels.kit_slug(root)
    link = _compare_link(version, slug, prev)
    if notes is not None:
        try:
            section = notes.read_text(encoding="utf-8").strip()
        except (OSError, ValueError):
            return _say(f"could not read the notes file {printable(str(notes))}; nothing changed")
        problem = _notes_problem(section, version)
        if problem:
            return _say(f"{problem}; nothing changed")
        rest = section.partition("\n")[2]
        section = f"## [{version}] - {datetime.date.today().isoformat()}\n{rest}"  # dated the day it is released
    else:
        try:
            prs = pr_subjects(root, prev)
        except RuntimeError as exc:
            return _say(str(exc))
        section = notes_section(version, datetime.date.today().isoformat(), prs, slug, prev).strip()
    if draft_notes is not None:
        try:
            inside = draft_notes.resolve().is_relative_to(root.resolve())
        except OSError:
            inside = False
        if inside:
            return _say("write the draft outside the checkout (e.g. /tmp/notes.md): a file in the checkout makes the release refuse")
        try:
            draft_notes.write_text(section + "\n", encoding="utf-8")
        except OSError as exc:
            return _say(f"could not write {printable(str(draft_notes))}: {printable(str(exc))}")
        print(f"draft notes for {tag} written to {printable(str(draft_notes))}; nothing else changed")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        if edit:
            try:
                edited = _edit(section, Path(tmp))
            except ValueError:
                return _say("$EDITOR cannot be split into a command")
            if edited is None or not edited.strip().startswith("## "):
                return _say("the editor failed or the section no longer starts with '## '; nothing changed")
            section = edited.strip()
        print(f"Release {tag} from main {sha[:7]} (CI green):")
        print(f"  pyproject.toml version -> {version}; CHANGELOG.md gets:")
        for line in section.splitlines():
            print(f"    {printable(line)}")
        if urgent:
            print("  release-status.json marks it urgent")
        print(f"  then: commit, tag {tag}, git push --atomic origin main {tag}, gh release create (with {' and '.join(ASSETS)})")
        if not yes and ask("Release now? [y/N] ").strip().lower() not in ("y", "yes"):
            return _say("cancelled; nothing changed")
        body = Path(tmp) / "notes.md"
        body.write_text(_release_body(section, version, link), encoding="utf-8")
        _set_version(root, version)
        _prepend_changelog(root, section)
        if urgent:
            status = load_json(_status_path(root))
            listed = status.get("urgent") if isinstance(status.get("urgent"), list) else []
            if version not in listed:
                listed.append(version)
            status["urgent"] = listed
            save_json(_status_path(root), status)
        _git(root, "add", "--", *RELEASE_FILES)
        problem = _staged_ok(root, RELEASE_FILES)
        if problem:
            _undo_files(root, RELEASE_FILES)
            return _say(f"{problem}; nothing committed")
        failed = _step(root, "git commit", _git(root, "commit", "-m", f"chore(release): {tag}"),
                       "the release files are changed and staged; nothing tagged or pushed")
        if failed:
            return failed
        where = f"the commit exists locally; finish by hand ({tag} not pushed)"
        failed = _step(root, "git tag", _git(root, "tag", "-a", tag, "-m", f"loadout {version}"), where)
        if failed:
            return failed
        failed = _step(root, "git push", _git(root, "push", "--atomic", "origin", "main", tag, timeout=120),
                       f"commit and tag {tag} exist locally only")
        if failed:
            return failed
        res = runner.run(["gh", "release", "create", tag, "--title", f"loadout {version}", "--notes-file",
                          str(body), *ASSETS], cwd=str(root), timeout=120)
        failed = _step(root, "gh release create", res,
                       f"{tag} is pushed; create the release by hand (gh release create {tag} {' '.join(ASSETS)})")
        if failed:
            return failed
    print(f"Released {tag}.")
    return 0


def withdraw(version: str, reason: str, use: str | None, yes: bool, ask: Callable[[str], str]) -> int:
    root = paths.kit_root()
    refusal = _checkout(root)
    if refusal:
        return _say(refusal)
    old = _parse(version)
    if old is None:
        return _say(f"{printable(str(version))} is not a version like X.Y.Z")
    tags = _tags(root)
    if tags is None:
        return _say("could not read the release tags from origin; nothing changed")
    if f"v{version}" not in tags:
        return _say(f"there is no tag v{version}; nothing changed")
    if not isinstance(reason, str) or not reason.strip():
        return _say("--reason is needed")
    if use is not None:
        target = _parse(use)
        if target is None or f"v{use}" not in tags or target <= old:
            return _say(f"--use must name an existing release newer than {version}; nothing changed")
    status = load_json(_status_path(root))
    withdrawn = status.get("withdrawn") if isinstance(status.get("withdrawn"), list) else []
    if any(isinstance(e, dict) and e.get("version") == version for e in withdrawn):
        return _say(f"{version} is already withdrawn")
    print(f"Withdraw v{version} ({printable(reason.strip())}); use: {use or 'none (loadout restore)'}")
    print("  then: commit release-status.json and git push origin main")
    if not yes and ask("Withdraw now? [y/N] ").strip().lower() not in ("y", "yes"):
        return _say("cancelled; nothing changed")
    withdrawn.append({"version": version, "reason": reason.strip(), "use": use})
    status["withdrawn"] = withdrawn
    save_json(_status_path(root), status)
    only = ("release-status.json",)
    _git(root, "add", "--", *only)
    problem = _staged_ok(root, only)
    if problem:
        _undo_files(root, only)
        return _say(f"{problem}; nothing committed")
    failed = _step(root, "git commit", _git(root, "commit", "-m", f"chore(release): withdraw v{version}"),
                   "release-status.json is changed and staged")
    if failed:
        return failed
    failed = _step(root, "git push", _git(root, "push", "origin", "main", timeout=120),
                   "the commit exists locally only")
    if failed:
        return failed
    print(f"Withdrawn v{version}.")
    return 0
