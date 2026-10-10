# Profile format

A profile is a per-project preset: settings, MCP servers, plugins and commands for one kind of project. `loadout profile NAME` and `loadout init` apply it to the current repo. The code is `cli/loadout/profiles.py` and `cli/loadout/project.py`.

A profile is one JSON file `NAME.json`. Kit profiles live in `profiles/` in the kit: `thesis`, `web`, `db`, `sonar` and `android`. Your own live in `<personal layer>/profiles/`. See [personal-layer](personal-layer.md).

## Fields

Only `description` is required. Missing fields are empty.

| Field | Type | Meaning |
|---|---|---|
| `description` | string | One line. `loadout configure show` uses it as the reason for the plugins the profile installs. |
| `install` | list of plugin ids | Plugins to install at project scope with `claude plugin install ID --scope project`. The marketplace of each id must be declared in `settings.base.json` for the kit's own profiles; a test checks this. |
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
4. `notes` is printed.

The repo's `.claude/settings.json` and `.mcp.json` are normal project files that you commit. `loadout restore` does not undo them.

`loadout init --dry-run` prints what would change and changes nothing.

### Skills

Each name in `skills` is looked up in `<personal layer>/profiles/skills/<name>/` first, then in `profiles/skills/<name>/` of the kit, and copied to `<repo>/.claude/skills/<name>/`. The copy follows these rules:

- An existing folder or link of that name is never overwritten. The output says `exists, left as is`.
- A name that is not a plain folder name (it has a path separator, or is `.` or `..`) is skipped.
- If `.claude` or `.claude/skills` is a link that leads outside the repo, nothing is copied.
- A name that is found nowhere is reported and skipped.

The copy is a snapshot. Later changes to the profile's skill do not reach the repo until you copy it again, and the copies in a repo can drift from the personal layer.

## Personal and kit profiles

Both directories are searched, personal first. A personal profile with the name of a kit profile replaces the kit profile for you. Nothing is merged: the personal file is used as it is, and later changes to the kit profile do not reach you.

When `loadout adopt` or `loadout configure set own` records a tool into a personal profile whose name is a kit profile, and no personal file exists yet, it starts the personal file as a copy of the kit profile and prints a note. If neither exists, the file starts with the description `Personal profile NAME (made by loadout adopt)`.

A profile name chosen through `project:<profile>` must match `[a-z0-9][a-z0-9_-]*`.

`loadout init` suggests profiles from the project's files:

| Profile | Suggested when |
|---|---|
| `sonar` | `sonar-project.properties` exists. |
| `android` | a `build.gradle*` file mentions `com.android`. |
| `web` | `package.json` depends on react, next, vue, svelte or astro. |
| `db` | `.env.example` defines `DATABASE_URL`. |
| `thesis` | a `.tex` or `.bib` file exists, or the folder name contains "thesis" or "paper". |

The detection is in `cli/loadout/detect.py`. It returns only these five names.
