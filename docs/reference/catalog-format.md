# Catalog format

`catalog.json` at the kit root is the kit's tool knowledge: what is good, what is superseded and why. `loadout bootstrap`, `loadout adopt`, `loadout check`, `loadout configure` and `loadout update` read it. The code is `cli/loadout/catalog.py`; the rules the file must follow are enforced by the catalog tests in `tests/test_repo_static.py`.

The file is one JSON object with one key, `entries`, a list of entries. Ids are unique.

## Fields

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Unique id. For a `binary` it is also the command name that is looked up on `PATH`. |
| `kind` | yes | `mcp`, `plugin`, `marketplace`, `skill`, `hook` or `binary`. |
| `status` | yes | One of the values below. |
| `match` | yes | How an installed item is recognised. `names` and `contains` are lists of strings; at least one must be non-empty. |
| `reason` | yes | Why the entry has this status. Shown to the user, and the place where the "why" lives. |
| `short` | no | The one-line reason `loadout adopt` shows (at most 60 characters, no trailing period). `reason` stays the full explanation, shown with `--verbose`. Required for every entry whose id starts with `mcp-`, `plugin-`, `marketplace-`, `skill-`, `skills-` or `hook-`, whatever its status. |
| `by` | no | The replacement for a superseded or alternative tool. Appended to the reason as `Replacement: ...`. |
| `profile` | for `status: profile` | Name of the kit profile (a file in `profiles/`) that carries the tool. |
| `offer` | no | Makes the entry a global add-on in `loadout configure`. See below. |
| `connector` | no | For a plugin: the name of the claude.ai connector with the same tools, as Claude Code lists it (for example "claude.ai Context7"). `loadout check` warns when the plugin is enabled and the connector has been connected. |
| `target` | no | The one coding agent the entry belongs to: `claude` or `codex`. A `binary` with a target is offered and checked only while that agent is on (`targets.json`). A `plugin` with `target: claude` is never added to Codex: Codex's plugin setup and a profile's Codex side skip it, and their output names it once (`Claude Code only, not added to Codex`). |
| `category` | no | Group heading in the configure wizard. Default: `other`. |
| `required` | no | For a `binary`: a missing one is a `FAIL` in `loadout check` and is installed by `bootstrap --install`. Exceptions: a missing `codex` or `claude` is only a warning while VS Code's extension for that agent brings its own binary, and in WSL `codex` is not checked when your only Codex is the Windows one ([`binary <name>`](cli.md#loadout-check)). |
| `version` | for `binary` | How to read and look up versions. See below. |
| `install` | no | Platform commands that install a `binary`. |
| `update` | no | Platform commands that update a `binary`. |
| `manual` | no | Text shown when loadout cannot install or update a `binary` itself. |
| `mise` | no | For a `binary` installed through mise: the mise tool name for `mise upgrade`. Without it, loadout derives the name from the mise install folder (`npm:<package>` for mise's npm backend, else the id). `codex` sets it to `codex`. |
| `needs` | no | For a binary: ids of binaries it is installed with (for example "node" needs "mise"). Bootstrap installs those first and skips this one if they failed. |
| `target` | no | For a `binary`: `claude` or `codex`. The binary is installed, checked and updated only while that coding agent is chosen (`targets.json`, see [Use loadout with Codex](../how-to/codex.md)). |
| `helper` | no | For a binary: installed only when another binary needs it; `loadout check` does not report it. |

### `match`

An installed item matches an entry of the same `kind` when its name is in `names`, or when its detail text contains one of the `contains` strings. The detail is the command line of an MCP server or hook, or the path of a skill. The first matching entry in file order wins. A `binary` entry is not matched against installed items; its `id` is used.

### `status`

| Status | What `loadout adopt` does with an installed match |
|---|---|
| `core` | A plugin or marketplace is kept. Any other kind is a duplicate of what the loadout plugin provides and is offered for `migrate`. |
| `recommended` | Kept. |
| `alternative` | Kept. The reason names the kit's default. |
| `profile` | Offered for `scope-down`: disabled globally, to be enabled per project with `loadout profile <profile>`. |
| `superseded` | Offered for `remove`. |
| `deprecated` | Offered for `remove`. |
| `review` | Shown for review; the user decides. |
| `system` | Provided by the operating system or distribution. Kept. |

Binaries follow their own rule: one that is missing and is `required` or `recommended` is offered for `install`, and one that is outdated is offered for `update`. `bootstrap --install` installs the same missing binaries.

An installed item that matches no entry is one of the user's own tools; see [personal-layer](personal-layer.md) and [loadout adopt](cli.md#loadout-adopt).

### `offer`

An entry with `offer` appears as a global add-on in `loadout configure show` and in the wizard. `offer` has these keys, and no others:

| Key | Meaning |
|---|---|
| `plugin` | A plugin id `name@marketplace`. The marketplace must be `claude-plugins-official` or declared in `settings.base.json`. |
| `mcp` | An object `{server name: server config}`. Switching the add-on on writes these servers into the personal `mcp.json`. Arguments must not use `@latest`. |
| `needs` | Environment variable names the servers use, for example `DATABASE_URL`. If one is unset, `configure set mcp` prints a note to add it to `secrets.env`. |

An add-on is addressed by its plugin id, or by the entry `id` or a server name for `mcp`: `loadout configure set mcp dbhub on`.

### `version`

| Key | Meaning |
|---|---|
| `cmd` | Required for a `binary`. The command that prints the installed version, for example `["serena", "--version"]`. |
| `github` | `owner/repo`. The latest release tag is the latest version. |
| `npm` | An npm package name. The registry's latest version is the latest version. It also gives the tool name for `mise` (`npm:<package>`). |
| `pypi` | A PyPI package name. |

Without `github`, `npm` or `pypi` the latest version is unknown, and the tool is never reported as outdated. Network failures also mean "unknown".

### `install` and `update`

Each is an object with the keys `posix` and `windows`. A value is a list of commands, and a command is a list of arguments:

```json
"update": { "posix": [["claude", "update"]], "windows": [["claude", "update"]] }
```

The key for the running system is `windows` on Windows and `posix` everywhere else. A platform without a key has no command. Without an `install` command, `loadout check` shows `manual` as the fix for a missing binary. Without an `update` command, `loadout update` prints `no update command for this platform` and `manual`.

`loadout update` prefers the package manager that owns the binary (mise, then Homebrew) over the `update` commands.

## Example

```json
{
  "id": "mcp-github-reference",
  "kind": "mcp",
  "status": "superseded",
  "by": "gh CLI",
  "match": { "names": ["github-server"], "contains": ["@modelcontextprotocol/server-github"] },
  "reason": "Archived reference server; the gh CLI is cheaper in context and well known to the model.",
  "short": "the gh CLI does this with less context"
}
```
