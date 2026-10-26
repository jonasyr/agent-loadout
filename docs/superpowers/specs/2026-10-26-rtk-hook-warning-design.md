# Design: silence rtk's false "No hook installed" warning

## Why

loadout provides rtk's Claude Code hook through its plugin (`plugins/loadout/hooks/hooks.json` runs `run.sh rtk hook claude`). rtk does not see plugin hooks. Its check (`hook_check.rs` / `init/claude.rs::hook_status`, the same in 1.0.1 and 1.1.0) looks only at:

- a `rtk hook claude` entry in `~/.claude/settings.json`;
- the legacy script `~/.claude/hooks/rtk-rewrite.sh`.

So on every machine set up by loadout, rtk prints this line on stderr, once a day, wherever it runs (the terminal, Claude Code's and Codex's shells):

`[rtk] /!\ No hook installed — run \`rtk init -g\` for automatic token savings`

That is a false alarm, and an expensive one: an agent that follows it runs `rtk init -g`. That adds a second rtk hook to `settings.json`, so commands get rewritten twice. `adopt` would then flag that hook as a duplicate.

rtk has a documented off switch for exactly this warning. `[hooks] suppress_hook_warning = true` in rtk's `config.toml` hides only "Missing", never "Hook outdated" (`config.rs`, `HooksConfig`). The environment variable `RTK_SUPPRESS_HOOK_WARNING` would also work, but only where loadout can set it; the config file covers the terminal too.

The maintainer chose two things:

1. loadout sets that key.
2. An issue upstream asks rtk to detect hooks that come from Claude Code plugins.

The issue is not part of this build. It is drafted separately and posted after the maintainer reads it.

## Goals

- On a machine where loadout's plugin provides the rtk hook, rtk no longer prints "No hook installed".
- "Hook outdated" stays visible: the key does not hide it.
- The change follows the User files rules in `AGENTS.md`:
  - exact-text record;
  - parse guard;
  - atomic write;
  - a backup step before every change, so `loadout restore` undoes it.

## Non-goals

- No `loadout check` row (maintainer's choice). The existing duplicate-hook detection (`duplicates.py`, catalog `hook-rtk`) already catches a second rtk hook from `rtk init -g`.
- No change to rtk's other settings, and no `rtk init` run.
- No environment variable in Claude Code's or Codex's settings.

## Anti-goals

These count as failure even if the warning disappears:

- A value, comment or formatting the user wrote in rtk's `config.toml` changes.
- loadout overrides `suppress_hook_warning = false` that the user wrote.
- The key stays after loadout no longer provides the hook, so a real "Missing" would be hidden.

## Decisions

### When loadout sets the key ("wanted")

All of these hold:

- Claude Code is on in `targets.json`;
- loadout's plugin is enabled in the desired settings (`duplicates.plugin_enabled()`);
- the plugin's hooks include the rtk hook (`duplicates.plugin_guarded_hooks("rtk")` or the same parse of `hooks.json`);
- `rtk` is on PATH (`runner.have("rtk")`).

Otherwise loadout's own key is not wanted, and loadout removes it (see Removal).

Two builder-check answers (my calls, not the maintainer's):

- **"Plugin enabled" means loadout's desired settings,** the same source as the duplicate-hook detection. It is not what `~/.claude/settings.json` holds now, so this step reads no agent folder.
- **The step runs on every re-apply, Codex-only runs included,** not inside the Claude-only part. So turning Claude Code off removes the key at the next `update`/`bootstrap`. Removal happens only then, not when `targets.json` changes.

### rtk versions

`suppress_hook_warning` exists since rtk 1.0.0. No rtk version rejects unknown config keys: there is no `deny_unknown_fields` in 0.30, 0.40 or 1.1.0. An older rtk ignores the key, so no version gate is needed.

### Where rtk's config lives

rtk uses `dirs::config_dir()/rtk/config.toml`:

| Platform | Path |
|---|---|
| Linux | `$XDG_CONFIG_HOME/rtk/config.toml` if absolute, else `~/.config/rtk/config.toml` |
| macOS | `~/Library/Application Support/rtk/config.toml` |
| Windows | `%APPDATA%\rtk\config.toml` (Roaming; fallback `~/AppData/Roaming`) |

The helper goes in `paths.py` and derives from `home()` like the others. In WSL this is the Linux path.

### Applying

The edit runs where loadout re-applies the setup (bootstrap, `update`, `adopt`'s re-apply), with a dry-run plan line like the other parts. The cases:

- **File missing.** Create it with exactly `[hooks]\nsuppress_hook_warning = true\n` (maintainer's choice). Record it as created (`bk.record_created`), so restore deletes it again.
- **File exists, `[hooks]` is a plain header table without the key.** Insert `suppress_hook_warning = true` as the table's last line, using the file's own newline (CRLF kept).
- **File exists, no `hooks` table at all.** Append `\n[hooks]\nsuppress_hook_warning = true\n`, adding a newline first if the file does not end with one.
- **The key is already there, from the user:**
  - `true`: nothing to do and nothing recorded. It is the user's line.
  - `false`: leave it. Print once, in bootstrap's or update's output, that rtk's warning stays because the user's rtk config sets `suppress_hook_warning = false`. A "said" marker in the record keeps it from repeating (maintainer's choice).
- **`hooks` is written another way** (an inline table, dotted keys `hooks.x = …`, or a header with quoting loadout cannot place safely). Leave the file and say once that loadout could not add the key.
- **The file does not parse.** Leave it, and say so in the apply line ("does not parse now; left as is"), as `codex.apply_config` does.

Every write:

1. A `bk.save_copy` before it (or `record_created` for a new file).
2. Then a parse guard: the result must parse to the old data plus `hooks.suppress_hook_warning = true` and nothing else.
3. Then `jsonio.write_atomic`.

The exact line written, whether loadout added the `[hooks]` header, and whether it created the file are recorded in a small state file, e.g. `paths.state_dir()/"rtk-config.json"`. The run's backup also saves that record, the way `settings_merge.backup_snapshot` does, so a restore does not leave a stale ownership record behind (my call).

### Removal

When the key is no longer wanted, or the plugin, Claude Code or rtk is gone:

1. Remove loadout's line only if it still reads exactly as recorded. A changed line is the user's from then on: release it, record that, and leave it.
2. Remove the `[hooks]` header only if loadout added it and the table is empty now.
3. Delete the file only if loadout created it and its content is exactly what loadout wrote.

The same backup step and parse guard apply. Then clear the record.

## Left to the builder

- The module layout: a new small module next to `codex_hooks.py` is the expected shape (`path()`, record, `apply(bk, dry_run)`). So is the exact hook-in point in `apply.py` / the re-apply steps.
- The plan and output wording, matching the existing apply lines.
- Docs:
  - an ADR (0043), with an index row and the `AGENTS.md` range;
  - where `docs/reference` lists files loadout writes;
  - a line in `docs/explanation/the-toolset.md` or wherever rtk's hook is described;
  - a troubleshooting row for the warning.
- Tests with `fake_home` / `fake_runner` cover:
  - each case above;
  - CRLF;
  - the user's `false`;
  - removal after the plugin is off;
  - restore of a created file;
  - an unparseable file;
  - a macOS path and a Windows path.
