"""Detect, redact and store plaintext secrets (MCP configs, settings env, secrets.env)."""
from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path, PurePath
from urllib.parse import parse_qsl, urlsplit

SECRET_PATTERNS = [
    r"gh[pousr]_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}", r"sk-[A-Za-z0-9_-]{20,}",
    r"apk_[A-Za-z0-9_=-]{16,}", r"xox[baprs]-[A-Za-z0-9-]{10,}", r"AKIA[0-9A-Z]{16}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"[sr]k_(?:live|test)_[A-Za-z0-9]{16,}", r"glpat-[\w-]{20,}",
    r"AIza[\w-]{35}", r"npm_[A-Za-z0-9]{36}", r"hf_[A-Za-z0-9]{30,}", r"eyJ[\w-]{10,}\.eyJ[\w-]{10,}\.[\w-]{10,}",
]
_SECRET_ANY = re.compile("|".join(f"(?:{p})" for p in SECRET_PATTERNS))  # one compiled search per value
SECRET_KEY = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|AUTH", re.I)
HEX_RUN = re.compile(r"[0-9a-fA-F]{32,}")
B64_RUN = re.compile(r"[A-Za-z0-9+/_=-]{40,}")
MASK = "***"

# Files that must never reach the personal layer (which may be a public git repo), whatever their content.
PRIVATE_DIRS = frozenset({".ssh", ".gnupg", ".aws", ".azure", ".kube", ".docker", ".password-store"})
PRIVATE_NAMES = ("*.pem", "*.key", "*.p12", "*.pfx", "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*", ".env", ".env.*",
                 ".netrc", ".npmrc", ".pypirc", "credentials", "credentials.json", "credentials.csv", "*.kdbx",
                 ".git-credentials", ".vault-token")
PRIVATE_EXEMPT = (".env.example", ".env.sample", ".env.template")  # templates without values
PRIVATE_HOME = ((".config", "gh"), (".claude.json",))  # relative to the home folder


def private_path(path: str | PurePath, home: str | PurePath | None = None) -> bool:
    """True for a path on the private-file denylist (keys, credentials, cloud and tool logins).
    With `home`, an absolute path is also checked against the home-relative entries (~/.config/gh, ~/.claude.json)."""
    p = PurePath(path)
    if any(part in PRIVATE_DIRS for part in p.parts):
        return True
    name = p.name.lower()
    if name not in PRIVATE_EXEMPT and any(fnmatch.fnmatchcase(name, pat) for pat in PRIVATE_NAMES):
        return True
    if home is not None:
        try:
            rel = p.relative_to(PurePath(home)).parts
        except ValueError:
            return False
        return any(rel[:len(entry)] == entry for entry in PRIVATE_HOME)
    return False


@dataclass
class Finding:
    server: str
    field: str      # env | headers | args | url
    key: str        # env/header name, arg key or index, URL query key
    value: str
    location: str
    fixable: bool   # user-scope env/headers in ~/.claude.json can be rewritten to ${VAR}; the rest is report-only


def high_entropy(value: str) -> bool:
    """A long hex (>= 32) or base64-ish (>= 40) run that mixes letters and digits (and cases, for base64)."""
    for m in HEX_RUN.finditer(value):
        run = m.group()
        if re.search(r"\d", run) and re.search(r"[a-fA-F]", run):
            return True
    for m in B64_RUN.finditer(value):
        run = m.group()
        if re.search(r"[a-z]", run) and re.search(r"[A-Z]", run) and re.search(r"\d", run):
            return True
    return False


def looks_secret(key: str, value: str, keyed_arg: bool = False) -> bool:
    """keyed_arg: the value came from a KEY=value argument, so the high-entropy test applies too."""
    if not isinstance(value, str) or "${" in value or _placeholder(value) or (_words(value) and _meta(value)):
        return False
    if _SECRET_ANY.search(value):
        return True
    if SECRET_KEY.search(key) and len(value) >= 12:
        return True
    return keyed_arg and high_entropy(value)


_JSON_PAIR = re.compile(r'"(?P<k>[^"\\]*)"(?P<sep>\s*:\s*)"(?P<v>(?:[^"\\]|\\.)*)"')
_PY_PAIR = re.compile(r"'(?P<k>[^'\\\n]*)'(?P<sep>\s*:\s*)'(?P<v>(?:[^'\\\n]|\\.)*)'")  # Python dicts
# YAML / INI / env line: `key: value` or `key = value`, anchored per line with one quantifier for the key
# (linear); the key and value are checked in _line_pair(). The keyword must be the key's LAST segment
# (`api_key`, `db.password`, but not `auth_url` or `token_budget`).
_LINE_PAIR = re.compile(r"^(?P<pre>[ \t]*(?:-[ \t]+)?(?:export[ \t]+)?(?P<q>[\"']?)(?P<k>[A-Za-z0-9_.-]+)(?P=q)"
                        r"[ \t]*[:=][ \t]*)(?P<v>\S+)", re.M)
# The key ends in a keyword: after a separator or at the start (any case; `api_key`, `db.password`, `Password`),
# after a lower-to-upper case boundary (`apiKey`, `clientSecret`), or as an upper-case suffix (`PGPASSWORD`;
# not a bare KEY suffix, so MONKEY/HOTKEY stay out). An `_id` after the keyword counts too (`private_key_id`).
# `auth_url`, `token_budget` and `monkey` do not match.
_LINE_KEY = re.compile(r"(?:(?:^|[_.-])(?i:key|token|secret|passw(?:or)?d|pass|passphrase|pwd|auth)"
                       r"|(?<=[a-z])(?:Key|Token|Secret|Password|Passwd|Pwd|Auth)"
                       r"|(?:PASSWORD|PASSWD|TOKEN|SECRET))(?:[_.-](?i:id))?$")
_PLACEHOLDER = re.compile(r"^(?:\$\{.*|\$[A-Za-z_][A-Za-z0-9_]*|<.*)$")
_CALL = re.compile(r"\w[\w.]*\(.*\)")                                   # getpass(), os.getenv("X")
_ENV_LOOKUP = re.compile(r"(?:process\.env\.|import\.meta\.env\.|settings\.|os\.environ\b)")
_CAPS_PLACEHOLDER = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+")   # YOUR_API_KEY
_PLAIN_WORDS = re.compile(r"[a-z]+(?:[-_.][a-z]+)*")               # required, lint-and-format, request.url.path
# Word-like: one lowercase word of up to 15 letters (authentication), or 2+ short segments joined by - _ .
# where each is a word of up to 15 letters with up to 3 trailing digits (v18, oauth2) or a number of up to 4
# digits (2, 2024).
_SEGMENT = r"(?:[a-z]{1,15}\d{0,3}|\d{1,4})"
_WORDS = re.compile(rf"[a-z]{{1,15}}|{_SEGMENT}(?:[-_.]{_SEGMENT})+")
_WORD = re.compile(r"[a-z]{1,15}\d{0,3}")  # rootpass, hunter22: a word under a strict key
_PROSE_WORD = re.compile(r"[A-Z]?[a-z]{1,15}")  # after a bare `token` in prose: "token Management"
_PLACEHOLDER_WORDS = frozenset({"required", "optional", "none", "null", "true", "false", "unlimited", "changeme"})
_YOUR_PLACEHOLDER = re.compile(r"(?i:your[-_.]\w*[-_.]here)|YOUR_[A-Z0-9_]*")   # your_api_key_here, YOUR_KEY
# Under a password or secret key a word-like value is a secret (hunter-22, rootpass) unless one of its segments
# says it is a placeholder or a name (example-password, my-secret-name-2, generate-with-openssl).
_STRICT_KEY = re.compile(r"(?i:passw(?:or)?d|secret)(?:[_.-](?i:id))?$")
_META_WORDS = frozenset({"example", "sample", "dummy", "placeholder", "name", "generate", "replace", "change",
                         "changeme", "your", "here", "secret", "password", "fake"})
_SEGMENTS = re.compile(r"[a-z]+")
# Code, not a value: a call or an index (getpass.getpass(...), cfg['x'], tokens[i]), an f-string with a field
# (f"Bearer {access}"), or a type annotation followed by = (password: Optional[str] = None). Checked on the
# rest of the line after the separator.
_CODE = re.compile(r"\w[\w.]*[(\[]|[fF][rR]?([\"'])[^\"'\n]*\{")
_ANNOTATION = re.compile(r"[A-Za-z_][\w.\[\], |]*?[ \t]=(?!=)")


def _path_or_url(value: str) -> bool:
    return value.startswith(("/", "~", "./", "../")) or "://" in value


def _reference(value: str) -> bool:
    """A value that names a secret instead of holding it: starts with `$`, contains `${`, `$(` or a `{{`
    template, is a call (`getpass()`), or an env lookup (process.env.X, settings.X, os.environ[...])."""
    return value.startswith("$") or "${" in value or "$(" in value or "{{" in value or MASK in value \
        or _ENV_LOOKUP.match(value) is not None or _CALL.fullmatch(value) is not None


def _words(value: str) -> bool:
    """Ordinary words rather than a secret: under 20 chars, word-like segments (see _WORDS), mostly letters."""
    if len(value) >= 20 or not _WORDS.fullmatch(value):
        return False
    letters = sum(c.isalpha() for c in value)
    return letters * 2 >= sum(c.isalnum() for c in value)


def _placeholder(value: str) -> bool:
    return value.lower() in _PLACEHOLDER_WORDS or _YOUR_PLACEHOLDER.fullmatch(value) is not None


def _meta(value: str) -> bool:
    return any(w in _META_WORDS for w in _SEGMENTS.findall(value.lower()))


def _secret_value(value: str, strict: bool = False) -> bool:
    """A config value that looks like a real secret rather than a word, a path, a URL, a reference or a
    placeholder. Not secret: under 8 chars, whitespace, a path or URL (starts with / ~ ./ ../ or contains
    ://), a reference (see _reference), ALL_CAPS_PLACEHOLDER, a placeholder word, or word-like (see _words).
    Fails closed: everything else is a secret (a 20+ char passphrase, a 16+ letter single word, letters
    mixed with digits, digits only, mixed case, symbols). `$`, `<` or `(` inside a value do not make it a reference."""
    if len(value) < 8 or any(c.isspace() for c in value) or _path_or_url(value) or _reference(value):
        return False
    if _CAPS_PLACEHOLDER.fullmatch(value) or _placeholder(value):
        return False
    if _words(value) or (strict and _WORD.fullmatch(value)):
        return strict and not _meta(value)  # strict (a password or secret key): a word is a secret too
    return True  # fail closed: whatever no rule above clearly calls a non-secret counts as a secret


# The lookbehind starts a match only at a token boundary: same matches (a key is the whole run before "="),
# but linear time on long runs without "=" (unanchored, it backtracked quadratically).
_KEY_EQ = re.compile(r"(?<![A-Za-z0-9_.-])(?P<k>[A-Za-z0-9_.-]+)=(?P<v>[^\s&'\"]+)")
# Anchored at a token start, one quantifier for the flag name; the keyword is checked in redact() (linear time).
_FLAG_VALUE = re.compile(r"(?<![A-Za-z0-9_-])(?P<k>--?[A-Za-z0-9_-]+)(?P<sp>\s+)(?P<v>[^\s-]\S{7,})")
_FLAG_WORD = re.compile(r"key|token|secret|password|auth", re.I)
_URL_PASSWORD = re.compile(r"(?P<k>(?<![a-z0-9+.-])[a-z][a-z0-9+.-]*://[^\s:/@]+:)(?P<v>[^\s@/]+)(?=@)", re.I)
# Same line only; after a bare `token` the value must look like a secret (".../token\nkey_path: ..." is not one).
# More shapes: curl -u user:pass, sshpass -p 'pass', a quoted keyword argument or assignment anywhere on a line
# (Client(api_key='...'), self.secret = '...'); each anchored at a token start with one quantifier per part.
_USER_PASS = re.compile(r"(?P<k>(?<![\w-])(?:-u|--user)[ \t]+['\"]?[\w.@-]+:)(?P<v>[^\s'\"]+)")
_SSHPASS = re.compile(r"(?P<k>(?<![\w-])sshpass[ \t]+-p[ \t]*(?P<q>['\"]?))(?P<v>[^\s'\"]+)")
_KWARG = re.compile(r"(?P<k>(?:(?<![\w.\-])(?P<n>[A-Za-z_]\w*)|\[(?P<sq>['\"])(?P<s>[A-Za-z_]\w*)(?P=sq)\])"
                    r"[ \t]*=[ \t]*(?P<q>['\"]))(?P<v>[^'\"\n]*)(?P=q)")   # also os.environ['API_KEY'] = '...'

_BEARER = re.compile(r"(?P<k>\b(?P<w>Bearer|Basic|token)[ \t]+)(?P<v>[A-Za-z0-9._~+/=-]{8,})")


def _code(rest: str, colon: bool) -> bool:
    """The text after `key =` / `key:` is code rather than a value (see _CODE, _ANNOTATION)."""
    return _CODE.match(rest) is not None or (colon and _ANNOTATION.match(rest) is not None)


def _line_pair(m: re.Match) -> str:
    value = m["v"].strip("'\",;")
    if len(value) < 8 or not _LINE_KEY.search(m["k"]) or m["k"].lower() == "key" or _PLACEHOLDER.match(value):
        return m.group()   # cheapest test first; a bare `key` field is not a secret
    end = m.string.find("\n", m.start("v"))
    if _code(m.string[m.start("v"):end if end >= 0 else len(m.string)], m["pre"].rstrip()[-1:] == ":"):
        return m.group()
    if not _secret_value(value, strict=_STRICT_KEY.search(m["k"]) is not None):
        return m.group()
    return m["pre"] + MASK


def _keyed_value(key: str, value: str) -> bool:
    """`key` names a secret field (as in the line rule) and `value` looks like a secret."""
    return len(value) >= 8 and _LINE_KEY.search(key) is not None and key.lower() != "key" \
        and MASK not in value and _secret_value(value, strict=_STRICT_KEY.search(key) is not None)


def _pair_secret(key: str, value: str) -> bool:
    return looks_secret(key, value) or _keyed_value(key, value)


def redact(text: str) -> str:
    """Mask anything that looks like a secret before it reaches the console."""
    if not text:
        return text
    text = _JSON_PAIR.sub(lambda m: f'"{m["k"]}"{m["sep"]}"{MASK}"' if _pair_secret(m["k"], m["v"]) else m.group(), text)
    text = _PY_PAIR.sub(lambda m: f"'{m['k']}'{m['sep']}'{MASK}'" if _pair_secret(m["k"], m["v"]) else m.group(), text)
    text = _LINE_PAIR.sub(_line_pair, text)
    text = _KWARG.sub(lambda m: m["k"] + MASK + m["q"] if _keyed_value(m["n"] or m["s"], m["v"]) else m.group(), text)
    text = _USER_PASS.sub(lambda m: m["k"] + MASK if _secret_value(m["v"]) else m.group(), text)
    text = _SSHPASS.sub(lambda m: m["k"] + MASK if not _reference(m["v"]) and MASK not in m["v"] else m.group(), text)
    text = _BEARER.sub(lambda m: m["k"] + MASK if m["w"] != "token" or (_secret_value(m["v"]) and not _PROSE_WORD.fullmatch(m["v"]))
                       else m.group(), text)
    text = _URL_PASSWORD.sub(lambda m: m["k"] + (m["v"] if m["v"].startswith("${") else MASK), text)
    text = _KEY_EQ.sub(lambda m: f"{m['k']}={MASK}" if looks_secret(m["k"], m["v"], keyed_arg=True)
                       or (m["k"].startswith("-") and _keyed_value(m["k"].lstrip("-"), m["v"])) else m.group(), text)
    text = _FLAG_VALUE.sub(lambda m: m["k"] + m["sp"] + MASK if _FLAG_WORD.search(m["k"])
                           and not m["v"].startswith(("/", "~", "./", "../")) else m.group(), text)
    for pattern in SECRET_PATTERNS:
        text = re.sub(pattern, MASK, text)
    return text


def var_name(server: str, key: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", f"{server}_{key}".upper()).strip("_")


def scan(claude_json: dict, location: str = "~/.claude.json", fixable: bool = True) -> list[Finding]:
    """Secrets in a {"mcpServers": {...}} mapping. `fixable` marks env/headers findings as movable."""
    found = []
    servers = claude_json.get("mcpServers")
    for server, cfg in (servers if isinstance(servers, dict) else {}).items():
        if not isinstance(cfg, dict):
            continue
        for field in ("env", "headers"):
            mapping = cfg.get(field)
            for key, value in (mapping if isinstance(mapping, dict) else {}).items():
                if looks_secret(key, value):
                    found.append(Finding(server, field, key, value, location, fixable))
        args = cfg.get("args")
        for i, arg in enumerate(args if isinstance(args, list) else []):
            if not isinstance(arg, str):
                continue
            keyed = "=" in arg
            key = arg.split("=", 1)[0] if keyed else str(i)
            value = arg.split("=", 1)[1] if keyed else arg
            if looks_secret(key, value, keyed_arg=keyed):
                found.append(Finding(server, "args", key, value, location, False))
        url = cfg.get("url")
        if isinstance(url, str) and "?" in url:
            for key, value in parse_qsl(urlsplit(url).query):
                if looks_secret(key, value, keyed_arg=True):
                    found.append(Finding(server, "url", key, value, location, False))
    return found


def scan_all() -> list[Finding]:
    """Every place the kit knows MCP servers or env values live. Only user-scope ~/.claude.json is fixable."""
    from . import paths
    from .jsonio import load_json

    claude_json = load_json(paths.claude_json())
    found = scan(claude_json)
    projects = claude_json.get("projects")
    for proj, cfg in (projects if isinstance(projects, dict) else {}).items():
        if isinstance(cfg, dict):
            found += scan(cfg, f"~/.claude.json projects[{proj}]", fixable=False)
    found += scan(load_json(paths.claude_home() / ".mcp.json"), "~/.claude/.mcp.json", fixable=False)
    personal = paths.personal_root() / "mcp.json"
    found += scan(load_json(personal), str(personal), fixable=False)
    env = load_json(paths.claude_home() / "settings.json").get("env")
    for key, value in (env if isinstance(env, dict) else {}).items():
        if looks_secret(key, value, keyed_arg=True):
            found.append(Finding("settings.json", "env", key, value, "~/.claude/settings.json", False))
    return found


# secrets.env format: NAME='value' with POSIX single-quote escaping, so `. secrets.env` never
# executes or mangles a value. The PowerShell loader (bootstrap.PS_BLOCK) parses the same format.
_ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def parse_env_line(line: str) -> tuple[str, str] | None:
    m = _ENV_LINE.match(line.rstrip("\r\n"))
    if not m:
        return None
    name, raw = m.group(1), m.group(2).strip()
    if len(raw) >= 2 and raw[0] == raw[-1] == "'":
        return name, raw[1:-1].replace("'\\''", "'")
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        return name, raw[1:-1]
    return name, raw


def load_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parsed = parse_env_line(line)
        if parsed:
            out[parsed[0]] = parsed[1]
    return out


def rewrite(server: str, cfg: dict, findings: list[Finding], known: dict[str, str]) -> tuple[dict, list[str], list[str]]:
    """Replace each fixable finding's value in a copy of cfg with ${VAR}. known (secrets.env) is updated in place.

    Returns (new config, new secrets.env lines, var names). A name that already holds a different value is
    never reused: _2, _3, ... is appended instead.
    """
    import json

    new = json.loads(json.dumps(cfg))
    lines, names = [], []
    for f in findings:
        var = var_name(f.server, f.key)
        n = 2
        while var in known and known[var] != f.value:
            var = f"{var_name(f.server, f.key)}_{n}"
            n += 1
        if var not in known:
            known[var] = f.value
            lines.append(f"{var}={quote(f.value)}\n")
        new[f.field][f.key] = new[f.field][f.key].replace(f.value, "${" + var + "}")
        names.append(var)
    return new, lines, names


def append_env(path: Path, lines: list[str], bk) -> None:
    """Append to secrets.env; a new file is created 0600 from the start and recorded as created."""
    import os

    if not lines:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_bytes() if path.exists() else b""
    if path.exists():
        bk.save_copy(path, "secrets.env before additions")
    else:
        os.close(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
        bk.record_created(path, "created secrets.env")
    if os.name != "nt":
        os.chmod(path, 0o600)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        if existing and not existing.endswith(b"\n"):
            fh.write("\n")
        fh.writelines(lines)
