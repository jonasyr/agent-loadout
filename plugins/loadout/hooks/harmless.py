"""Searches and reads that Serena's `remind` hook cannot help with (stdlib only).

The guard (mcp_guard.py) calls `skips_remind(payload)` before it runs `serena-hooks remind`: a call that is only
harmless greps (behind a pipe, in config or doc files, limited to doc types, outside the project) or reads of files
outside the project is not counted. Anything not provably harmless goes to Serena ("when in doubt, Serena").

The shell parsing mirrors Serena 2.1.0's `PreToolUseRemindAboutSymbolicToolsHook` (`ShellCommandLine`,
`_GREP_SHELL_COMMANDS`, `_READ_SHELL_COMMANDS`, `_is_read_invocation`), so both see the same invocations. The
suffix lists and filter rules are a copy of cli/loadout/searches.py (hooks cannot import loadout; a test keeps
NON_CODE in step). See docs/reference/hooks.md."""
from __future__ import annotations

import os
import re
import shlex

NON_CODE = (".log", ".md", ".markdown", ".rst", ".txt", ".json", ".jsonl", ".toml", ".yaml", ".yml", ".csv",
            ".lock", ".ini", ".cfg", ".env", ".html", ".xml")
CONFIG_NAMES = frozenset({".gitignore", ".gitattributes", ".editorconfig", ".npmrc", ".dockerignore", ".prettierrc",
                          ".eslintignore", "Makefile", "Dockerfile", "LICENSE", "CODEOWNERS", "README"})
GREP_CMDS = frozenset({"grep", "rg", "ag", "ack", "fgrep", "egrep", "ugrep", "ug"})
READ_CMDS = frozenset({"cat", "head", "tail", "sed", "awk", "less", "more", "bat", "get-content", "gc"})

TAKES_VALUE = frozenset({"-g", "-t", "-T", "-m", "-A", "-B", "-C", "-f", "--glob", "--type", "--type-not",
                         "--max-count", "--include", "--exclude", "--exclude-dir", "-d", "--max-depth"})
FILTERS = frozenset({"-t", "--type", "-g", "--glob", "--include", "--iglob"})
DOC_TYPES = frozenset({"md", "markdown", "rst", "txt", "json", "jsonl", "yaml", "yml", "toml", "csv", "log", "html",
                       "xml", "ini", "cfg"})
PATTERN_OPTS = frozenset({"-e", "--regexp", "-f", "--file"})

_CONTROL = frozenset(("&&", "||", ";", ";;", "|", "|&", "&", "(", ")"))
_PIPES = frozenset(("|", "|&"))
_REDIRECT = frozenset((">", ">>", ">|", ">&", "&>", "&>>", "<", "<<", "<<<", "<&", "<>"))
_PREFIX = frozenset(("command", "env", "exec"))
_ASSIGN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
_SHELLS = frozenset({"bash", "sh", "zsh", "dash", "fish"})


def doc_filter(value: object) -> bool:
    """A file type or glob that limits a search to docs, configs or data (`-t md`, `-g '*.json'`)."""
    if not isinstance(value, str) or not value:
        return False
    v = value.strip("'\"").lower()
    return v in DOC_TYPES or v.endswith(NON_CODE)


def harmless_path(path: str, cwd: str) -> bool:
    """True for a config or doc file, or a path outside the project folder `cwd`; false when unsure."""
    if not isinstance(path, str) or not path or "$" in path or "`" in path:
        return False
    base = os.path.basename(path)
    if base in CONFIG_NAMES or base.startswith(".env"):
        return True
    if os.path.splitext(base)[1].lower() in NON_CODE:
        return True
    root = os.path.normpath(cwd)
    full = os.path.normpath(os.path.join(root, os.path.expanduser(path)))
    return full != root and not full.startswith(root.rstrip(os.sep) + os.sep)


def _has_suffix(path: str) -> bool:
    return bool(os.path.splitext(os.path.basename(path))[1])


def _blocks(operands: list[str], cwd: str) -> bool:
    """Some operand is a file with a suffix that is not harmless: a code file inside the project."""
    return any(_has_suffix(o) and not harmless_path(o, cwd) for o in operands)


def _segments(line: str):
    """(program, arguments, piped) per simple command; `piped` is true after `|` or `|&`. None if unparseable."""
    lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return None
    segs: list[tuple[list[str], bool]] = [([], False)]
    skip = False
    for i, tok in enumerate(tokens):
        if skip:
            skip = False
        elif tok in _CONTROL:
            segs.append(([], tok in _PIPES))
        elif tok in _REDIRECT:
            skip = True
        elif tok.isdigit() and i + 1 < len(tokens) and tokens[i + 1] in _REDIRECT:
            continue  # the fd of `2>&1`
        else:
            segs[-1][0].append(tok)
    out = []
    for seg, piped in segs:
        if not seg:
            continue
        i = 0
        while i < len(seg):
            if _ASSIGN.match(seg[i]):
                i += 1
            elif os.path.basename(seg[i]).lower() in _PREFIX:
                i += 1
                while i < len(seg) and seg[i].startswith("-"):
                    i += 1
            else:
                break
        if i < len(seg):
            out.append((os.path.basename(seg[i]).lower(), seg[i + 1:], piped))
    return out


def _grep_paths(args: list[str]):
    """(paths, limited to docs by a filter) of a grep invocation's arguments."""
    paths: list[str] = []
    have_pattern = False
    limited = False
    skip = False
    ended = False
    for j, a in enumerate(args):
        if skip:
            skip = False
            continue
        if ended or not a.startswith("-") or a == "-":
            if have_pattern:
                paths.append(a)
            else:
                have_pattern = True
            continue
        if a == "--":
            ended = True
            continue
        name, eq, val = a.partition("=")
        if name in FILTERS:
            value = val if eq else (args[j + 1] if j + 1 < len(args) else "")
            limited = limited or doc_filter(value)
        if name in PATTERN_OPTS:
            have_pattern = True
        if not eq and a in TAKES_VALUE | PATTERN_OPTS:
            skip = True
    return paths, limited


def _is_read(prog: str, args: list[str]) -> bool:
    if prog not in READ_CMDS:
        return False
    return not (prog == "sed" and any(a == "--in-place" or a.startswith(("-i", "--in-place=")) for a in args))


def _operands(args: list[str]) -> list[str]:
    return [a for a in args if a and not a.startswith("-")]


def _bash_skips(line: str, cwd: str) -> bool:
    segs = _segments(line)
    if not segs:
        return False
    found = False
    pipeline_blocked = False  # an earlier segment of the current pipeline reads a code file
    in_pipeline = False
    for prog, args, piped in segs:
        if not piped:
            pipeline_blocked, in_pipeline = False, False
        else:
            in_pipeline = True
        blocks_here = _blocks(_operands(args), cwd)
        if prog in GREP_CMDS:
            found = True
            paths, limited = _grep_paths(args)
            ok = ((in_pipeline and not pipeline_blocked) or limited
                  or (bool(paths) and all(harmless_path(p, cwd) for p in paths)))
            if not ok:
                return False
        elif _is_read(prog, args):
            found = True
            if blocks_here:
                return False
        pipeline_blocked = pipeline_blocked or blocks_here
    return found


def _command(tool_input: dict) -> str | None:
    cmd = tool_input.get("command", tool_input.get("cmd"))
    if isinstance(cmd, list):
        words = [w for w in cmd if isinstance(w, str)]
        if len(words) >= 3 and os.path.basename(words[0]) in _SHELLS and words[1] in ("-c", "-lc", "-ic"):
            return words[2]
        return shlex.join(words)
    return cmd if isinstance(cmd, str) else None


def skips_remind(payload: dict) -> bool:
    """True when the hook payload is a call Serena's `remind` should not see (neither counted nor denied)."""
    try:
        cwd = payload.get("cwd")
        ti = payload.get("tool_input")
        if not isinstance(cwd, str) or not cwd or not isinstance(ti, dict):
            return False
        tool = payload.get("tool_name")
        if tool == "Bash":
            line = _command(ti)
            return line is not None and _bash_skips(line, cwd)
        if tool == "Read":
            return harmless_path(ti.get("file_path"), cwd)
        if tool == "Grep":
            if doc_filter(ti.get("glob")) or doc_filter(ti.get("type")):
                return True
            p = ti.get("path")
            return bool(p) and harmless_path(p, cwd)
    except (TypeError, ValueError, AttributeError):
        return False
    return False
