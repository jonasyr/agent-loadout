# Live tour fixes

Status: approved scope (user, 2026-10-21). Evidence: the live tour on Linux (cases A-E: Codex CLI only, own Serena, both agents with a shared repo, VS Code's Codex extension only, VS Code's Claude Code extension only), findings and bootstrap logs in `.superpowers/handoff/2026-10-21-live-tour-findings.md` and `live-tour-logs/` (git-ignored; the numbers below are its finding numbers).

## Why

A fresh machine does not get the kit loadout promises, failures look like success, and one click in Codex ends loadout's ownership of a server. The friend's first install (WSL/Windows) is next; these must be fixed before it.

## Out of scope (own PR later, "BIG")

VS Code's Codex extension loads plugins installed with its bundled `codex` and has its own hook review (findings 22, 24, 29, 30). ADR 0033's extension mode is outdated. Everything about extension mode (hooks_status counting the plugin's hooks, the "Codex plugin: not installed" row, four warnings for one cause, "the extension has no /hooks") waits for that PR (findings 16, 22, 28, 32). Remote-WSL and native Windows were not toured.

## Fixes

1. **The official marketplace on a fresh machine (17, 34).** `settings.base.json` declares every marketplace in `extraKnownMarketplaces` except `claude-plugins-official`, whose plugins are 10 of the 12 enabled. Claude Code 2.1.304 no longer has it by default, so `claude plugin install …@claude-plugins-official` fails on a fresh home, and `loadout update` cannot repair it. Declare it (`github`, `anthropics/claude-plugins-official`) like the others, so bootstrap and update add it. `plugins_plan` matches marketplace names exactly (today a substring test on `claude plugin marketplace list` text). The `plugins installed` check row stops claiming the plugins "install automatically at the next Claude Code start"; it names a missing marketplace when that is the cause, and its fix is `loadout update` (or `loadout bootstrap`).

2. **`bootstrap --no-plugins` (13).** The flag skips Codex's marketplaces and plugins too, as its help says.

3. **A large Codex clone is honest (2, 4, 20).** `codex plugin marketplace add pbakaus/impeccable` cloned 400+ MB and hit the 900 s timeout while the screen showed one unchanging line; bootstrap then exited 0, "Still to do" said nothing and `loadout check` found nothing missing. Now:
   - the progress line says a clone can take several minutes for a large repository;
   - marketplace add and upgrade get a longer timeout (1800 s);
   - `loadout check` gets a Codex row for every marketplace and plugin loadout wants but Codex lacks (CLI mode only), fix `loadout update`, which already retries them;
   - bootstrap's "Still to do" names it.

4. **Codex tool approvals stay the user's (31).** Choosing "Always allow" writes `[mcp_servers.<name>.tools.<tool>]` with `approval_mode` under a table loadout owns. Today any sub-table releases the whole table ("left as is (it has sub-tables); loadout no longer manages it"). From now on `tools.*` sub-tables are the user's own text inside a table loadout keeps managing: never compared, never rewritten: when loadout replaces the parent (now in place, not moved to the end of the file) the sub-tables and a comment directly above them keep their lines (blank lines between tables stay as loadout's writer already normalises them). If loadout would remove a parent that still has `tools.*` sub-tables, it keeps both and says so once (recorded like a release), because orphaned sub-tables stop Codex from starting. A table released earlier only because of `tools.*` sub-tables is managed again once its own text equals loadout's. ADR 0036.

5. **Codex asks once about Serena's approvals (7).** Claude Code auto-approves Serena through loadout's hook; Codex asks before every `serena_repl` call. A new preference, asked once when Codex is on (bootstrap, `loadout configure prefs`), with the trade-off stated (serena_repl runs code in Serena's process): "approve automatically" writes `approval_mode = "approve"` in `[mcp_servers.serena.tools.serena_repl]` when loadout owns the serena table; "ask each time" (default) writes nothing, and removes only the key (and a header) loadout wrote. A user's own Serena table (named `serena` since Serena 2.1's `serena setup codex`) is never changed; the answer is then a note said once. A personal layer cloned onto a new machine, or Codex turned on later, is not asked: the default applies and `loadout configure prefs` changes it. The choice is stored in a new personal-layer file `loadout.json` (data only loadout reads; a preference target kind for Codex-only choices), so it syncs with the personal layer. ADR 0036.

6. **Marketplaces only when a plugin uses them (18).** Bootstrap and update clone a declared marketplace only when it is loadout's own or an enabled plugin comes from it (`life-sciences` stays declared for people who enable `wiley-scholar-gateway` themselves, but is not cloned otherwise). `academic-research-skills` moves from `settings.base.json` to `profiles/thesis.json`; applying the profile adds it when Claude Code lacks it, before installing its plugin (a `run` step in the plan, not undoable, as profile commands are). Existing machines keep their clones; only the settings entry goes. Inventory treats a profile's marketplace as the kit's; adopt keeps declaring an adopted plugin's marketplace. ADR 0037.

7. **No `X -> X` updates (10, 19).** When mise has no install of a tool (empty `current`), `find_outdated` compares the version of the binary on PATH with mise's latest and reports only a newer one. No list (hook notice, update plan, adopt) ever shows an update whose versions are equal.

8. **codebase-memory's daemon conflict is named (6).** codebase-memory-mcp 0.12 runs one daemon per user account and refuses to start for a second cache folder; the agent shows only "failed". The failing session writes the conflict into its own cache folder (`$CBM_CACHE_DIR`, else `~/.cache/codebase-memory-mcp`; verified). `loadout check` reads `<cache>/logs/daemon-conflicts.ndjson` (read only, POSIX) and warns when it has an entry from the last 24 hours, with the server's own explanation and fix. No probe starts a server (`daemon status` hangs).

9. **A user's own codebase-memory table in Codex (real machine).** A `[mcp_servers.codebase-memory-mcp]` the user wrote in `config.toml` next to the loadout plugin's server of the same name is named by `loadout check` (warn; which one runs is Codex's choice), fix: remove the user's table (the plugin provides the server) or turn the plugin off in Codex.

10. **"Now do this" (1, backlog 2026-10-21).** One Codex step when both "restart Codex" and the hooks step apply (the hooks step already says restart). `derive` never returns the same id twice. The Claude Code "/reload-plugins" step clears when loadout's Stop hook runs from the newly installed loadout plugin folder, but only when loadout's own plugin was among the updated ones (the only reload a hook can see); otherwise it clears at the next session as before.

11. **Plain words (14, 25, 36).** Bootstrap's Codex line names skills only when it linked some. When the user's own Serena is kept, one line says so. Adopt does not list "Not installed yet: claude" when VS Code's Claude Code extension's claude runs loadout's commands; it says a claude on PATH is optional (for the terminal).

## Deferred to the backlog (with evidence)

- Account-synced plugins (35): `~/.claude/plugins/synced/<bucket>/manifest.json` lists `superpowers` with `installationPreference: "available"`, and the maintainer's sessions load superpowers' skills once. A duplicate row needs to know which preferences load the plugin; not guessed.
- Serena's dashboard on launch as a personal preference (user, 2026-10-21).

## Constraints

Every rule in AGENTS.md: exact-text records, backups before writes, `runner.run` argument lists, `fake_home`/`fake_runner` in tests, no real installers or mutating `claude`/`codex` in tests, no plaintext secrets, Conventional Commits without attribution.
