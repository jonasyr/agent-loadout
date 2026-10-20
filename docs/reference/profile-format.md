# Profile format

A profile is a per-project preset: settings, MCP servers, plugins and commands for one kind of project. `loadout profile NAME` and `loadout init` apply it to the current repo. The code is in `cli/loadout/`: `profiles.py` and `project.py`, with `repo_merge.py` (the three-way merge), `repo_writes.py` (the plan), `repo_config.py` (`.loadout.json`) and, for Codex, `codex_project.py`.

A profile is one JSON file `NAME.json`. Kit profiles live in `profiles/` in the kit: `thesis`, `web`, `db`, `sonar` and `android`. Your own live in `<personal layer>/profiles/`. See [personal-layer](personal-layer.md).

## Fields

Every field is optional; a missing field is empty. Kit profiles must have a `description` and a `why` reason for each `settings` and `mcp` entry, and may use only the fields below except `skills` (a test checks this). The table says what each field does in Claude Code; what it does in Codex is in [In Codex](#in-codex).

| Field | Type | Meaning |
|---|---|---|
| `description` | string | One line. `loadout configure show` uses it as the reason for the plugins the profile installs. |
| `install` | list of plugin ids | Plugins to install at project scope with `claude plugin install ID --scope project`. Each id is `name@marketplace`; anything else is skipped with a message and `loadout profile` exits 1. This step is skipped when the repo is not for Claude Code, or when Claude Code is off for you. Only the second case gets a plan note (`plugin ID: …`); for a repo that is not for Claude Code the skipped installs are not named. For the kit's own profiles, the marketplace of each id must be `claude-plugins-official` or declared in `settings.base.json`; a test checks this. |
| `settings` | object | Merged (three-way, see below) into the repo's `.claude/settings.json` (when the repo is for Claude Code). |
| `mcp` | object | Merged (three-way, see below) into the repo's `.mcp.json` (when the repo is for Claude Code). Usually `{"mcpServers": {...}}`. Pin versions: the kit's own profiles must not use `@latest`. |
| `commands` | list of commands | Commands run in the repo after the plugins, each a list of arguments, for example `["playwright-cli", "install", "--skills"]`. |
| `skills` | list of names | Skill folders copied into the repo's `.claude/skills/`. |
| `notes` | string | Printed after the profile is applied. |
| `why` | object | One-line reasons for the plan, keyed by a top-level entry: `settings.KEY` or `mcp.KEY`, for example `{"mcp.mcpServers": "Chrome DevTools for performance and network debugging"}`. The plan's line for that file reads `profile NAME: <reason>`; without one it names the profile. |

Kit profiles use `description`, `settings`, `mcp`, `install`, `commands`, `notes` and `why`. A `skills` list is for personal profiles; the folders come from `profiles/skills/<name>/` (see below).

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
  "why": {
    "mcp.mcpServers": "Chrome DevTools for performance and network debugging",
    "settings.disabledMcpjsonServers": "keeps Chrome DevTools off until you enable it in /mcp"
  },
  "notes": "chrome-devtools is for performance/network debugging; enable it in /mcp when needed. ..."
}
```

## What applying a profile does

In this order:

1. `settings` is merged into `<repo>/.claude/settings.json`, and `mcp` into `<repo>/.mcp.json`. The merge is three-way against the profile's record in [`.loadout.json`](cli.md#loadoutjson) ([ADR 0031](../adr/0031-repo-profile-entries-merge-three-way.md)): a missing entry is added; a profile update applies when the file still has the value loadout wrote; a value someone changed stays (loadout asks once when the profile has a new one, and `--take-profile` takes it); a list entry someone removed stays removed; an entry the profile dropped is removed when it still has loadout's value and no other profile recorded it. Without a record (a repo from before this rule), only missing entries are added, and a different existing value is named in the plan. An MCP server's definition is one entry. `loadout explain <file>` shows which entries are loadout's. A file is written only when the result differs, and only in the layout it already has (see [Repo writes](cli.md#repo-writes)). A profile with an empty `settings` or `mcp` does not touch that file, unless its record holds entries there (then the dropped entries are removed as above). The agents come from the repo's [`.loadout.json`](cli.md#loadoutjson); these two files are written only when it names Claude Code (or, without the file, when Claude Code is on for you).
2. `skills` are copied. See below.
3. `install` and `commands` run, unless `--no-install` was given. A failing command prints `failed: ...` and the rest continues.
4. When the repo is for Codex, the Codex side is set up (see [In Codex](#in-codex)).
5. `notes` is printed.

The repo's `.claude/settings.json` and `.mcp.json` are normal project files that you commit. Before it writes them, loadout shows the plan and asks, and the run's backup holds a copy of each changed file and a record of each created one, so `loadout restore` undoes the file changes ([Repo writes](cli.md#repo-writes)). It does not undo `commands`.

`--dry-run` (on `init` and on `profile`) prints the plan, including the settings and `.mcp.json` changes, and changes nothing.

When a step has a problem, the rest still runs, and the command ends with `Profile NAME: applied with problems (below)` (`Init: …` for init) and exit code 1 (the causes are listed under [loadout init](cli.md#loadout-init)).

### Skills

Each name in `skills` is looked up in `<personal layer>/profiles/skills/<name>/` first, then in `profiles/skills/<name>/` of the kit, and copied to `<repo>/.claude/skills/<name>/`, or when the repo is for Codex only to `<repo>/.agents/skills/<name>/` ([ADR 0027](../adr/0027-repo-files-follow-the-agents.md), [ADR 0030](../adr/0030-repo-files-follow-the-repos-agents.md)). The copy follows these rules:

- An existing folder or link of that name, in `.claude/skills` or `.agents/skills`, is never overwritten. The output says `exists, left as is`.
- A name that is not a plain folder name (it has a path separator, or is `.` or `..`) is skipped.
- If the folder it copies into (`.claude` or `.claude/skills`; for a Codex-only repo `.agents` or `.agents/skills`) is a link that leads outside the repo, nothing is copied.
- After the copy and the `commands`, every skill folder (or link to one) is linked into the skill folder of each other agent the repo is for: `.agents/skills/NAME -> ../../.claude/skills/NAME` for Codex, `.claude/skills/NAME -> ../../.agents/skills/NAME` for Claude Code. So a repo that started with Codex only gets its skills linked for Claude Code on the first `loadout profile` after Claude Code is added to the repo's agents (`loadout init --agents claude,codex`).
- Nothing is linked, and the output says why, when either skill folder is a link that leads outside the repo, or the folder it links into (or its `.claude` / `.agents` parent) is a link or not a folder. A single skill that is a link leading outside the repo is not linked either, and reported. An existing link that is not loadout's relative link (an absolute one, say) stays and is reported, because it would be dangling in other clones.
- A name that is found nowhere is reported and skipped.

The copy is a snapshot. Later changes to the profile's skill do not reach the repo until you copy it again, and the copies in a repo can drift from the personal layer.

## In Codex

When the repo is for Codex, `loadout init` and `loadout profile NAME` also set up Codex in the repo. The repo's agents come from [`.loadout.json`](cli.md#loadoutjson); without that file, Codex must be on for you ([Use loadout with Codex](../how-to/codex.md#switch-it-on)). The plugin installs below run only when Codex is also on for you. loadout only adds tables to `.codex/config.toml`; it records them in `.loadout.json`, so a table or plugin switch someone removed is not added back, and a newer table in the profile is named in the plan instead of written. Each field maps like this:

| Field | In Codex |
|---|---|
| `description`, `notes` | Same as for Claude Code. |
| `install` | Each plugin is installed with `codex plugin add` (not with `--no-install`; a plugin whose marketplace is not on GitHub has no Codex route and is reported). It is switched on for this repo only: `[plugins."NAME@MARKET"] enabled = true` in the repo's `.codex/config.toml`, and `enabled = false` in the user-level `~/.codex/config.toml`. loadout keeps that user-level switch off even after `codex plugin add` turns it on again. Two exceptions stay on everywhere: a plugin you had already installed in Codex, and one your merged settings enable globally (the kit's or your personal `enabledPlugins`). |
| `mcp` | Each server becomes a section in the repo's `.codex/config.toml`. loadout only adds sections: one you already have under that name stays and is reported. A server the profile lists in `settings.disabledMcpjsonServers` gets `enabled = false`. A server with `${VAR}` in its `command`, `args` or `url` (the `db` profile's DBHub) is skipped for Codex with the reason, because Codex does not expand variables there. |
| `settings` | Not used by Codex, except `disabledMcpjsonServers` (above) and `extraKnownMarketplaces` (where a plugin comes from). |
| `commands` | Run once, for both agents. |
| `skills` | Copied as above (into `.agents/skills/` for a Codex-only repo). When the repo is for Codex, every skill in the repo's `.claude/skills`, including ones a `commands` entry installed there, is linked into `.agents/skills` as `../../.claude/skills/NAME`. A different item already at that path stays and is reported. |

Codex reads a repo's `.codex/config.toml` only in a trusted project. Until then, loadout prints the step on every run: start `codex` in the repo once and accept the trust question. loadout never trusts a project for you.

With only VS Code's Codex extension and no Codex CLI (extension mode), the `install` step installs no Codex plugins and prints the note `VS Code's Codex extension loads no plugins; the profile's Codex plugins are not set` (a note, not a problem: the run still writes the profile's other files and exits 0); the repo's `.codex/config.toml` does not name the plugins. The extension would not load them anyway. The trust step above also names the Codex CLI. Recommended: the Codex CLI next to the extension (`loadout bootstrap --install`), then run `codex` in the repo from VS Code's terminal for the trust question ([The Codex CLI alongside VS Code](../how-to/vscode.md#the-codex-cli-alongside-vs-code)). In a repo that is for Codex only, the Claude Code parts of a profile are not written: no `.claude/settings.json`, no `.mcp.json`, nothing in `.claude/skills`. The plan names each file the profile would have written and why it was left out, and one line names the profile's plugins that are not installed for Claude Code (`skipped for this repo (not for Claude Code): plugin a@m, …`); add Claude Code with `loadout init --agents claude,codex` and run `loadout profile NAME` again to add them ([ADR 0030](../adr/0030-repo-files-follow-the-repos-agents.md)).

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
