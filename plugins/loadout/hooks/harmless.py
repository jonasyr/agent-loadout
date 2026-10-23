"""Searches and reads that Serena's `remind` hook cannot help with (stdlib only).

The guard (mcp_guard.py) calls `skips_remind(payload)` before it runs `serena-hooks remind`: a call that is only
harmless greps (behind a pipe, in config or doc files, limited to doc types, outside the project) or reads of files
outside the project is not counted. Anything not provably harmless goes to Serena ("when in doubt, Serena").

Only simple lines can be harmless: commands joined by `&&`, `||`, `;` and pipes. A line with a `cd`, a loop, a
group or subshell, a command substitution or a process substitution goes to Serena whole, because where it runs
and what it reads cannot be told before the shell runs it.

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

_CONTROL = frozenset(("&&", "||", ";", ";;", "|", "|&", "&"))
_PIPES = frozenset(("|", "|&"))
_REDIRECT = frozenset((">", ">>", ">|", ">&", "&>", "&>>", "<", "<<", "<<<", "<&", "<>"))
_PREFIX = frozenset(("command", "env", "exec"))
_ASSIGN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
_SHELLS = frozenset({"bash", "sh", "zsh", "dash", "fish"})
# a line with any of these is not simple: Serena gets it whole
_COMPLEX_TOKENS = frozenset(("(", ")", "{", "}"))
_COMPLEX_PROGRAMS = frozenset(("for", "while", "until", "if", "case", "select", "function", "do", "done", "then",
                               "else", "elif", "fi", "esac", "!", "time", "coproc", "cd", "pushd", "popd"))
_GLOB = re.compile(r"[*?\[]")
_VAR_WORD = re.compile(r"[\w./~${}-]+")  # a word made of path characters and `$`: a file named by a variable


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


def harmless_path(path: str, cwd: str) -> bool:
    """True for a config or doc file, or a path outside the project folder; false when unsure."""
    if not isinstance(path, str) or not path or "$" in path or "`" in path:
        return False
    root = os.path.normpath(_project(cwd))
    full = os.path.normpath(os.path.join(cwd, os.path.expanduser(path)))
    if full != root and not full.startswith(root.rstrip(os.sep) + os.sep):
        return True  # outside the project
    base = os.path.basename(path.rstrip("/"))
    named = base in CONFIG_NAMES or base.startswith(".env") or os.path.splitext(base)[1].lower() in NON_CODE
    try:
        if not named or os.path.isdir(full):  # a folder named `docs.md` holds whatever it holds
            return False
        if _GLOB.search(path):  # `*.md` is what the shell expands it to: no folder may be among the matches
            import glob
            return not any(os.path.isdir(m) for m in glob.glob(full))
        return True
    except (OSError, ValueError):
        return False


def _is_dir(path: str, cwd: str) -> bool:
    if path in (".", "./") or path.endswith("/"):
        return True
    try:
        return not _GLOB.search(path) and os.path.isdir(os.path.join(cwd, os.path.expanduser(path)))
    except (OSError, ValueError):
        return False


def _code_file(operand: str, cwd: str) -> bool:
    """A code file of the project, or a file that cannot be told before the shell runs: a suffix that is not
    harmless, a wildcard (`bin/*`), a variable (`$f`), or an existing file without a suffix (`bin/loadout`) that is
    not a config name. An operand that names no file (a sed script, an awk program, a count) is none."""
    if harmless_path(operand, cwd):
        return False
    if "$" in operand or "`" in operand:
        return bool(_VAR_WORD.fullmatch(operand))  # `"$f"`, `src/$x.py`; not `{print $1}`
    if _GLOB.search(operand) or os.path.splitext(os.path.basename(operand))[1]:
        return True
    try:
        return os.path.isfile(os.path.join(cwd, os.path.expanduser(operand)))
    except (OSError, ValueError):
        return True


def _segments(line: str):
    """(program, arguments, piped) per simple command; `piped` is true after `|` or `|&`. None when the line is not
    simple (see the module docstring) or does not parse."""
    if "`" in line or "$(" in line or "<(" in line or ">(" in line:
        return None
    lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return None
    if any(tok in _COMPLEX_TOKENS for tok in tokens):
        return None
    segs: list[tuple[list[str], bool]] = [([], False)]
    skip = False
    for i, tok in enumerate(tokens):
        if skip:
            skip = False
        elif tok in _CONTROL:
            segs.append(([], tok in _PIPES))
        elif tok in ("<", "<>"):
            if not segs[-1][0]:
                return None  # `< file cmd`: the redirect comes before its command, so the line is not simple
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
            elif os.path.basename(seg[i]).lower() in _PREFIX:
                i += 1
                while i < len(seg) and seg[i].startswith("-"):
                    i += 1
            else:
                break
        if i < len(seg):
            prog = os.path.basename(seg[i]).lower()
            if seg[i] in _COMPLEX_PROGRAMS or prog in _COMPLEX_PROGRAMS:
                return None
            out.append((prog, seg[i + 1:], piped))
    return out


def _grep_args(args: list[str]):
    """(paths, inclusion filter values) of a grep invocation's arguments. Long options take `=value` or the next
    word; a short cluster (`-rne`, `-efoo`, `-tmd`) ends at its first option that takes a value, whose value is the
    rest of the cluster or the next word."""
    paths: list[str] = []
    includes: list[str] = []
    have_pattern = False
    skip = None  # the option whose value the next word is
    ended = False
    for a in args:
        if skip is not None:
            if skip in PATTERN_OPTS:
                have_pattern = True
            elif skip in FILTERS and not a.strip("'\"").startswith("!"):
                includes.append(a)
            skip = None
            continue
        if ended or not a.startswith("-") or a == "-":
            if have_pattern:
                if a != "-":  # `-` is stdin
                    paths.append(a)
            else:
                have_pattern = True
            continue
        if a == "--":
            ended = True
            continue
        if a.startswith("--"):
            name, eq, val = a.partition("=")
            if name in TAKES_VALUE | PATTERN_OPTS:
                if eq:
                    have_pattern = have_pattern or name in PATTERN_OPTS
                    if name in FILTERS and not val.strip("'\"").startswith("!"):
                        includes.append(val)
                else:
                    skip = name
            continue
        for k, c in enumerate(a[1:], 1):  # a short cluster
            opt = "-" + c
            if opt in TAKES_VALUE | PATTERN_OPTS:
                rest = a[k + 1:]
                if not rest:
                    skip = opt
                elif opt in PATTERN_OPTS:
                    have_pattern = True
                elif opt in FILTERS and not rest.startswith("!"):
                    includes.append(rest)
                break
    return paths, includes


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


def _grep_harmless(paths: list[str], includes: list[str], piped: bool, code_before: bool, cwd: str) -> bool:
    limited = bool(includes) and all(doc_filter(v) for v in includes)
    if paths:  # an explicit path is read whatever the filters say; a filter limits only a folder's walk
        return all(harmless_path(p, cwd) or (limited and _is_dir(p, cwd)) for p in paths)
    return (piped and not code_before) or limited


def _bash_skips(line: str, cwd: str) -> bool:
    segs = _segments(line)
    if not segs:
        return False
    found = False
    code_before = False  # an earlier command of the line names a code file
    for prog, args, piped in segs:
        operands = _operands(args)
        if prog in GREP_CMDS:
            found = True
            paths, includes = _grep_args(args)
            if not _grep_harmless(paths, includes, piped, code_before, cwd):
                return False
        elif _is_read(prog, args):
            found = True
            if any(_code_file(o, cwd) for o in operands):
                return False
        code_before = code_before or any(_code_file(o, cwd) for o in operands)
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
            p = ti.get("path")
            includes = [v for v in (ti.get("glob"), ti.get("type")) if isinstance(v, str) and v]
            return _grep_harmless([p] if isinstance(p, str) and p else [], includes, False, False, cwd)
    except (TypeError, ValueError, AttributeError):
        return False
    return False
