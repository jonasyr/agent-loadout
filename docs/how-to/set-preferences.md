# Set your working preferences

Use this page to change how your agent (Claude Code, Codex or both) works for you everywhere: answer language, commit style, AI attribution, effort level and so on. Answers go only into your personal layer. The list of preferences, their options and defaults are in [preferences format](../reference/preferences-format.md#the-preferences).

## In the terminal

Ask all the preference questions. Enter keeps the current answer:

```bash
loadout configure prefs
```

List every preference with its id and current answer:

```bash
loadout configure show
```

Set one preference without questions:

```bash
loadout configure set pref-choice effort_level high
```

Set any key in your personal `settings.json` directly. The value is parsed as JSON, and stored as a string if that fails:

```bash
loadout configure set pref effortLevel '"high"'
```

Run `loadout configure` with no arguments for the full wizard, which also offers global add-ons. All forms are in the [CLI reference](../reference/cli.md#loadout-configure).

## By asking your agent

Say what you want in Claude Code or Codex, for example "answer in German" or "turn off AI attribution". The loadout plugin's `configure` skill runs the same commands after your yes ([Ask your agent about loadout](ask-about-loadout.md)).

## What to expect

- Text answers become lines in a block of `rules/me.md` between `<!-- loadout:preferences:start -->` and `<!-- loadout:preferences:end -->`. Other answers go into your personal `settings.json`. AI attribution goes into both. See [the managed block](../reference/preferences-format.md#the-managed-block).
- Where they take effect differs by agent. Claude Code reads `me.md` from `~/.claude/rules/personal` and gets the settings merged into `~/.claude/settings.json`. Codex reads `me.md` through the block in `~/.codex/AGENTS.md`, and gets only the effort level and push notifications from the settings (`model_reasoning_effort`, `tui.notifications` in `~/.codex/config.toml`). Other settings have no effect there, and commit attribution in Codex is an account setting. The table is in [Personal layer](../reference/personal-layer.md#files); the attribution detail in [preferences format](../reference/preferences-format.md).
- Your own lines in `me.md` are read to recognise answers you already gave, but never moved or rewritten. When you change an answer that one of your lines also states, loadout names the line and, in a terminal, offers to remove it (with a backup).
- Values in your existing `~/.claude/settings.json` (Claude Code) count as answers too, so re-running changes nothing you already decided.
- If a setting, a legacy `includeCoAuthoredBy`, or one of your `me.md` lines (for example "never add Co-Authored-By") still contradicts a choice, loadout prints `not effective` and names it instead of claiming success. `set pref-choice` then exits with 1.
- A first run (bootstrap's starter layer, `configure --first-run`) starts unanswered questions at the recommended defaults. Bootstrap first shows all recommended answers on one screen: Enter takes them (auto mode trust is not drafted then), `n` asks each question. Without a terminal it takes them silently.
- The auto mode preference drafts a trust environment from the git remotes under your code folder (default `~/Documents/Code`). You choose which owners are yours, see the full draft and must confirm it. It needs a terminal. See [the auto mode generator](../reference/preferences-format.md#the-auto-mode-generator).

To sync your answers across machines, make the personal layer a private git repo: [Sync](../reference/personal-layer.md#sync). `loadout configure` offers to commit and push after a change; `configure set ...` only lists pending changes.
