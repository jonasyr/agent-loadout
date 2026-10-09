# Adopt: decide what happens to your own tools

Status: approved design (2026-10-10). Extends spec `2026-10-08-agent-loadout-design.md` §3.2, §6.2 and §6.4.

## 1. Problem

`inventory.classify` marks every plugin, MCP server, skill, hook or marketplace that is not in the catalog as `unknown`. `adopt.select` only offers to remove those (default: none). An item that is kept stays on that one machine, unmanaged: it is not in the personal layer, so it is not reproduced on another machine and cannot be made project-scoped. Only catalog entries with `status: profile` get `scope-down`.

Found while validating the design against the code:

- **G1:** `bootstrap.setup_plugins` (installs personal `enabledPlugins` / `extraKnownMarketplaces`) runs only from `bootstrap` and `configure.apply_all`, not after the daily pull. A plugin recorded on machine A is enabled in settings on machine B after the pull but never installed there.
- **G2:** `personal_mcp.apply_mcp` skips a server whose name exists in `~/.claude.json` but not in `managed-mcp.json` unless the config is identical. Recording a server in `<personal>/mcp.json` with a different (secret-rewritten) config would be skipped as "not managed".
- **G3:** `classify` labels personal-layer plugins "Enabled by the kit." and has no check for personal `mcp.json` servers, so those show as `unknown` and adopt offers to remove them.
- **G4:** spec §6.2 says unknown items are "kept untouched"; `GROUP_HELP["unknown"]` says "picking removes it"; README lines 29, 81 and 205 describe adopt without the new choices.

## 2. Goal

For each of the user's own items, adopt (and later `loadout configure`) asks one of:

| Choice | Meaning |
|---|---|
| **[g]lobal** | Record it in the personal layer so it follows the user to every machine. |
| **[p]roject** | Disable it globally and write it into a personal profile; offer to apply that profile to repos. |
| **[l]eave** | Stay as is, machine-only and unmanaged; not asked again on this machine. |
| **[r]emove** | Remove it, restorable (today's behaviour). |

Default everywhere is **leave**: `--yes`, non-interactive runs and an empty answer change nothing (the user's ask-before-removing rule).

Catalog `scope-down` items gain an explicit "keep global" answer (interactive pick), which is the same as **global** for that plugin.

## 3. Architecture

| Unit | Change |
|---|---|
| `inventory.classify` | Personal-layer aware: plugins/marketplaces from personal `settings.json`, servers from personal `mcp.json`, skills/hooks linked from the personal layer, and items listed in a personal profile while disabled globally → `keep`, reason "from your personal layer". Items in `own-decisions.json` → `keep`, reason "left on this machine". The action `unknown` is renamed `own`. Fixes G3. |
| `own.py` (new) | `unmanaged(verdicts)`, `record_global(item, bk)`, `record_project(item, profile, bk)` (dispatch per kind), `remember_leave(item)`, `parse_spec("a=global,b=project:x,c=leave,d=remove")`, `candidate_repos(item)`. |
| `secrets.py` | Factor the `${VAR}` rewrite out of `adopt.fix_secrets` into a function that returns the rewritten config and the new `secrets.env` lines, so `fix_secrets` and `own` share it. |
| `link.py` | `LINKS()` adds one link per `<personal>/skills/<name>` → `~/.claude/skills/<name>`, per entry of `<personal>/skills.json` whose target exists, and `<personal>/hooks` → `~/.claude/hooks/personal`. All go through `_link_one` (copy mode on Windows included). |
| `profiles.py` | New `skills: [name, ...]` field. `apply_profile` copies `<personal>/skills/<name>/` into `<project>/.claude/skills/<name>/`; an existing destination is never overwritten (reported instead). |
| `maintenance._maintain` | After a pull that changed something, also run `bootstrap.setup_plugins()` (installs only missing items) and notify each line. Fixes G1. |
| `adopt.py` | Group `YOUR OWN TOOLS` replaces `UNKNOWN`; prompt "[l]eave all / [c]hoose each"; per-item four-way prompt; `--own SPEC`; "keep global" for picked scope-down items; at the end, offer to apply new or changed profiles to repos. |
| `configure.py` / `commands.py` | `loadout configure own [--all]` lists unmanaged items (with `--all`, also the ones left on this machine); `loadout configure set own NAME CHOICE` applies one choice. Used by `/loadout:configure`. |
| `check.py` | One `warn` line: "N tools are not managed by loadout → `loadout configure own`" (left items not counted). |

### Personal layer additions

```
personal/
├── settings.json    + enabledPlugins / extraKnownMarketplaces / hooks for global items
├── mcp.json         + global MCP servers (secrets as ${VAR})
├── skills/<name>/   global skills (moved here, linked back)
├── skills.json      {"<name>": "<target>"} for skills that are symlinks to a shared source
├── hooks/<file>     scripts used by global or project hooks (linked as ~/.claude/hooks/personal)
└── profiles/*.json  + personal profiles created by "project" (may contain "skills")
```

Machine-local: `~/.claude/.loadout/own-decisions.json` → `{"<kind>:<name>": "leave"}`.

## 4. Data flow per choice

| Kind | Global: personal layer | Global: this machine | Project: profile gets | Project: this machine |
|---|---|---|---|---|
| plugin | `settings.json` `enabledPlugins[id]=true`; the marketplace's source into `extraKnownMarketplaces` unless the kit declares it | unchanged | `install`, `settings.enabledPlugins`, and `settings.extraKnownMarketplaces` if needed | `claude plugin disable <id> --scope user` (undo recorded) |
| marketplace | `extraKnownMarketplaces[name]` from its `source` | unchanged | — (project not offered) | — |
| MCP server | `mcp.json`: config with secrets rewritten to `${VAR}` (values appended to `secrets.env`) | same `${VAR}` config re-added to `~/.claude.json` user scope; the server is added to `managed-mcp.json` (fixes G2) | `mcp.mcpServers[name]` (with `${VAR}`) | removed from user scope (undo recorded) |
| skill (directory) | moved to `skills/<name>/` | `~/.claude/skills/<name>` becomes a link to it (original into the backup) | moved to `skills/<name>/`, `skills: [name]` | `~/.claude/skills/<name>` into the backup |
| skill (symlink to a shared source, e.g. `/usr/share/omarchy/...`) | pointer in `skills.json` | unchanged (already linked) | — (project not offered) | — |
| hook | `settings.json` `hooks` entry; a referenced script is moved to `hooks/` and the command rewritten | the `~/.claude/settings.json` hook rewritten to the same command, so the merge does not duplicate it | `settings.hooks` entry (script handled the same way) | hook removed from `~/.claude/settings.json` |

**Hook scripts.** A command token that resolves to an existing regular file under `$HOME` (outside the kit and the personal layer) is a local script: it is moved to `<personal>/hooks/<file>` and the token becomes `"$HOME/.claude/hooks/personal/<file>"`. A name clash with a different file in `hooks/` is a collision (§5). Commands without such a token (`rtk hook claude`, `npx ...`) are recorded as is. A token pointing outside `$HOME` is recorded as is with a warning that it depends on that machine.

**Profile names.** The prompt offers existing personal profiles; the default is the last name used in this run. A name that matches a kit profile (for example `db`) creates a personal profile that starts as a copy of the kit one, because a personal profile replaces a kit profile of the same name; the prompt says so.

**Applying the profile to repos.** After apply, for each profile that was created or changed: candidates are existing directories among `~/.claude.json` `projects` whose project MCP servers, `.mcp.json` or `.claude/settings*.json` mention the item name. The user confirms the list (empty = candidates, `-` = none) or types paths; each gets `project.add_profile(path, name)`. Detection is only a hint. Non-interactive runs and `--own` never apply profiles to repos.

**Committing the personal layer.** Afterwards, reuse the commit-and-push offer from `configure.apply_all` (it refuses when an `.env` file would be committed). Uncommitted changes already pause the daily sync and `loadout check` already warns about it.

**Interactive prompt.**

```
YOUR OWN TOOLS (3) — not managed by loadout; they stay only on this machine unless you choose.
  [plugin] foo@bar  1.2.0
  [mcp]    my-db    npx -y my-db-mcp
  [skill]  notes    ~/.claude/skills/notes

your own tools: [l]eave all / [c]hoose each (default leave): c
  plugin foo@bar — [g]lobal / [p]roject / [l]eave / [r]emove (default l): g
  mcp my-db     — [g]lobal / [p]roject / [l]eave / [r]emove (default l): p
    profile (existing: android, db, sonar, thesis, web; or a new name) [db]: mydb
  skill notes   — [g]lobal / [p]roject / [l]eave / [r]emove (default l): l
Apply 2 change(s)? [y/N]
```

Choices that do not apply to an item (project for a marketplace or a shared-source skill) are left out of its prompt.

**Non-interactive.** `loadout adopt --apply --own "foo@bar=global,my-db=project:mydb,notes=leave"`. Items not named stay untouched. `--own` works with or without `--yes`; `--yes` alone leaves own tools alone. `loadout configure set own NAME CHOICE` takes the same `CHOICE` syntax (`global`, `project:<profile>`, `leave`, `remove`). If a name matches items of more than one kind, it must be qualified as `<kind>:<name>`.

## 5. Errors, undo, safety

- **Order:** each choice writes the personal layer first, then changes the machine. If the machine step fails, the personal-layer change stays (harmless, visible in `git status`) and the item is reported as "recorded, not active here yet: <reason>". MCP changes follow the existing rule: try to re-add the original, never leave the user without the server.
- **Backup:** one `Backup("adopt")` for the whole run. Changed files are saved with `save_copy` first, new personal-layer files are recorded with `record_created`, moved skills and scripts go through `move`, and CLI changes are recorded with `record_command`. `loadout restore` replays everything.
- **Collisions are never overwritten:** a personal `mcp.json` server with the same name and a different config, an existing `<personal>/skills/<name>` or `hooks/<file>` with different content, or a profile that already lists the item differently → "skipped: <name> already exists in <file> with a different config"; the item is untouched.
- **Windows `.cmd` shim:** when `runner.would_refuse` says `claude` cannot take the JSON argument, write the manual commands file as `_apply_mcp` does and remove nothing.
- **Secrets:** every printed line is redacted. `secrets.env` is created 0600 via the existing helper. A secret that cannot be fixed automatically (newline in the value, URL query string) blocks global and project for that server: "move the secret by hand first".
- **Validation first:** an unknown name or choice in `--own` or `set own` exits with code 2 before anything changes.
- **Idempotent:** a second run classifies recorded items as `keep` and asks nothing.

## 6. Known limits (to document for users)

- An MCP server is managed by loadout only if it is in `managed-mcp.json` or its config in `~/.claude.json` is identical to the personal one; otherwise `apply_mcp` leaves the user's server alone (G2). Recording through adopt seeds `managed-mcp.json`.
- New personal-layer plugins are installed on other machines by the daily pull (G1 fix), so the daily pull now also downloads plugins from marketplaces the user added. `LOADOUT_NO_AUTO_PULL=1` disables it.
- A profile is copied into a repo when applied; later changes to the personal profile do not reach repos until it is applied again. Skill copies in a repo can drift from the personal layer.
- A skill recorded as a pointer to a shared source is linked only on machines where that source exists.
- A hook whose command points outside `$HOME` is recorded as is and only works where that path exists.

## 7. Tests

All with a temp `HOME`, `LOADOUT_PERSONAL` on a temp copy and `fake_runner`; no real installers or `claude` mutations.

- Each kind × {global, project, leave, remove}, including backup entries and `restore` undoing them.
- MCP global: secrets rewritten, `managed-mcp.json` seeded, a following `apply_mcp()` reports no change.
- Hook global: local script moved and path rewritten; outside-`$HOME` path warns; plain command unchanged; no duplicate after `apply_settings`.
- Skill: directory moved and linked (and copy mode); shared-source symlink becomes a pointer; profile `skills` copied into a repo and never overwrites.
- Profile name equal to a kit profile: personal copy starts from the kit profile.
- Collisions skip; `.cmd` shim path removes nothing; unfixable secret blocks global/project.
- `classify`: personal-layer items are `keep`; left items are `keep`; G3 regression.
- Defaults: `--yes` and non-interactive leave everything; `--own` parse and validation errors; ambiguous name needs `<kind>:`.
- Idempotent re-run asks nothing.
- `maintenance`: `setup_plugins` runs only after a pull that changed something.
- `check` line; `configure own [--all]`; `configure set own`.
- Eval: extend the `/loadout:configure` eval with a case where it offers the four choices for an unmanaged item (fixture, stubbed runner).

## 8. Docs

- Main spec: §3.2 (new personal-layer files), §6.2 (action `own` replaces `unknown`; four choices; defaults; personal-layer items are `keep`), §6.4 (`configure own`, `set own`).
- README: lines 29, 81 and 205; a "Your own tools" section; known limits from §6 under the existing troubleshooting/trust sections.
- `GROUP_HELP`, the onboard and configure SKILL.md texts.
- The Diátaxis restructure is not part of this change (repo-polish step).

## 9. Out of scope

- Syncing machine-local "leave" decisions across machines.
- Updating repos that already have a profile applied when the personal profile changes.
- Hooks configured in project settings files (adopt only looks at user scope).
