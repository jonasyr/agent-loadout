# Secret-free backup manifest (design)

Date: 2026-10-31. Status: approved direction, spec for planning.

## Why

AGENTS.md "Secrets" (P1): no plaintext secret is written to the backup manifest. The code breaks that rule today. When loadout removes or rewrites a user-scope Claude Code MCP server, it records the undo as `claude mcp add-json -s user NAME '<full config JSON>'` inside `manifest.json`. The JSON includes `env` and `headers` values, which can be tokens. The user docs describe and accept this ("backups can hold … undo commands with secrets", `docs/how-to/undo-and-restore.md:30`, `:85`; `docs/explanation/security-and-trust.md:78`), so the docs contradict the rule. The user chose to fix the code so the rule holds. The manifest is the file people open, read and might paste somewhere: it must be safe to show.

Found by the agent-teams run on the start-clean design (`docs/superpowers/specs/2026-10-31-start-clean-design.md` section 5). That feature (`--use-loadout`) would make more of these undos, so this fix lands first.

## Where it happens today

- `cli/loadout/adopt.py` `_apply_mcp` (lines ~309-315): removing a user's `~/.claude.json` server records `["claude","mcp","add-json","-s","user",name,json.dumps(cfg)]` via `Backup.record_command`.
- `cli/loadout/personal_mcp.py` `replace_user_server` (line ~83, used by `adopt.fix_secrets`): records `add-json … json.dumps(original)`. The original still holds the plaintext secret it is replacing.
- Restore: `backup._undo` runs `"run"` steps after `_allowed_run` (which accepts `add-json` only with 7 args and a JSON object as the last one). `_refused_pairs` pairs a `remove` with its later `add-json` for the Windows `.cmd` shim case. `contents()` (used by `restore --show`) prints run commands through `redact()` heuristics.

## Goals

1. No new `manifest.json` contains an MCP server config (or any secret value) inline.
2. Restore re-adds exactly the original server config, the same as today.
3. `restore --show` shows the step without the config, so nothing depends on `redact()` guessing.
4. Every existing safety property stays: restore runs only allowlisted undo commands; a referenced file must sit inside that backup's own `files/` folder (like `move`/`restore-file`); Windows shim pairing still writes the manual-commands file instead of running half a pair.
5. Old backups with inline configs keep restoring unchanged.

## Non-goals

- Rewriting or migrating existing backups (user decision: leave them; restore keeps working; docs say older backups can carry secrets in the manifest).
- Avoiding the secret on the command line during restore. `claude mcp add-json` takes the config only as an argument, so the value is in argv for the call's duration. Documented, not fixed. Restoring with `${VAR}` references instead was rejected because the undo must put back the original exactly.
- The Windows manual-commands files (`runner.write_manual_commands`, labelled "full commands, contains secrets"). They are separate 0600 files, not the manifest, and stay as they are.
- Codex: `codex.remove_server` backs up a copy of `config.toml` (`save_copy`). That is a file copy in `files/`, not manifest content. Out of scope.
- A `loadout check` row for old backups.

## Anti-goals

- An undo that no longer restores the original server, or restores it with a different config.
- A manifest field that lets a hand-edited manifest read a file outside its backup or run anything beyond today's allowlist.

## Design (decided)

- The config goes into the backup's `files/` folder as a private file (0600, the folder 0700: the same `_slot` + `_private` path that `save_copy` uses), one file per recorded undo, written before the manifest step that refers to it.
- The manifest step keeps the command without its last argument (`claude mcp add-json -s user NAME`) and refers to the config file. At restore, loadout checks that the file is inside this backup's `files/` (as for `move`/`restore-file`) and parses to a JSON object, then appends it as the last argument and runs the result through the existing `_allowed_run` + `runner.run` path. A missing file, unreadable JSON, a non-object, or a path outside `files/` gives a `failed: <label>: …` line, and nothing runs.
- `_refused_pairs` and `runner.would_refuse` see the full command (with the config loaded) so the Windows shim handling works as today.
- `contents()` shows the step as `run: claude mcp add-json -s user NAME <config in files/…>` (path shortened with `~` like other steps).
- Both call sites (`adopt._apply_mcp`, `personal_mcp.replace_user_server`) use one new `Backup` method for this. No caller builds the inline form any more.
- Old manifests: a `run` step whose `add-json` carries the JSON inline still passes `_allowed_run` and restores as today.

Settled after the builder check (Claude's calls, consistent with "never leave the user without the server"):
- **A bad config skips its pair.** When an `add-json` step's config cannot be loaded (missing, outside `files/`, symlink, not a JSON object), `_refused_pairs` (or its successor) also skips the paired earlier `remove` of the same server, with a `failed:` line for both. Restore never removes a server it then cannot re-add, the same rule as the Windows shim case. Its own test.
- **The config file stays after restore.** It stays in `files/`, like the copies `restore-file` leaves behind, so a `--force` replay works. `files/` holding a secret until the backup is deleted is accepted and documented (the docs already say so for copies).
- **The file is written only after the decision.** In `adopt._apply_mcp` and `replace_user_server`, the full command is built in memory for `runner.would_refuse` and the manual-commands file. The new `Backup` method (which writes the config file and the manifest step) is called only once the removal or replacement will actually happen, so a refused removal leaves no config file and no step.

## Left to the builder

- The exact manifest shape (e.g. a `"config-file"` key next to `"run"`, or a new undo kind), the method name, and the file naming in `files/`. Constraints: goals 1-5, and `summary()` still counts it as a command.
- Whether `_allowed_run` checks the 6-argument form directly or the loaded 7-argument form.

## Docs to update

- `docs/how-to/undo-and-restore.md` line 30: the manifest holds no secret values. MCP server configs and copied files in `files/` can, with the same file modes. Backups made before this change can still carry secrets in the manifest. Line 85 ("Do not share it: it can contain secrets"): the manifest of a new backup is safe to show; `files/` is not.
- `docs/explanation/security-and-trust.md` line 78: the same, in one sentence, plus that a restore passes the config to `claude` on the command line.
- If `docs/reference/` describes manifest step kinds, add the new one there.

## Tests (fake_home, fake_runner)

1. Adopt removing a user MCP server with an `env` secret: `manifest.json` text does not contain the secret value. The config file in `files/` does and has mode 0600 (POSIX).
2. Restore of that backup calls `claude mcp add-json -s user NAME <exact original JSON>` (compared as parsed JSON).
3. `fix_secrets` / `replace_user_server`: the same two properties for the "(original)" step; the reverse-replay order (remove rewritten, then add original) is unchanged.
4. A manifest whose config reference points outside `files/` (or to a symlink, a missing file, a non-object JSON) is refused with a `failed:` line, and no command runs.
5. Windows shim pairing: with `would_refuse` true, restore writes the manual-commands file with the full pair and runs neither command.
6. An old-style manifest with the inline JSON still restores (existing tests keep passing; `test_secret_fix_undo_removes_then_readds_original` is updated to read the config through the new path).
7. `restore --show` for the new step contains no secret and names the config file.
8. A `remove` + `add-json` pair whose config cannot be loaded: neither runs, both get a `failed:` line, the server stays.
9. Adopt with `would_refuse` true (Windows shim): no config file in `files/`, no manifest step, manual-commands file written as today.
