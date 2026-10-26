# 0043. Silence rtk's "No hook installed" warning where loadout's plugin provides the hook

- Status: Accepted
- Date: 2026-10-26
- Source: [Design: silence rtk's false "No hook installed" warning](../superpowers/specs/2026-10-26-rtk-hook-warning-design.md)

## Context

loadout's plugin provides rtk's Claude Code hook: `plugins/loadout/hooks/hooks.json` runs `run.sh rtk hook claude`. rtk does not see hooks that come from Claude Code plugins. Its check (the same in rtk 1.0.1 and 1.1.0) looks only in `~/.claude/settings.json` for a `rtk hook claude` entry, and at the legacy script `~/.claude/hooks/rtk-rewrite.sh`. So on every machine loadout sets up, rtk prints on stderr, once a day, wherever it runs:

`[rtk] /!\ No hook installed — run rtk init -g for automatic token savings`

The line is false, and it is expensive. An agent that follows it runs `rtk init -g`, which adds a second rtk hook to `settings.json`, so every command is rewritten twice, and `loadout check` then reports the duplicate. The upstream report is [rtk-ai/rtk#4800](https://github.com/rtk-ai/rtk/issues/4800), which asks rtk to detect plugin hooks.

rtk has a documented switch for this warning: `[hooks] suppress_hook_warning = true` in its `config.toml`. It hides only "Missing", never "Hook outdated". An environment variable does the same, but only where loadout can set it, not in the user's terminal.

## Decision

loadout sets `suppress_hook_warning = true` in rtk's `config.toml`, but only while loadout's plugin provides the hook. The line is "wanted" when all of these hold: Claude Code is on in `targets.json`, loadout's plugin is enabled in the desired settings and installed (a user-scope entry in Claude Code's `installed_plugins.json`, since rtk's setting is global; with `bootstrap --no-plugins` or a failed install rtk's warning is real), the plugin's hooks include the rtk hook, and `rtk` is on PATH. While `installed_plugins.json` does not parse, loadout leaves rtk's file as it is. The record holds the resolved path of rtk's file (through symlinked folders and a symlinked file); when rtk's file resolves elsewhere, loadout owns nothing in the new file.

- **Where the file is:** rtk's `dirs::config_dir()/rtk/config.toml`, per OS (`paths.rtk_config()`): Linux `$XDG_CONFIG_HOME` when absolute, else `~/.config`; macOS `~/Library/Application Support`; Windows `%APPDATA%`, else `~/AppData/Roaming`.
- **How it is written:** an exact-text record, a parse guard and an atomic write, as for the other User files. A backup is saved before every change, so `loadout restore` undoes it. A file loadout creates is recorded as created and deleted again on restore.
- **Your text stays:** a value, comment or format you wrote stays byte for byte. Your own `suppress_hook_warning = false` is kept; loadout prints once that rtk's warning stays because of it. A `hooks` table written in a form loadout cannot place safely (an inline table, dotted keys) is left alone, and loadout says once that it could not add the key.
- **A file that does not parse:** loadout leaves it and says so once; once it parses again, a later break is said again.
- **Removal:** when the line is no longer wanted, loadout removes its line only if it still reads exactly as recorded. An edited line is yours from then on, and loadout releases it. A line you delete while it is wanted comes back at the next run, as with loadout's Codex `config.toml` entries; to keep the warning, set `suppress_hook_warning = false`.
- **When it runs:** in bootstrap, `update`, `configure` and the daily sync (after a pull that brought new commits). It runs also with Claude Code off, so turning Claude Code off removes loadout's line at the next run, and with only Codex on.

"Hook outdated" stays visible, because the key does not hide it.

## Alternatives considered

- **Environment variable `RTK_SUPPRESS_HOOK_WARNING`:** it works only where loadout sets the environment, that is in Claude Code's and Codex's shells. The user's terminal would still warn, so the config file is the right place.
- **`rtk init -g`:** it adds a second hook to `settings.json`, so commands are rewritten twice. It is exactly what the warning tempts agents to do.
- **Leave the warning:** agents follow the hint, so the duplicate hook keeps coming back.

## Consequences

- On a machine loadout set up, rtk no longer prints the false warning. A real "Missing" is hidden the same way, while loadout still provides the hook; once loadout stops providing it, the line goes, so a real "Missing" shows again.
- rtk's other settings are not changed, and loadout runs no `rtk init`.
- The fix is a workaround. When rtk detects plugin hooks (upstream issue #4800), the key and this step can go.

## In the code

- `cli/loadout/rtk_config.py`: `wanted`, `apply`, `_span`, `_has_line`, `_unplaceable`, `_remove`, `_store`
- `cli/loadout/paths.py`: `rtk_config`
- `cli/loadout/apply.py`: `rtk_step`, run by `bootstrap.py`, `update.py`, `configure.py` and `maintenance.py` (the daily sync)
