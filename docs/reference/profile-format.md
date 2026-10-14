# Profile format

A profile is a per-project preset: settings, MCP servers, plugins and commands for one kind of project. `loadout profile NAME` and `loadout init` apply it to the current repo. The code is `cli/loadout/profiles.py` and `cli/loadout/project.py`.

A profile is one JSON file `NAME.json`. Kit profiles live in `profiles/` in the kit: `thesis`, `web`, `db`, `sonar` and `android`. Your own live in `<personal layer>/profiles/`. See [personal-layer](personal-layer.md).

## Fields

Every field is optional; a missing field is empty. Kit profiles must have a `description` (a test checks it). The table says what each field does in Claude Code; what it does in Codex is in [In Codex](#in-codex).

| Field | Type | Meaning |
|---|---|---|
| `description` | string | One line. `loadout configure show` uses it as the reason for the plugins the profile installs. |
| `install` | list of plugin ids | Plugins to install at project scope with `claude plugin install ID --scope project`. Each id is `name@marketplace`; anything else is skipped with a message and `loadout profile` exits 1. With Claude Code off, this step is skipped. The marketplace of each id must be declared in `settings.base.json` for the kit's own profiles; a test checks this. |
| `settings` | object | Merged into the repo's `.claude/settings.json`. |
| `mcp` | object | Merged into the repo's `.mcp.json`. Usually `{"mcpServers": {...}}`. Pin versions: the kit's own profiles must not use `@latest`. |
| `commands` | list of commands | Commands run in the repo after the plugins, each a list of arguments, for example `["playwright-cli", "install", "--skills"]`. |
| `skills` | list of names | Skill folders copied into the repo's `.claude/skills/`. |
| `notes` | string | Printed after the profile is applied. |

Kit profiles use `description`, `settings`, `mcp`, `install`, `commands` and `notes`. A `skills` list is for personal profiles; the folders come from `profiles/skills/<name>/` (see below).

Example, the kit's `web` profile:

```json
{
  "description": "Web UI work: Playwright skills, Chrome DevTools MCP (off by default)",
  "mcp": {
    "mcpServers": {
      "chrome-devtools": { "type": "stdio", "command": "npx", "args": ["-y", "chrome-devtools-mcp@1.10.1"] }
    }
  },
  "settings": { "disabledMcpjsonServers": ["chrome-devtools"] },
  "commands": [["playwright-cli", "install", "--skills"]],
  "notes": "chrome-devtools is for performance/network debugging; enable it in /mcp when needed. ..."
}
```

## What applying a profile does

In this order:

1. `settings` is merged into `<repo>/.claude/settings.json`, and `mcp` into `<repo>/.mcp.json`. Dicts merge recursively, lists are joined without duplicates, and for any other value the profile wins. A file is written only when the result differs. A profile with an empty `settings` or `mcp` does not touch that file.
2. `skills` are copied. See below.
3. `install` and `commands` run, unless `--no-install` was given. A failing command prints `failed: ...` and the rest continues.
4. With Codex on, the Codex side is set up (see [In Codex](#in-codex)).
5. `notes` is printed.

The repo's `.claude/settings.json` and `.mcp.json` are normal project files that you commit. loadout makes no backup of them, and `loadout restore` does not undo them.

`loadout init --dry-run` prints the profile's description, the skills it would copy, the plugins and commands it would run and the files `init` would create, and changes nothing. It does not show the settings or `.mcp.json` diff.

When a step has a problem, the rest still runs, and the command ends with `profile NAME: applied with problems` and exit code 1 (the causes are listed under [loadout init](cli.md#loadout-init)).

### Skills

Each name in `skills` is looked up in `<personal layer>/profiles/skills/<name>/` first, then in `profiles/skills/<name>/` of the kit, and copied to `<repo>/.claude/skills/<name>/`, or with Codex only to `<repo>/.agents/skills/<name>/` ([ADR 0027](../adr/0027-repo-files-follow-the-agents.md)). The copy follows these rules:

- An existing folder or link of that name, in `.claude/skills` or `.agents/skills`, is never overwritten. The output says `exists, left as is`.
- A name that is not a plain folder name (it has a path separator, or is `.` or `..`) is skipped.
- If the folder it copies into (`.claude` or `.claude/skills`; with Codex only `.agents` or `.agents/skills`) is a link that leads outside the repo, nothing is copied.
- After the copy and the `commands`, every skill folder (or link to one) is linked into the skill folder of each other agent that is on: `.agents/skills/NAME -> ../../.claude/skills/NAME` for Codex, `.claude/skills/NAME -> ../../.agents/skills/NAME` for Claude Code. So a repo that started with Codex only gets its skills linked for Claude Code on the first `loadout profile` after you turn Claude Code on.
- Nothing is linked, and the output says why, when either skill folder is a link that leads outside the repo or the folder it links into is not a folder. A single skill that is a link leading outside the repo is not linked either, and reported.
- A name that is found nowhere is reported and skipped.

The copy is a snapshot. Later changes to the profile's skill do not reach the repo until you copy it again, and the copies in a repo can drift from the personal layer.

## In Codex

With Codex on ([Use loadout with Codex](../how-to/codex.md#switch-it-on)), `loadout init` and `loadout profile NAME` also set up Codex in the repo. Each field maps like this:

| Field | In Codex |
|---|---|
| `description`, `notes` | Same as for Claude Code. |
| `install` | Each plugin is installed with `codex plugin add` (not with `--no-install`; a plugin whose marketplace is not on GitHub has no Codex route and is reported). It is switched on for this repo only: `[plugins."NAME@MARKET"] enabled = true` in the repo's `.codex/config.toml`, and `enabled = false` in the user-level `~/.codex/config.toml`. loadout keeps that user-level switch off even after `codex plugin add` turns it on again. Two exceptions stay on everywhere: a plugin you had already installed in Codex, and one your merged settings enable globally (the kit's or your personal `enabledPlugins`). |
| `mcp` | Each server becomes a section in the repo's `.codex/config.toml`. loadout only adds sections: one you already have under that name stays and is reported. A server the profile lists in `settings.disabledMcpjsonServers` gets `enabled = false`. A server with `${VAR}` in its `command`, `args` or `url` (the `db` profile's DBHub) is skipped for Codex with the reason, because Codex does not expand variables there. |
| `settings` | Not used by Codex, except `disabledMcpjsonServers` (above) and `extraKnownMarketplaces` (where a plugin comes from). |
| `commands` | Run once, for both agents. |
| `skills` | Copied as above (into `.agents/skills/` with Codex only). With Codex on, every skill in the repo's `.claude/skills`, including ones a `commands` entry installed there, is linked into `.agents/skills` as `../../.claude/skills/NAME`. A different item already at that path stays and is reported. |

Codex reads a repo's `.codex/config.toml` only in a trusted project. Until then, loadout prints the step on every run: start `codex` in the repo once and accept the trust question. loadout never trusts a project for you. With Codex only, the Claude Code parts of a profile are not written: no `.claude/settings.json`, no `.mcp.json`, nothing in `.claude/skills`. loadout prints `Claude Code is off: FILE not written` for each file the profile would have written; turn Claude Code on and run `loadout profile NAME` again to add them ([ADR 0027](../adr/0027-repo-files-follow-the-agents.md)).

What `init` and `profile` write per agent is tabled in [the CLI reference](cli.md#loadout-profile).

## Personal and kit profiles

Both directories are searched, personal first. A personal profile with the name of a kit profile replaces the kit profile for you. Nothing is merged: the personal file is used as it is, and later changes to the kit profile do not reach you.

When `loadout adopt` or `loadout configure set own` records a tool into a personal profile whose name is a kit profile, and no personal file exists yet, it starts the personal file as a copy of the kit profile and prints a note. If neither exists, the file starts with the description `Personal profile NAME (made by loadout adopt)`.

A profile name (the file name without `.json`) must match `[a-z0-9][a-z0-9_-]*`: lowercase letters, digits, `-` and `_`. A file with another name is not listed and cannot be applied.

`loadout init` suggests profiles from the project's files:

| Profile | Suggested when |
|---|---|
| `sonar` | `sonar-project.properties` exists. |
| `android` | a `build.gradle*` file mentions `com.android`. |
| `web` | `package.json` depends on react, next, vue, svelte or astro. |
| `db` | `.env.example` defines `DATABASE_URL`. |
| `thesis` | a `.tex` or `.bib` file exists, or the folder name contains "thesis" or "paper". |

The detection is in `cli/loadout/detect.py`. It returns only these five names.
