#!/usr/bin/env python3
"""Tool hints (stdlib only, no network; always exit 0, silent on error; never blocks).

PreToolUse Grep|Glob|Bash (Claude Code) or Bash (Codex): on the SEARCHES-th symbol search since Serena or the code
graph was last used, add one short fact naming those tools. PostToolUse on a Serena or codebase-memory tool resets
the count. At most one hint per SPACING matched calls; never silenced for the rest of a session.
PreToolUse WebSearch|WebFetch on library docs: one fact naming Context7 and Microsoft Learn, at most once per
SPACING calls.
State: <state_dir>/tool-hint/<session_id>.json. See docs/reference/hooks.md."""
from __future__ import annotations

import json
import os
import re
import shlex
import sys
import tempfile
import time
from pathlib import Path

SEARCHES = 3
SPACING = 10
MAX_CHARS = 300
KEEP_DAYS = 7
MAX_INPUT = 200_000

IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,63}")
DECL = re.compile(r"\b(?:def|class|function|fn|func|interface|struct|type|enum|trait)\s+([A-Za-z_][A-Za-z0-9_]{1,63})")
CALL = re.compile(r"^([A-Za-z_][A-Za-z0-9_]{2,63})\\?\($")
COMMON = frozenset("""error errors todo fixme warning warn debug info test tests true false none null import from
return print main self this name path file data value values config http https version license readme string
true false def class function type""".split())
NON_CODE = (".log", ".md", ".markdown", ".rst", ".txt", ".json", ".jsonl", ".toml", ".yaml", ".yml", ".csv",
            ".lock", ".ini", ".cfg", ".env", ".html", ".xml")
CODE_MARKERS = ("pyproject.toml", "setup.py", "package.json", "Cargo.toml", "go.mod", "pom.xml", "build.gradle",
                "build.gradle.kts", "Gemfile", "composer.json", "mix.exs", "CMakeLists.txt", "Makefile")
CODE_EXT = (".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go", ".kt", ".java", ".cs", ".rb", ".php", ".c", ".cc",
            ".cpp", ".h", ".hpp", ".swift", ".scala", ".ex", ".lua", ".sh")
SEARCH_CMDS = ("rg", "grep", "egrep")
TAKES_VALUE = frozenset({"-g", "-t", "-T", "-m", "-A", "-B", "-C", "-f", "--glob", "--type", "--type-not",
                         "--max-count", "--include", "--exclude", "--exclude-dir", "-d", "--max-depth"})
OPERATORS = frozenset({"|", "||", "&&", ";", ">", ">>", "<", "2>", "&"})
MCP = re.compile(r"^mcp__(?:plugin_loadout_)?(?:serena|codebase-memory-mcp|codebase_memory_mcp)__")
SHELL_TOOLS = frozenset({"Bash", "shell", "local_shell", "exec_command", "shell_command"})
SESSION = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
FIND = ["<find of code files>"]  # shell_search's paths for a `find -name '*.py'`: a search without a symbol

DOCS_HOST = re.compile(r"(^|\.)(docs|developer|learn|api|reference)\.|readthedocs\.io|docs\.rs|pkg\.go\.dev|"
                       r"pypi\.org|npmjs\.com|developer\.mozilla\.org|docs\.python\.org|learn\.microsoft\.com",
                       re.I)
DOCS_WORDS = re.compile(r"\b(docs?|documentation|api|reference|sdk|library|package|framework|changelog|"
                        r"migration guide|usage example)\b", re.I)
DOCS_HINT = ("Library or API docs: Context7 first (`resolve-library-id`, then `query-docs`); Microsoft Learn for "
             ".NET, Azure and Windows; web search last.")

SEARCH_HINT = ("`{name}` looks like a symbol. codebase-memory `search_graph` and `trace_path` give its definition "
               "and callers; Serena `find_symbol` and `find_referencing_symbols` give the exact place to edit.")
SEARCH_HINT_PLAIN = ("Searching code by text: codebase-memory `search_graph` and `trace_path` find definitions "
                     "and callers; Serena `find_symbol` finds the exact place to edit.")


def state_dir() -> Path:
    """The same rule as loadout's paths.state_dir() (this hook cannot import loadout)."""
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or str(Path.home())
    base = os.environ.get("XDG_STATE_HOME", "")
    root = Path(base) if base and Path(base).is_absolute() else Path(home) / ".local" / "state"
    return root / "loadout" / "tool-hint"


def symbol(pattern: object) -> str | None:
    """The symbol a search pattern looks for, or None (a common word, a phrase, a regex soup)."""
    if not isinstance(pattern, str) or len(pattern) > 200:
        return None
    p = pattern.strip().strip("'\"")
    p = re.sub(r"^\^|\$$|\\b", "", p)
    m = DECL.search(p)
    if m:
        name = m.group(1)
    else:
        m = CALL.match(p)
        name = m.group(1) if m else (p if IDENT.fullmatch(p) else None)
    if not name or name.lower() in COMMON:
        return None
    return name


def _words(command: object) -> list[str]:
    if isinstance(command, list):
        return [w for w in command if isinstance(w, str)][:200]
    if not isinstance(command, str) or len(command) > 4000:
        return []
    try:
        return shlex.split(command)[:200]
    except ValueError:
        return command.split()[:200]


def shell_search(command: object) -> tuple[bool, str | None, list[str]]:
    """(is a search, symbol or None, path arguments) for the first rg/grep/git grep/find in a shell command.
    A grep that filters another command's output (`ls | grep X`) and a find that changes files are no search."""
    words = _words(command)
    for i, w in enumerate(words):
        base = os.path.basename(w)
        piped = i > 0 and words[i - 1] == "|"
        if base == "find":
            rest = words[i + 1:]
            if any(x in ("-delete", "-exec", "-execdir", "-ok", "-okdir") for x in rest):
                return False, None, []
            for j, x in enumerate(rest[:-1]):
                if x in ("-name", "-iname") and rest[j + 1].endswith(CODE_EXT):
                    return True, None, FIND
            return False, None, []
        if base == "git" and i + 1 < len(words) and words[i + 1] == "grep":
            return _search_args(words[i + 2:])
        if base in SEARCH_CMDS:
            return (False, None, []) if piped else _search_args(words[i + 1:])
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
    return bool(paths) and all(p.lower().endswith(NON_CODE) for p in paths)


FILTERS = frozenset({"-t", "--type", "-g", "--glob", "--include", "--iglob"})
DOC_TYPES = frozenset({"md", "markdown", "rst", "txt", "json", "jsonl", "yaml", "yml", "toml", "csv", "log", "html",
                       "xml", "ini", "cfg"})


def doc_filter(value: object) -> bool:
    """A file type or glob that limits a search to docs, configs or data (`-t md`, `-g '*.json'`)."""
    if not isinstance(value, str) or not value:
        return False
    v = value.strip("'\"").lower()
    return v in DOC_TYPES or v.endswith(NON_CODE)


def code_repo(cwd: object) -> bool:
    if not isinstance(cwd, str) or not cwd:
        return False
    try:
        with os.scandir(cwd) as it:
            for n, entry in enumerate(it):
                if n > 300:
                    break
                if entry.name in CODE_MARKERS or entry.name.endswith(CODE_EXT):
                    return True
                if entry.name == "src" and entry.is_dir():
                    return True
    except OSError:
        return False
    return False


def _load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    os.replace(tmp, path)


def _clean(folder: Path) -> None:
    cutoff = time.time() - KEEP_DAYS * 86400
    try:
        for entry in os.scandir(folder):
            if entry.name.endswith(".json") and entry.stat().st_mtime < cutoff:
                os.unlink(entry.path)
    except OSError:
        pass


def _int(data: dict, key: str, default: int) -> int:
    v = data.get(key)
    return v if isinstance(v, int) and not isinstance(v, bool) else default


def _emit(event: str, text: str) -> None:
    out = {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text[:MAX_CHARS]}}
    sys.stdout.write(json.dumps(out))


def search_event(tool: str, tool_input: dict) -> tuple[bool, str | None]:
    """(counts as a symbol search, symbol)."""
    if tool == "Grep":
        path = tool_input.get("path") or tool_input.get("glob") or ""
        if isinstance(path, str) and non_code([path]):
            return False, None
        if doc_filter(tool_input.get("type")) or doc_filter(tool_input.get("glob")):
            return False, None
        name = symbol(tool_input.get("pattern"))
        return name is not None, name
    if tool == "Glob":
        pattern = tool_input.get("pattern")
        return isinstance(pattern, str) and pattern.endswith(CODE_EXT), None
    if tool in SHELL_TOOLS:
        is_search, name, paths = shell_search(tool_input.get("command"))
        if not is_search or non_code(paths):
            return False, None
        return (name is not None or paths is FIND), name  # a common word or a phrase never counts
    return False, None


def handle(payload: dict) -> None:
    session = payload.get("session_id")
    if not isinstance(session, str) or not SESSION.match(session):
        return
    event = payload.get("hook_event_name") or ""
    tool = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    folder = state_dir()
    path = folder / f"{session}.json"
    fresh = not path.exists()
    state = _load(path)
    if event == "PostToolUse":
        if MCP.match(tool):
            state["searches"] = 0
            _save(path, state)
        return
    if event != "PreToolUse":
        return
    hit, name = search_event(tool, tool_input)
    docs = not hit and docs_event(tool, tool_input)
    if not hit and not docs:
        return
    if hit and not code_repo(payload.get("cwd")):
        return
    calls = _int(state, "calls", 0) + 1
    state["calls"] = calls
    text = None
    if hit:
        searches = _int(state, "searches", 0) + 1
        state["searches"] = searches
        if searches >= SEARCHES and calls - _int(state, "last_hint", -SPACING) >= SPACING:
            text = SEARCH_HINT.format(name=name[:40]) if name else SEARCH_HINT_PLAIN
            state["searches"], state["last_hint"] = 0, calls
    elif calls - _int(state, "last_docs", -SPACING) >= SPACING:
        text, state["last_docs"] = DOCS_HINT, calls
    _save(path, state)
    if fresh:
        _clean(folder)
    if text:
        _emit(event, text)


def docs_event(tool: str, tool_input: dict) -> bool:
    if tool == "WebFetch":
        url = tool_input.get("url")
        if not isinstance(url, str):
            return False
        host = re.sub(r"^[a-z]+://", "", url, flags=re.I).split("/", 1)[0]
        return bool(DOCS_HOST.search(host))
    if tool == "WebSearch":
        query = tool_input.get("query")
        return isinstance(query, str) and len(query) < 500 and bool(DOCS_WORDS.search(query))
    return False


def main() -> int:
    try:
        raw = sys.stdin.read(MAX_INPUT + 1)
        if len(raw) > MAX_INPUT:
            return 0
        payload = json.loads(raw)
        if isinstance(payload, dict):
            handle(payload)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
