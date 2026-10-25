# 0042. Re-add a Codex marketplace whose upgrade timed out

- Status: Accepted
- Date: 2026-10-25
- Source: [Design: get past Codex's 30-second marketplace-upgrade timeout](../superpowers/specs/2026-10-25-codex-marketplace-timeout-design.md)

## Context

`codex plugin marketplace upgrade` clones the marketplace again and gives that clone a fixed 30 seconds (`MARKETPLACE_UPGRADE_GIT_TIMEOUT` in codex-rs, codex-cli 0.164.0). No config key, environment variable or flag changes it ([openai/codex#38770](https://github.com/openai/codex/issues/38770)).

On the maintainer's machine, `pbakaus/impeccable` (a snapshot of about 720 MB) missed that limit on every run. `loadout update` reported the failure, and its plugins stayed at the old version for good. Each failed try also left a clone in `~/.codex/.tmp/marketplaces/.staging/`, which had grown to 53 GB in 810 folders ([openai/codex#39421](https://github.com/openai/codex/issues/39421)).

Codex's source shows a way around it:

- `codex plugin marketplace add` clones with no time limit.
- `codex plugin marketplace remove <name>` deletes only two things: the `[marketplaces.<name>]` table and the snapshot. Plugin entries and installed plugins stay. It also succeeds when the snapshot is already gone.

## Decision

- **Trigger:** only Codex's own timeout of the upgrade. loadout's runner timeout (exit 124) and other failures keep their old handling: one retry for the others, then the "failed to upgrade" line. After Codex's timeout, the upgrade is not tried again, because each try leaves one more clone in `.staging`.
- **Scope:** only loadout's marketplaces, the routes `loadout update` walks. Also excluded:
  - a marketplace frozen by `autoUpdate: false` (daily sync);
  - Codex turned off in `targets.json`.
- **When a table is left alone:** loadout says so and leaves the table in two cases:
  - your `[marketplaces.<name>]` sets `ref_name` or `sparse_paths` that `add` would not write again;
  - the table is not a plain header table (an inline table, dotted keys), so its text could not be put back byte for byte. Any quoting of the header (`["marketplaces".name]`) is fine.
- **Never while Codex runs.** During the re-add the table is missing for a while, and a running Codex could clone the marketplace itself or rewrite `config.toml`. `codex.codex_running()` checks processes on this OS:
  - Linux: `/proc`;
  - macOS: `ps`;
  - Windows: `tasklist`.

  In WSL with a Codex home on the Windows drive, a Windows Codex sharing that home is invisible to `/proc`, so the check cannot tell. If Codex runs, or the check cannot tell, nothing is removed, and the line asks you to quit Codex and run `loadout update` again.
- **Backup and rollback:**
  1. A copy of `config.toml` goes into the run's backup.
  2. The snapshot is moved aside into the backup.
  3. Then remove, then add.
  4. On success:
     - loadout writes your `config.toml` back byte for byte. Only the values Codex refreshed in the marketplace's table (`last_updated`, `last_revision`) are set, and only when the result parses to exactly what Codex wrote; otherwise Codex's file stays. Comments and formatting in the table survive this way.
     - The moved-aside snapshot stays in this run's backup, so `loadout restore` can put the old snapshot and the old config back together.
     - The maintainer chose "keep only the newest": copies of the same marketplace in older backups are deleted. A snapshot of a few hundred MB per run would otherwise fill the backups while the upstream limit stands.
  5. On failure:
     - the config bytes go back first, and only when the table is missing (a running Codex may have written it again, and that version is kept);
     - then the snapshot goes back. If moving it back fails, the line says the snapshot stays in the backup.
- **Check row:** `loadout check` adds a row, `Codex marketplace staging`, which warns above 1 GB. It counts with a capped walk and deletes nothing.

## Alternatives considered

- **Retry the upgrade:** the limit is the same on every try, and each try leaks one more clone.
- **A patched or configurable timeout:** that is Codex's to change, and the upstream issue tracks it.
- **Leave it to the user** (only a fix line): the plugins of a large marketplace then never update.
- **Clean `.staging` in `adopt`:** the maintainer chose "warn only". Codex 0.164 reclaims abandoned folders itself, a few per run.

## Consequences

- A large loadout marketplace stays current despite the 30 s limit. Each `loadout update` re-clones it in full while the upstream limit stands.
- `loadout restore` of the newest such run puts the old `config.toml` and snapshot back. An older run's snapshot step reports that nothing is left, because its copy was dropped on purpose; its config still comes back.
- Once Codex makes the limit configurable or removes it, the trigger no longer fires, and the code can go.

## In the code

- `cli/loadout/codex.py`: `codex_running`, `_codex_timed_out`, `_table_blockers`, `_readd`, `_upgrade`, `_install_routes`
- `cli/loadout/check.py`: `_codex_staging`, `_dir_size_capped`
