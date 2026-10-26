# Design: get past Codex's 30-second marketplace-upgrade timeout

## Why

`codex plugin marketplace upgrade` clones the marketplace again, and Codex gives that clone a fixed 30 seconds (`MARKETPLACE_UPGRADE_GIT_TIMEOUT` in `codex-rs/core-plugins/src/marketplace_upgrade.rs`, codex-cli 0.164.0). Neither a config key, an environment variable nor a flag changes it ([openai/codex#38770](https://github.com/openai/codex/issues/38770)).

On the maintainer's machine, `pbakaus/impeccable` (a snapshot of about 720 MB) misses that limit on every run:

- `loadout update` reports `marketplace impeccable: failed to upgrade (…timed out after 30s)` (handled since #59). Its plugins then stay at the old version for good.
- Each failed attempt also left a clone in `~/.codex/.tmp/marketplaces/.staging/`. That folder had grown to 53 GB in 810 folders before the maintainer emptied it by hand ([openai/codex#39421](https://github.com/openai/codex/issues/39421)).

`codex plugin marketplace add` clones with no time limit: `marketplace_add/install.rs`, `run_git`, which calls `command.output()`. `codex plugin marketplace remove <name>` deletes only two things:

- the `[marketplaces.<name>]` table in the user's `config.toml`;
- the snapshot `~/.codex/.tmp/marketplaces/<name>`.

`[plugins."x@<name>"]` entries and `plugins/cache` stay. Removing the marketplace and adding it again therefore gets a large marketplace current where `upgrade` cannot.

Codex 0.164 already reclaims abandoned staging folders itself (`marketplace_staging.rs`), but only up to 4 per run. A folder that keeps growing still deserves a warning.

## Decisions (the maintainer's)

1. **Automatic.** Within `loadout update`, the only trigger is a Codex upgrade that timed out. loadout then removes the marketplace and adds it again, with a backup, and the plan and output say so. Nothing is asked.
2. **Only loadout's marketplaces**: the routes `_install_routes` already walks (desired settings / catalog). A marketplace the user added themselves is never touched.
3. **`loadout check` warns above a size** of `~/.codex/.tmp/marketplaces/.staging`. It deletes nothing itself.

## Behaviour

### Re-add after a timeout (`cli/loadout/codex.py`)

`_install_routes` already calls `_upgrade(exe, market)`, which ends in `refreshed, stale = up.ok, not up.ok`. Add one step between "upgrade failed" and "stale":

- **Trigger:** the upgrade failed, and its stderr contains Codex's timeout text (`timed out after 30s`; match `timed out after` together with `marketplace` or `git clone`, not loadout's own runner timeout, exit 124). Any other failure stays as today: one retry, then the existing `failed to upgrade` line.
- **Only when the add reproduces the table.** The user's table for that marketplace (`marketplaces()[market]`) must have no `ref_name` and no `sparse_paths` beyond what `marketplace add <src>` itself writes; for a `src` with `@ref`, the matching `ref_name` is fine. Otherwise loadout keeps today's failure line and adds `; loadout did not re-add it because your table sets <keys>`.
- **Not while Codex runs (the maintainer's decision).** During the re-add the table is missing for up to `CLONE_TIMEOUT`. A running Codex (app, VS Code extension, a session) could clone the marketplace itself or rewrite `config.toml` in that time. So before step 1, loadout checks for a running Codex process. If one runs, nothing is removed, and the line reads `marketplace <market>: Codex's upgrade timed out after 30s; quit Codex and run loadout update again to re-add it (openai/codex#38770)`. Plugins stay as they are, as today.
  - **New helper** `codex.codex_running() -> bool | None`:
    - Linux: read `/proc/*/comm`, and the first `cmdline` entry, without running anything.
    - macOS: `ps -A -o comm=`.
    - Windows: `tasklist /FO CSV /NH`.

    Both commands run through `runner.run` with a timeout.
  - **Match:** the program's basename, case-insensitive, is `codex` or `codex.exe`. The Codex app's main binary counts too. `codex-reviewer` or a path that only contains "codex" does not count.
  - **When it can't tell** (`None`): my call is to treat that as running. The re-add is skipped, the line says `could not tell whether Codex runs`, and safe wins over automatic.
  - **Scope:** processes on this OS only; a Windows Codex seen from WSL is out of scope.
- **Remove needs no snapshot.** Verified in `marketplace_remove.rs`: `remove_marketplace_sync` fails only when neither the table nor the snapshot exists, and it does not look at installed plugins. Moving the snapshot aside first is therefore safe.
- **No retry after Codex's timeout** (my call): `_upgrade` returns at once on Codex's timeout text, as it does on exit 124, because each failed try leaves one more clone in `.staging`.
- **"loadout's marketplace"** (my call): every marketplace in the routes `_install_routes` walks, also one the user had added before loadout did. The `ref_name`/`sparse_paths` rule below keeps a table the add would not reproduce.
- **Reading the table:** `marketplaces()` returns only `root` and `source`, so the `ref_name`/`sparse_paths` rule reads `[marketplaces.<market>]` from `config.toml` with `tomllib`.
- **Steps:**
  1. Back up the `config.toml` file (`bk.save_copy`).
  2. Move the snapshot folder aside (`bk.move`; a rename on the same disk, so it is cheap).
  3. Run `codex plugin marketplace remove <market>`.
  4. Run `codex plugin marketplace add <src> --json` with `CLONE_TIMEOUT`, through `runner.run` as today. Call `_keep_lock()` before each long call.
- **Success:** `refreshed = True` and `stale = False`. The plugin loop then reinstalls the marketplace's plugins from the new snapshot exactly as after a normal upgrade. `_remember(src, market, head)` records the head. The moved-aside snapshot is deleted from the backup, because it is a stale clone of a few hundred MB and keeping one per run would fill the backups. The config copy stays, so `loadout restore` can put the old table back. Output: `marketplace <market>: Codex's upgrade timed out after 30s; removed and added it again (openai/codex#38770)`.
- **Failure** (remove or add): put the snapshot back and write the backed-up `config.toml` back, the exact bytes and atomically, only if the file now lacks the `[marketplaces.<market>]` table. The result is the state before the attempt. Then report today's stale line plus `; re-adding it failed too (<tail>)`. Plugins stay as they are, as today.
- **Same rules as the rest of update:** nothing runs with Codex turned off in `targets.json`. Frozen marketplaces (`autoUpdate: false` on the daily sync) never reach the upgrade, so never the re-add either. The daily sync (`auto=True`) does the same as an explicit `loadout update`.
- **The plan:** where `loadout update` shows its numbered plan, nothing new is needed up front, because the timeout is only known when it happens. The run's output line is the record.

### Check row (`cli/loadout/check.py`)

- **Name:** `Codex marketplace staging`.
- **Shown** only with Codex on.
- **States:**
  - OK: the folder is missing or below 1 GB. Detail: the size, or `empty`.
  - warn above 1 GB. Detail: `<size> in <n> folders in ~/.codex/.tmp/marketplaces/.staging`.
- **Fix text:** `quit Codex, then empty that folder (abandoned clones of failed marketplace upgrades, openai/codex#39421)`.
- **Measuring:** walk with `os.scandir`, without following symlinks. Stop counting bytes at the threshold and report it as `over 1 GB`, so a 500 GB folder does not make `check` slow. Count the top-level folders separately; that is cheap.
- **Reads only.** It never runs `codex`.

## Non-goals

- No change to Codex itself, and no patched timeout.
- No cleanup of `.staging` by loadout (the maintainer chose "warn only"), and no handling of the `~/.codex/.tmp/git-*` folders.
- No re-add for marketplaces the user added themselves.
- No change for Claude Code's marketplaces (`claude plugin marketplace update` has no such limit).

## Docs

- A new ADR 0042, "Re-add a Codex marketplace whose upgrade timed out". It records the trigger, the scope (loadout's marketplaces only), the backup and rollback, and why the old snapshot is not kept.
- `docs/how-to/troubleshooting.md`: one entry on the timeout and the staging folder.
- `docs/reference/check.md` (or wherever check rows are listed): the new row.
- The backlog line for this bug becomes DONE.

## Left to the builder

- The exact helper names and where the table-matches-the-add test lives.
- How the rollback reuses `backup.py`. It may restore the two items directly instead of through `loadout restore`.
- The size format (match the other check rows).
