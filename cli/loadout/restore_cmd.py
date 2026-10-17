"""`loadout restore`: a path, --last, --list, or (in a terminal) a numbered pick of recent backups (spec Part 6)."""
from __future__ import annotations

from pathlib import Path

from . import backup, ui
from .out import printable as _printable
from .secrets import redact


def printable(text: str) -> str:
    """Manifest text for the terminal: secrets masked (a token in a repo folder's name), control characters escaped."""
    return _printable(redact(text))

PAGE = 10
QUESTION = "Restore which? [1-{n}, m = more, Enter = cancel] "
CONFIRM = "Restore this? [y/N] "
NO_TERMINAL = "no terminal: nothing picked. Restore one with `loadout restore <path>` or the newest with `loadout restore --last`"


def _restore(root: Path, force: bool) -> int:
    lines, ok, pre = backup.restore(root, force=force)
    for line in lines:
        print(printable(line))
    if pre is not None:
        print(f"\nthe state this restore replaced is in {pre}  (undo this restore: loadout restore {pre})")
    return 0 if ok else 1


def _row(i: int, b: backup.BackupInfo, now) -> str:
    state = f"  restored {backup._stamp(b.restored_at)}" if b.restored_at else ""
    return printable(f"{i:>3}  {backup.age(b.created, now)} ({backup._stamp(b.created)})  {b.description or '(no description)'}"
            f"  {backup.where(b)}  {backup.summary(b)}{state}")


def _show(b: backup.BackupInfo) -> None:
    print(printable(f"{backup._shown(b.path)} ({b.description or 'no description'}) does this:"))
    for line in backup.contents(b) or ["nothing to undo"]:
        print(printable(f"  {line}"))  # paths and labels come from the manifest


def _info(path: Path):
    """The listed backup at `path` (resolved), else None."""
    try:
        want = path.expanduser().resolve()
    except (OSError, ValueError):
        return None
    return next((b for b in backup.backups() if b.path.resolve() == want), None)


def run(path, list_only: bool, last: bool, repo, force: bool, ask, interactive: bool, now=None, show: bool = False) -> int:
    """show: print what the backup at `path` puts back, change nothing (for agents, before asking the user)."""
    if show:
        b = _info(Path(path)) if path else None
        if b is None:
            print(printable(f"no loadout backup at {path} (see loadout restore --list)" if path
                            else "--show needs a backup path (see loadout restore --list)"))
            return 1
        _show(b)
        return 0
    if path and (list_only or last):  # a read-only-looking --list must never replay the backup it names
        print("a backup path goes with --show or alone, not with --list or --last; nothing restored")
        return 2
    if path:
        return _restore(Path(path).expanduser(), force)
    found = backup.backups(Path(repo).expanduser() if repo else None)
    if not found:
        print(f"no backups for repo {repo}" if repo else "no backups yet")
        return 0
    if list_only:
        for row in backup.list_backups(Path(repo).expanduser() if repo else None):
            print(printable(row))
        print("\nundo one: loadout restore <path from the first column>")
        return 0
    if last:  # the newest of any kind (a later command's or a restore's own backup too): in a terminal, ask
        _show(found[0])
        if interactive and not ui.confirm(ask, CONFIRM):
            print("nothing restored")
            return 0
        return _restore(found[0].path, force)
    if not interactive:
        for row in backup.list_backups(Path(repo).expanduser() if repo else None):
            print(printable(row))
        print(NO_TERMINAL)
        return 0
    shown, wrong = 0, 0
    pick = None
    while pick is None:
        if shown == 0:
            shown = min(PAGE, len(found))
            print("\n".join(_row(i + 1, b, now) for i, b in enumerate(found[:shown])))
        answer = ask(QUESTION.format(n=shown)).strip().lower()
        if answer == "":
            print("nothing restored")
            return 0
        if answer == "m":
            if shown >= len(found):
                print("no more backups")
            else:
                more = found[shown:shown + PAGE]
                print("\n".join(_row(shown + i + 1, b, now) for i, b in enumerate(more)))
                shown += len(more)
            continue
        if answer.isascii() and answer.isdecimal() and 1 <= int(answer) <= shown:
            pick = found[int(answer) - 1]
            break
        wrong += 1
        if wrong >= 3:
            print("nothing restored")
            return 0
        print(f"answer a number from 1 to {shown}, m or Enter")
    _show(pick)
    if pick.restored_at and not force:
        print(f"already restored on {backup._stamp(pick.restored_at)}; replay it with "
              f"`loadout restore --force {backup._shown(pick.path)}`")
        return 1
    if not ui.confirm(ask, CONFIRM):
        print("nothing restored")
        return 0
    return _restore(pick.path, force)
