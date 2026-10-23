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
_KEYWORDS = frozenset(("{", "}", "!", "do", "then", "else", "elif", "time"))  # before the program of a compound part
_CD = frozenset(("cd", "pushd"))
_FILE_LIKE = re.compile(r"[\w./~-]*[A-Za-z_][\w./~-]*")  # a path-like word: letters, digits, `_ . / ~ -` only


def doc_filter(value: object) -> bool:
    """A file type or glob that limits a search to docs, configs or data (`-t md`, `-g '*.json'`)."""
    if not isinstance(value, str) or not value:
        return False
    v = value.strip("'\"").lower()
    if v.startswith("!"):  # an exclusion (`-g '!*.lock'`) limits nothing
        return False
    return v in DOC_TYPES or v.endswith(NON_CODE)


def _project(cwd: str) -> str:
    """The project folder: Claude Code's CLAUDE_PROJECT_DIR when cwd lies in it (a `cd` in an earlier call moves
    cwd), else cwd."""
    root = os.environ.get("CLAUDE_PROJECT_DIR")
    if root:
        r, c = os.path.normpath(root), os.path.normpath(cwd)
        if c == r or c.startswith(r.rstrip(os.sep) + os.sep):
            return r
    return cwd


def harmless_path(path: str, cwd: str, relative_outside: bool = True) -> bool:
    """True for a config or doc file, or a path outside the project folder; false when unsure. relative_outside:
    False after a `cd` in the same line, where a relative path's folder is unknown (only absolute and ~ paths can be
    outside then)."""
    if not isinstance(path, str) or not path or "$" in path or "`" in path:
        return False
    base = os.path.basename(path)
    if base in CONFIG_NAMES or base.startswith(".env"):
        return True
    if os.path.splitext(base)[1].lower() in NON_CODE:
        return True
    expanded = os.path.expanduser(path)
    if not relative_outside and not os.path.isabs(expanded):
        return False
    root = os.path.normpath(_project(cwd))
    full = os.path.normpath(os.path.join(cwd, expanded))
    return full != root and not full.startswith(root.rstrip(os.sep) + os.sep)


def _has_suffix(path: str) -> bool:
    return bool(os.path.splitext(os.path.basename(path))[1])


def _code_file(operand: str, cwd: str, rel: bool, here: str | None = None) -> bool:
    """A code file of the project: a suffix that is not harmless, or, without a suffix, an existing file (a script
    like bin/loadout) that is not a config name. An operand that names no file (a sed script, a count) is none.
    here: the folder relative operands resolve in after this line's `cd`s (None: unknown, so an extensionless
    relative operand counts as code)."""
    if harmless_path(operand, cwd, rel):
        return False
    if _has_suffix(operand):
        return True
    path = os.path.expanduser(operand)
    if here is None and not os.path.isabs(path):
        return bool(_FILE_LIKE.fullmatch(operand))  # a file name in an unknown folder; `1,80p` is a sed script
    try:
        return os.path.isfile(os.path.join(here or cwd, path))
    except (OSError, ValueError):
        return True


def _blocks(operands: list[str], cwd: str, rel: bool = True, here: str | None = None) -> bool:
    """Some operand is a code file inside the project."""
    return any(_code_file(o, cwd, rel, here) for o in operands)


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
        elif tok in ("<", "<>"):
            continue  # an input file is what the command reads: its target stays an operand
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
            elif seg[i] in _KEYWORDS:
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
    includes: list[str] = []
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
            if not value.strip("'\"").startswith("!"):  # an exclusion limits nothing
                includes.append(value)
        if name in PATTERN_OPTS:
            have_pattern = True
        if not eq and a in TAKES_VALUE | PATTERN_OPTS:
            skip = True
    return paths, bool(includes) and all(doc_filter(v) for v in includes)


def _is_read(prog: str, args: list[str]) -> bool:
    if prog not in READ_CMDS:
        return False
    return not (prog == "sed" and any(a == "--in-place" or a.startswith(("-i", "--in-place=")) for a in args))


def _operands(args: list[str]) -> list[str]:
    """The non-option arguments; after `--` every argument (`cat -- -script.py`)."""
    out, ended = [], False
    for a in args:
        if not ended and a == "--":
            ended = True
        elif a and (ended or not a.startswith("-")):
            out.append(a)
    return out


def _bash_skips(line: str, cwd: str) -> bool:
    segs = _segments(line)
    if not segs:
        return False
    found = False
    rel = not any(prog in _CD for prog, _, _ in segs)  # after a cd, relative paths cannot be judged as outside
    code_before = False  # an earlier segment of the line names a code file (a loop or `{ }` can feed the pipe)
    in_pipeline = False
    cds = sum(1 for prog, _, _ in segs if prog in _CD)
    here: str | None = cwd if cds <= 1 else None  # where relative operands resolve: one literal `cd` is followed;
    # with several, `&&`/`||` decide which ran, so the folder is unknown
    for prog, args, piped in segs:
        in_pipeline = piped
        operands = _operands(args)
        if prog in _CD:
            target = operands[0] if len(operands) == 1 else None
            ok_target = target is not None and target != "-" and "$" not in target and "`" not in target
            here = os.path.normpath(os.path.join(here, os.path.expanduser(target))) if ok_target and here else None
            if cds > 1:
                here = None
            if here is not None and not os.path.isdir(here):  # a cd that fails leaves the shell where it was
                here = None
            continue
        blocks_here = _blocks(operands, cwd, rel, here)
        if prog in GREP_CMDS:
            found = True
            paths, limited = _grep_paths(args)
            ok = ((in_pipeline and not code_before and not paths) or limited  # a grep with paths reads those
                  or (bool(paths) and all(harmless_path(p, cwd, rel) for p in paths)))
            if not ok:
                return False
        elif _is_read(prog, args):
            found = True
            if blocks_here or any("$" in o or "`" in o for o in operands):  # a read of an unknown file
                return False
        code_before = code_before or blocks_here
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
            return harmless_path(ti.get("file_path"), cwd)  # the Read tool takes absolute paths
        if tool == "Grep":
            if doc_filter(ti.get("glob")) or doc_filter(ti.get("type")):
                return True
            p = ti.get("path")
            return bool(p) and harmless_path(p, cwd)
    except (TypeError, ValueError, AttributeError):
        return False
    return False
