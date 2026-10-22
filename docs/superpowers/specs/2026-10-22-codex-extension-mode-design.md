# Codex extension mode, as the extension really works

Status: draft for your review (answers from the user, 2026-10-22). Evidence: the live tour, case D (VS Code's Codex extension 26.1007, bundled codex 0.162.0-alpha, no Codex CLI), findings 16, 21-25, 27-30 and 32 in `.superpowers/handoff/2026-10-21-live-tour-findings.md` (git-ignored); the BIG entry in `.superpowers/handoff/2026-10-13-hardening-backlog.md`.

## Why

ADR 0033 (#50) set Codex up for VS Code's Codex extension without its CLI on two claims the tour disproved:
- the extension loads no plugins;
- it has no `/hooks`.

In fact it loads plugins installed with its bundled `codex plugin marketplace add` / `plugin add` into `~/.codex`. `$loadout` then lists loadout's skills, and Settings > MCP servers > "From plugins" shows the plugin's codebase-memory-mcp. It also has its own hook review: the prompt-bar hooks icon ("Review hooks · N need approval", Allow all) and Settings > Hooks. Approvals land in `config.toml` `[hooks.state]`, as with the CLI.

So today a person with only the extension (Niklas' setup) gets:
- no loadout skills and no codebase-memory;
- four warn rows for one cause (finding 16);
- a "hooks not approved" warning that never clears, even after Allow all (finding 28);
- advice to install a CLI they do not need.

**Goal:** after `loadout bootstrap` on a machine with only the extension, the person opens VS Code, trusts the folder and clicks Allow all once. They then have everything the CLI user has, and `loadout check` is green.

## Decisions (the user's, 2026-10-22)

1. **Plugins in extension mode.** Bootstrap, update, the daily sync and `loadout profile` add marketplaces and install plugins with the extension's codex (`codex.program()`), exactly as in CLI mode, with the same timeouts and progress lines. No question first.
2. **Hooks.** The person approves them in the extension. loadout never writes trust into `[hooks.state]`. Every message that today says "the extension has no /hooks" names the way instead: the hooks icon in the prompt bar, then Allow all (or Settings > Hooks).
3. **One cause, one row.** Without a Codex CLI next to a usable extension, check shows one **OK/info** row, `Codex CLI: not installed (optional: VS Code's Codex extension runs its own)`. It is not a warning, and health does not count it as a problem. The `Codex plugin`, `Codex hooks`, `Codex plugins missing` and `Codex MCP <name>` rows check the real state through the extension's codex, as in CLI mode. The `binary codex` row and the `VS Code (Codex)` gap ("plugins do not load …, no /hooks") stop warning about a missing CLI.
4. **CLI and extension on one machine.** The CLI installs (as today); both read the same `~/.codex`, so one install serves both. A `VS Code (Codex)` row also checks the extension:
   - warn when its codex is older than 0.161, since it may then not load what the CLI installed;
   - warn when it reads another home (see 5).
5. **Windows, CLI in WSL, extension native.** These are two homes. loadout recommends VS Code's switch that runs the extension's codex in WSL (the existing `--vscode-wsl` offer). Declined, check names that the extension sees none of loadout's setup, with the switch as the fix. loadout does not set up the second home.
6. **Machines set up after #50 without plugins.** The next `loadout update` (or bootstrap, or the daily sync) installs the missing plugins. "Now do this" then says: approve the hooks in the extension.
7. **A too-old extension codex.** Unchanged: an extension codex under 0.161 (and no usable CLI) means Codex is not set up; the line names the extension update, then `loadout update`. Within >= 0.161, a `codex plugin` call that fails as an unknown command skips plugins with one line (update the extension, then `loadout update`); the rest is set up.
8. **A broken CLI next to a working extension.** When a Codex CLI is on PATH but unusable (too old, no version, or the Windows codex in WSL) and this side's extension runs a usable codex, loadout uses the extension's codex for everything (as in extension mode). Check warns once: the CLI is unusable (with its reason and fix), the extension's codex is used. `program()` and `unavailable()` decide this in one place.
9. **WSL and Windows.** Covered by tests with `fake_runner` in this PR. The live check happens at Niklas' first install; what it finds becomes its own fix PR.

## What changes

- `hooks_status()` counts only the hooks that can exist: Serena's always, and the loadout plugin's (`hook_keys()`) only when the loadout plugin is installed in Codex. Then Allow all in the extension makes it `trusted`, and the `codex/hooks` step and the `Codex hooks` row clear (finding 28).
- `apply_plugins`, `_codex_summary`, `update._codex_item`, `codex_project` (profile), `steps.derive`/`settle` (`codex/restart` without a CLI means "reload the VS Code window" or nothing; the builder decides from what the extension needs to pick up new plugins) and `open_steps()` drop the extension-mode skip and its `PLUGINS_EXTENSION` / `PLUGINS_EXTENSION_NOTE` / `HOOKS_NO_CLI` texts.
- Logins stay as they are (`LOGIN_EXTENSION`).
- Bootstrap's Codex CLI offer (`codex_recommended`, `CODEX_CLI_QUESTION`, `RECOMMENDED_WHY` "for /hooks and plugins") no longer claims the CLI is needed for plugins or hooks.
  - Builder's call: whether the offer stays, as an optional "for the terminal" offer, or goes. Keep `--without-codex-cli` working, as a no-op if the offer goes.
- New ADR 0038 supersedes the plugin and hooks parts of ADR 0033 (the usability rule, the 0.161 floor and `chatgpt.cliExecutable` stand). ADR 0033 gets "Superseded in part by 0038". Index and AGENTS.md range (0001-0038) updated.
- **The version parser keeps prereleases (backlog minor).** `0.163.0-alpha` sorts before `0.163.0` wherever versions are compared (`versions.parse_version`, `vscode.too_old`, `codex.unavailable`, `find_outdated`), so a prerelease never counts as the release.
- **Docs (finding 21).** Every page listed under "Docs" names VS Code's Restricted Mode ("Trust Folder & Continue") as step 1 for the extension.
- **`.serena/` in git (finding 27).** `loadout init` already adds `.serena/cache/` to `.gitignore`. The onboard skill (and init's output, if it says nothing today) names which `.serena/` files belong in git (`project.yml`, `memories/`) and which do not (`project.local.yml`, `cache/`).
  - The builder verifies this against what Serena 2.1 itself writes (its own `.serena/.gitignore`) and follows Serena.
- **Codex summary "skills" (finding 25).** Already fixed in #55 (`apply._codex_summary` names skills only when some were linked). Add a test for extension mode if none exists.

## Docs

Every page that states the old claims is rewritten:
- `docs/how-to/vscode.md`, `setups.md` (#recommended-setups: extension alone is a full setup), `codex.md`, `troubleshooting.md`, `wsl.md`;
- `install-with-an-agent.md`, `tutorials/getting-started.md`;
- `reference/cli.md`, `hooks.md`, `state-and-sync.md`, `profile-format.md`, `modules.md`;
- `explanation/architecture.md`, `security-and-trust.md`, `the-toolset.md`, `documentation-strategy.md`;
- `plugins/loadout/skills/configure/SKILL.md`.

`tests/test_docs_vscode.py` follows the new wording. Run `loadout:docs-sync` at the end.

## Non-goals

- Writing hook trust for the person.
- Setting up a second (Windows) Codex home.
- Changing the 0.161 floor.
- Claude Code's extension (case E passed).
- The other backlog items (synced plugins, Serena dashboard, guided install).

## Anti-goals

- A row or step that cannot clear after the person did what it said.
- A message that tells an extension-only person they need the CLI for anything loadout sets up.

## Constraints

Every rule in AGENTS.md:
- exact-text records, backups before writes;
- `runner.run` argument lists;
- `fake_home`/`fake_runner` in tests, no real installers or mutating `claude`/`codex` in tests;
- no plaintext secrets;
- Conventional Commits without attribution.

## Builder's calls made by the author (check these)

- The 0.161 floor compares (major, minor) only, so `0.161.0-alpha` passes; the prerelease ordering applies to update comparisons (`find_outdated`, adopt), not the floor.
- "Reads another home" (decision 4) means only what loadout already detects (`vscode.reads_home`, the Windows window, Remote-WSL, the WSL/Windows split); no new detection of VS Code's environment (for example `CODEX_HOME` set only in a shell).
- Undo records for plugin installs keep `["codex", ...]` (so `backup._allowed_run` still matches) and resolve to `program()` at replay.
