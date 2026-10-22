"""What counts as a symbol search in a grep, rg, git grep or find command (stdlib only).

`loadout usage` uses it to count symbol-like searches, the measure of whether agents reach for grep where Serena or
the code graph would answer. See docs/reference/cli.md#loadout-usage."""
from __future__ import annotations

import os
import re

IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,63}")
DECL = re.compile(r"\b(?:def|class|function|fn|func|interface|struct|type|enum|trait)\s+([A-Za-z_][A-Za-z0-9_]{1,63})")
CALL = re.compile(r"^([A-Za-z_][A-Za-z0-9_]{2,63})\\?\($")
COMMON = frozenset("""error errors todo fixme warning warn debug info test tests true false none null import from
return print main self this name path file data value values config http https version license readme string
true false def class function type""".split())
NON_CODE = (".log", ".md", ".markdown", ".rst", ".txt", ".json", ".jsonl", ".toml", ".yaml", ".yml", ".csv",
            ".lock", ".ini", ".cfg", ".env", ".html", ".xml")
CODE_EXT = (".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go", ".kt", ".java", ".cs", ".rb", ".php", ".c", ".cc",
            ".cpp", ".h", ".hpp", ".swift", ".scala", ".ex", ".lua", ".sh")
SEARCH_CMDS = ("rg", "grep", "egrep")
TAKES_VALUE = frozenset({"-g", "-t", "-T", "-m", "-A", "-B", "-C", "-f", "--glob", "--type", "--type-not",
                         "--max-count", "--include", "--exclude", "--exclude-dir", "-d", "--max-depth"})
OPERATORS = frozenset({"|", "||", "&&", ";", ">", ">>", "<", "2>", "&"})
SHELLS = frozenset({"bash", "sh", "zsh", "dash", "fish"})
PREFIXES = frozenset({"rtk", "xargs", "sudo", "time", "nice", "env", "command", "exec", "nohup"})
FIND = ["<find of code files>"]  # shell_search's paths for a `find -name '*.py'`: a search without a symbol
FILTERS = frozenset({"-t", "--type", "-g", "--glob", "--include", "--iglob"})
DOC_TYPES = frozenset({"md", "markdown", "rst", "txt", "json", "jsonl", "yaml", "yml", "toml", "csv", "log", "html",
                       "xml", "ini", "cfg"})
_ALT = re.compile(r"\\\||\|")


def _one_symbol(p: str) -> str | None:
    p = re.sub(r"^\^|\$$|\\b", "", p.strip().strip("()"))
    m = DECL.search(p)
    if m:
        name = m.group(1)
    else:
        m = CALL.match(p)
        name = m.group(1) if m else (p if IDENT.fullmatch(p) else None)
    if not name or name.lower() in COMMON:
        return None
    return name


def symbol(pattern: object) -> str | None:
    """The symbol a search pattern looks for, or None (a common word, a phrase, a regex soup). For an alternation
    (`a\\|b`, `-E 'a|b'`, `(a|b)`) the first alternative that is a symbol."""
    if not isinstance(pattern, str) or len(pattern) > 200:
        return None
    p = pattern.strip().strip("'\"")
    for part in _ALT.split(p) if _ALT.search(p) else [p]:
        name = _one_symbol(part)
        if name:
            return name
    return None


def _words(command: object) -> list[str]:
    """The words of a shell command: a string (Claude Code) or an argv list (Codex); `bash -lc "<script>"`
    is unwrapped one level, so Codex's usual shell wrapper is seen."""
    if isinstance(command, list):
        words = [w for w in command if isinstance(w, str)][:200]
        if len(words) >= 3 and os.path.basename(words[0]) in SHELLS and words[1] in ("-c", "-lc", "-ic"):
            return _words(words[2])
        return words
    if not isinstance(command, str) or len(command) > 4000:
        return []
    try:
        import shlex  # imported here: most calls never get this far
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)  # `src;rg` -> `src`, `;`, `rg`
        lexer.whitespace_split = True
        return list(lexer)[:200]
    except ValueError:
        return command.split()[:200]


def shell_search(command: object) -> tuple[bool, str | None, list[str]]:
    """(is a search, symbol or None, path arguments) for the rg/grep/git grep/find commands of a shell line (after
    `;`, `&&`, `rtk`, `xargs` and the like): the first search with a symbol, else the first search. A grep that
    filters another command's output (`ls | grep X`), a word in a message (`echo grep X`) and a find that changes
    files are no search."""
    words = _words(command)
    first = None
    for i, w in enumerate(words):
        prev = words[i - 1] if i else ""
        if i and prev not in OPERATORS and prev not in PREFIXES:
            continue  # an argument, not a command
        base = os.path.basename(w)
        found = None
        if base == "find":
            found = _find_args(words[i + 1:])
        elif base == "git" and i + 1 < len(words) and words[i + 1] == "grep":
            found = _search_args(words[i + 2:])
        elif base in SEARCH_CMDS and prev != "|":
            found = _search_args(words[i + 1:])
        if not found or not found[0]:
            continue
        if found[1] is not None and not non_code(found[2]):
            return found
        first = first or found
    return first or (False, None, [])


def _find_args(rest: list[str]) -> tuple[bool, str | None, list[str]]:
    if any(x in ("-delete", "-exec", "-execdir", "-ok", "-okdir") for x in rest):
        return False, None, []
    for j, x in enumerate(rest[:-1]):
        if x in OPERATORS:
            break
        if x in ("-name", "-iname") and rest[j + 1].endswith(CODE_EXT):
            return True, None, FIND
    return False, None, []


def _search_args(args: list[str]) -> tuple[bool, str | None, list[str]]:
    pattern, paths, skip = None, [], False
    for j, a in enumerate(args):
        if a in OPERATORS:
            break
        if skip:
            skip = False
            continue
        if a in ("-e", "--regexp") and j + 1 < len(args):
            pattern, skip = args[j + 1], True
            continue
        if a in FILTERS and j + 1 < len(args) and doc_filter(args[j + 1]):
            return False, None, []  # limited to docs, configs or data: a text search
        if "=" in a and a.split("=", 1)[0] in FILTERS and doc_filter(a.split("=", 1)[1]):
            return False, None, []
        if a in TAKES_VALUE:
            skip = True
            continue
        if a.startswith("-"):
            continue
        if pattern is None:
            pattern = a
        else:
            paths.append(a)
    if pattern is None:
        return False, None, []
    return True, symbol(pattern), paths


def non_code(paths: list[str]) -> bool:
    return bool(paths) and paths is not FIND and all(p.lower().endswith(NON_CODE) for p in paths)


def doc_filter(value: object) -> bool:
    """A file type or glob that limits a search to docs, configs or data (`-t md`, `-g '*.json'`)."""
    if not isinstance(value, str) or not value:
        return False
    v = value.strip("'\"").lower()
    return v in DOC_TYPES or v.endswith(NON_CODE)


def is_symbol_search(command: object) -> bool:
    """A shell line that searches code for a symbol (what `loadout usage` counts)."""
    hit, name, paths = shell_search(command)
    return hit and name is not None and not non_code(paths)
