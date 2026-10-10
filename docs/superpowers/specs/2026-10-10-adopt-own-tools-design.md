# Adopt: decide what happens to your own tools

Status: approved design (2026-10-10). Extends spec `2026-10-08-agent-loadout-design.md` §3.2, §6.2 and §6.4.

## 1. Problem

`inventory.classify` marks every plugin, MCP server, skill, hook or marketplace that is not in the catalog as `unknown`. `adopt.select` only offers to remove those (default: none). An item that is kept stays on that one machine, unmanaged: it is not in the personal layer, so it is not reproduced on another machine and cannot be made project-scoped. Only catalog entries with `status: profile` get `scope-down`.

Found while validating the design against the code:

- **G1 (resolved by Claude Code, document only):** `bootstrap.setup_plugins` runs only from `bootstrap` and `configure.apply_all`, not after the daily pull. This is not a gap: for user settings, "a marketplace that settings declare but `known_marketplaces.json` lacks: Claude Code clones it, then reloads plugins and downloads enabled plugins that aren't cached yet" (code.claude.com/docs/en/plugins/loading). After the daily pull merges the personal layer into `~/.claude/settings.json`, Claude Code installs new plugins at its next start (in the background; active after `/reload-plugins` or a new session). Decision 2026-10-10: no maintenance change; document the behaviour.
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

Default everywhere is **decide later**: `--yes`, non-interactive runs, an empty answer and three invalid answers change nothing and remember nothing. Only an explicit `l`/leave is remembered. (The user's ask-before-removing rule.)

Catalog `scope-down` plugins gain an explicit "keep global" answer (interactive pick), which is the same as **global** for that plugin.

## 3. Architecture

| Unit | Change |
|---|---|
| `inventory.classify` | Personal-layer aware: plugins/marketplaces from personal `settings.json`, servers from personal `mcp.json`, skills/hooks linked from the personal layer, and items listed in a personal profile while disabled globally → `keep`, reason "from your personal layer". Items in `own-decisions.json` → `keep`, reason "left on this machine". The action `unknown` is renamed `own`. Fixes G3. |
| `own.py` (new) | `unmanaged(verdicts)`, `record_global(item, bk)`, `record_project(item, profile, bk)` (dispatch per kind), `remember_leave(item)`, `parse_spec("a=global,b=project:x,c=leave,d=remove")`, `candidate_repos(item)`. |
| `secrets.py` | Factor the `${VAR}` rewrite out of `adopt.fix_secrets` into a function that returns the rewritten config and the new `secrets.env` lines, so `fix_secrets` and `own` share it. |
| `link.py` | `LINKS()` adds one link per `<personal>/skills/<name>` → `~/.claude/skills/<name>`, per entry of `<personal>/skills.json` whose target exists, and `<personal>/hooks` → `~/.claude/hooks/personal`. All go through `_link_one` (copy mode on Windows included). |
| `profiles.py` | New `skills: [name, ...]` field. `copy_skills` copies `<profiles dir>/skills/<name>/` (personal first, then kit) into `<project>/.claude/skills/<name>/`; an existing destination is never overwritten (reported instead). |
| `adopt.py` | Group `YOUR OWN TOOLS` replaces `UNKNOWN`; prompt "[l]eave all / [c]hoose each"; per-item four-way prompt; `--own SPEC` (`--groups own` is refused); "keep global" for picked scope-down items; at the end, offer to apply new or changed profiles to repos (default none). |
| `configure.py` / `commands.py` | `loadout configure own [--all]` lists unmanaged items (with `--all`, also the ones left on this machine); `loadout configure set own NAME CHOICE` applies one choice. Used by `/loadout:configure`. |
| `check.py` | One `warn` line named `own tools`: "N tool(s) not managed by loadout (they stay on this machine only)", fix "decide with `loadout adopt --apply` or `loadout configure own`" (left items not counted). A broken JSON file gives a `warn` whose fix names the file. |

### Personal layer additions

```
personal/
├── settings.json    + enabledPlugins / extraKnownMarketplaces / hooks for global items
├── mcp.json         + global MCP servers (secrets as ${VAR})
├── skills/<name>/   global skills (moved here, linked back to ~/.claude/skills/<name>)
├── skills.json      {"<name>": "<target>"} for skills that are symlinks to a shared source
├── hooks/<file>     scripts used by global or project hooks (linked as ~/.claude/hooks/personal)
├── profiles/*.json  + personal profiles created by "project" (may contain "skills")
└── profiles/skills/<name>/  skills used by profiles (not linked globally)
```

Machine-local: `~/.claude/.loadout/own-decisions.json` → `{"<key>": "leave"}`. The key is `<kind>:<name>`, with two exceptions: a hook is `hook:<Event>:<matcher>:<first 16 hex of sha256(command)>`, so the file never holds a command line, and an MCP server in `~/.claude/.mcp.json` is `mcp:.mcp.json:<name>`, because it is a different item from a user-scope server of the same name. Older keys (the raw command, plain `mcp:<name>`) are still read.

## 4. Data flow per choice

| Kind | Global: personal layer | Global: this machine | Project: profile gets | Project: this machine |
|---|---|---|---|---|
| plugin | `settings.json` `enabledPlugins[id]=true`; the marketplace's source into `extraKnownMarketplaces` unless the kit declares it | unchanged | `install`, `settings.enabledPlugins`, and `settings.extraKnownMarketplaces` if needed | `claude plugin disable <id> --scope user` (undo recorded) |
| marketplace | `extraKnownMarketplaces[name]` from its `source` | unchanged | — (project not offered) | — |
| MCP server | `mcp.json`: config with secrets rewritten to `${VAR}` (values appended to `secrets.env`) | same `${VAR}` config re-added to `~/.claude.json` user scope; the server is added to `managed-mcp.json` (fixes G2) | `mcp.mcpServers[name]` (with `${VAR}`) | removed from user scope (undo recorded) |
| skill (directory) | copied to `skills/<name>/` | `~/.claude/skills/<name>` into the backup, replaced by a link to the copy | copied to `profiles/skills/<name>/`, `skills: [name]` | `~/.claude/skills/<name>` into the backup |
| skill (symlink to a shared source, e.g. `/usr/share/omarchy/...`) | pointer in `skills.json` | unchanged (already linked) | — (project not offered) | — |
| hook | `settings.json` `hooks`: a group `{matcher, hooks: [hook]}`; a referenced script is copied to `hooks/` and the command rewritten | the hook is taken out of its group in `~/.claude/settings.json` and added back as exactly that group, which is then recorded in `managed-settings.json` (backed up first): it does not run twice, and removing it from the personal layer later removes it on this machine too | `settings.hooks` group (script handled the same way) | hook removed from `~/.claude/settings.json` |

**Hook names.** A hook is named `<Event>:<matcher>` as `loadout configure own` lists it (`Stop:` when there is no matcher; result lines read `hook Stop (no matcher)`). When several hooks share a name, each gets `#n` (1-based, in the order `configure own --all` lists them), and `--own` / `set own` then require it.

**Hook scripts.** Only a simple command of the form `<interpreter> <script> args` gets its script copied. The script is the first token, or the first token after `env` and a known interpreter with its flags. It must be an existing regular file under `$HOME` (outside the kit and the personal layer) that has a script extension, is executable or starts with `#!`. It is copied to `<personal>/hooks/<file>` (the original stays in place; other hooks may use it) and the token becomes `"$HOME/.claude/hooks/personal/<file>"`. Hook commands run through `sh -c` (Git Bash or PowerShell on Windows), so `$HOME` expands (code.claude.com/docs/en/hooks). Only that one file is copied, not files next to it. A name clash with a different file in `hooks/` is a collision (§5). A complex shell command (metacharacters outside the script path), a hook in exec form (with `args`, which runs without a shell) and a command without such a token (`rtk hook claude`, `npx ...`) are recorded as is. A path outside `$HOME` is recorded as is with a note that it works only where it exists; files under `/usr`, `/bin`, `/sbin`, `/opt/homebrew` and `/usr/local` (interpreters) give no note. Any hook that refers to a private file (§5) anywhere in its command or args is refused.

**Profile names.** The prompt offers existing personal profiles; the default is the last name used in this run. Without a previous name it ends with `; Enter: skip`, and Enter skips the item. A name that matches a kit profile (for example `db`) creates a personal profile that starts as a copy of the kit one, because a personal profile replaces a kit profile of the same name; the prompt says so.

**Applying the profile to repos.** After apply, for each profile that was created or changed: candidates are existing directories among `~/.claude.json` `projects` whose project MCP servers, `.mcp.json` or `.claude/settings.json` (not `settings.local.json`) mention the item name. The default is none: the user answers `y` to take the candidates, or types paths; each gets `project.add_profile(path, name)`, which is the same as `loadout profile` and is not undone by `loadout restore`. Detection is only a hint. Non-interactive runs and `--own` never apply profiles to repos.

**Committing the personal layer.** `global` and `project` choices reach other machines only when the personal layer is a git repo and the user commits and pushes. Interactive adopt reuses the commit-and-push offer from `configure.apply_all`: it prints the changes (`git status --porcelain`, the `--short` layout) and refuses without asking when a private file or an `.env` file would be committed. After `--own` or `configure set own` nothing is committed; the user (or `/loadout:configure`, with a yes) runs `git add -A`, `git commit` and `git push` in the personal layer. Uncommitted changes already pause the daily sync and `loadout check` already warns about it.

**Second machine.** After the daily pull, maintenance merges the settings and applies `mcp.json`, then `link.link_all` links the pulled skills and hook scripts (`~/.claude/skills/<name>`, `~/.claude/hooks/personal`). Plugins install at the next Claude Code start (G1).

**Interactive prompt.**

```
YOUR OWN TOOLS (3) — not managed by loadout; they stay only on this machine unless you choose.
  [plugin] foo@bar  1.2.0
  [mcp]    my-db    npx -y my-db-mcp
  [skill]  notes    ~/.claude/skills/notes

your own tools: [l]eave all (not asked again on this machine) / [c]hoose each (Enter: decide later): c
  global = personal layer, every machine · project = personal profile, per repo · leave = this machine only, not asked again · remove = into the backup (loadout restore)
  plugin foo@bar — [g]lobal / [p]roject / [l]eave / [r]emove (Enter: decide later): g
  mcp my-db — [g]lobal / [p]roject / [l]eave / [r]emove (Enter: decide later): p
    profile (existing: android, db, sonar, thesis, web; or a new name; Enter: skip): mydb
  skill notes — [g]lobal / [p]roject / [l]eave / [r]emove (Enter: decide later): l
Apply 2 change(s)? [y/N]
```

An empty answer, or three invalid answers for one item, skips that item (not decided, not remembered); an unrecognised answer to the first question decides nothing for all items. Once a profile was named, the next profile prompt shows it as the default (`[mydb]`). Choices that do not apply to an item are left out of its prompt: project for a marketplace or a shared-source skill; global and project for a server in `~/.claude/.mcp.json` (only user-scope servers in `~/.claude.json` can be recorded).

**Non-interactive.** `loadout adopt --apply --own "foo@bar=global,my-db=project:mydb,notes=leave"`. Items not named stay untouched. `--own` works with or without `--yes`; `--yes` alone leaves own tools alone. `--groups own` is an error (exit 1): own tools are decided per item with `--own`. `loadout configure set own NAME CHOICE` takes the same `CHOICE` syntax (`global`, `project:<profile>`, `leave`, `remove`). If a name matches items of more than one kind, it must be qualified as `<kind>:<name>`; a hook name shared by several hooks as `Event:matcher#n`. A name listed twice, an unknown name or a bad choice is an error (exit 2). Catalog scope-down plugins accept only `global`. A hook name that contains `,` cannot be given (the spec splits on commas); the error says to use `loadout adopt --apply` in a terminal.

## 5. Errors, undo, safety

- **Order:** each choice writes the personal layer first, then changes the machine. If the machine step fails, the personal-layer change stays (harmless, visible in `git status`) and the item is reported as `<kind> <name>: failed: <reason>` (`skipped: <reason>` when nothing was recorded), and one item's I/O error never stops the others. `loadout configure set own` and `loadout adopt --apply --own` then exit 1 when an item was not recorded, or recorded but not active on this machine (see the `skipped:`/`failed:` line); a removal that did not happen (`skipped (...)`, `not removed`) counts too. `adopt.apply_own` reports these items in its `not_done` list, so the exit code does not depend on the wording. A failed removal leaves the item listed under own tools next time. MCP changes follow the existing rule: try to re-add the original, never leave the user without the server.
- **Backup:** one `Backup("adopt")` for the whole run. Changed files are saved with `save_copy` first (also `managed-settings.json`, the snapshot of the last settings merge, and `own-decisions.json` when a decision is dropped), new personal-layer files are recorded with `record_created`, moved skills and scripts go through `move`, and CLI changes are recorded with `record_command`. `loadout restore` replays everything.
- **Collisions are never overwritten:** a personal `mcp.json` server with the same name and a different config, an existing `<personal>/skills/<name>` or `hooks/<file>` with different content, or a profile that already lists the item differently → "skipped: <name> already exists in <file> with a different config"; the item is untouched.
- **Windows `.cmd` shim:** when `runner.would_refuse` says `claude` cannot take the JSON argument, write the manual commands file as `_apply_mcp` does and remove nothing.
- **Secrets:** nothing that looks like a secret is written to the personal layer. Every printed line is redacted. `secrets.env` is created 0600 via the existing helper.
  - MCP: `env` and `headers` values become `${VAR}`. A secret in `args`, in the URL (query string or a high-entropy path segment) or in a multi-line value is refused ("move it by hand first"), because it cannot be moved safely.
  - Marketplace sources with credentials or a token in the URL are refused.
  - Hooks (command, args, script) and skill files that still look secret are refused ("move it to secrets.env and use ${VAR}, then try again"). All skill files are scanned, binary ones by their text runs; a file with a UTF-16 BOM or mostly NUL bytes is scanned both as UTF-16 and as UTF-8 (NULs as line breaks); an unreadable file refuses.
  - Private files are refused: a skill containing one, a hook naming one. The denylist is `.ssh`, `.gnupg`, `.aws`, `.azure`, `.kube`, `.docker` and `.password-store` folders, `~/.config/gh`, `~/.claude.json`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `id_rsa*`, `id_dsa*`, `id_ecdsa*`, `id_ed25519*`, `.env`, `.env.*` (except `.env.example`, `.env.sample` and `.env.template`), `.netrc`, `.npmrc`, `.pypirc`, `credentials`, `credentials.json`, `credentials.csv`, `.git-credentials`, `.vault-token` and `*.kdbx` (`secrets.private_path`; the commit offer uses it too).
  - A skill containing `.git` (folder or file) is refused.
- **Validation first:** an unknown or ambiguous name, a duplicate or a bad choice in `--own` or `set own` exits with code 2 before anything changes.
- **Idempotent:** a second run classifies recorded items as `keep` and asks nothing.

## 6. Known limits (to document for users)

- An MCP server is managed by loadout only if it is in `managed-mcp.json` or its config in `~/.claude.json` is identical to the personal one; otherwise `apply_mcp` leaves the user's server alone (G2). Recording through adopt seeds `managed-mcp.json`.
- A plugin recorded on one machine reaches another through the daily pull of the personal layer; Claude Code then installs it at its next start, in the background, and it is active after `/reload-plugins` or a new session (G1). `LOADOUT_NO_AUTO_PULL=1` stops the pull, and with it this.
- A profile is copied into a repo when applied; later changes to the personal profile do not reach repos until it is applied again. Skill copies in a repo can drift from the personal layer.
- A skill recorded as a pointer to a shared source is linked only on machines where that source exists.
- A hook whose command points outside `$HOME`, a complex shell command and a hook in exec form (`args`) are recorded as is and only work where their paths exist.
- For a hook script, only the script file is copied, also behind an interpreter (`/bin/sh ~/x.sh`); files it reads next to it must be copied into `<personal>/hooks/` by hand.
- A hook matcher that contains `,` cannot be named in `--own` or `set own`; choose it in the interactive prompt.
- Hook groups merge three-way by event + matcher + command set (`settings_merge.merge_settings`). If `~/.claude/settings.json` already holds a hook with the same command, event and matcher as a recorded one that loadout never applied there, the merge does not add it again (`settings_merge.effective_desired`) and that copy is not managed: it survives a removal from the personal layer. A group loadout applied before is updated in place when another field (such as `timeout`) changes, and removed with the personal layer only if the user did not change it. On the recording machine adopt records the regrouped hook as applied, so it is managed there. Duplicates already in `settings.json` are not cleaned up.
- A removal that fails leaves the item listed under own tools; profile membership explains only a plugin that is disabled globally.
- A leave decision stored by an older version for a `~/.claude/.mcp.json` server uses the plain `mcp:<name>` key and also hides a user-scope server of that name.
- Only backups made after the snapshot fix (adopt own tools, bootstrap) include `managed-settings.json`. Restoring an older backup after a global hook or plugin choice can let the next merge drop the restored value. `configure`, `apply-settings` and maintenance rewrite the snapshot without a backup.
- Scanning skill files takes roughly 2 s per MB.
- `leave` decisions are not synced between machines, and hooks in project settings files are not inspected (§9).

## 7. Tests

All with a temp `HOME`, `LOADOUT_PERSONAL` on a temp copy and `fake_runner`; no real installers or `claude` mutations.

- Each kind × {global, project, leave, remove}, including backup entries and `restore` undoing them.
- MCP global: secrets rewritten, `managed-mcp.json` seeded, a following `apply_mcp()` reports no change.
- Hook global: local script copied and path rewritten; outside-`$HOME` path and exec form warn; plain command unchanged; no duplicate after `apply_settings`.
- Skill: directory moved and linked (and copy mode); shared-source symlink becomes a pointer; profile `skills` copied into a repo and never overwrites.
- Profile name equal to a kit profile: personal copy starts from the kit profile.
- Collisions skip; `.cmd` shim path removes nothing; unfixable secret blocks global/project.
- `classify`: personal-layer items are `keep`; left items are `keep`; G3 regression.
- Defaults: `--yes` and non-interactive leave everything; `--own` parse and validation errors; ambiguous name needs `<kind>:`.
- Idempotent re-run asks nothing.
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
