# Preferences format

Working preferences are a fixed set of questions in `preferences.json` at the kit root. `loadout configure prefs` asks them, `loadout configure set pref-choice ID OPTION` sets one, and `loadout configure show` lists them. The code is `cli/loadout/preferences.py`.

Answers go only into your [personal layer](personal-layer.md): as lines in a managed block of `rules/me.md`, as keys in `settings.json` (or both), or as keys in `loadout.json`, which only loadout reads.

## File structure

`preferences.json` is an object with a `$comment` and a `preferences` list. Each preference has these fields:

| Field | Meaning |
|---|---|
| `id` | Used on the command line: `loadout configure set pref-choice <id> <option>`. |
| `question` | The text of the prompt. |
| `options` | List of `{value, label}`. `value` is what you type; matching is case-insensitive, and a number picks an option by position in the prompt. An option with `"free_text": true` takes text after a colon, for example `other:French`. |
| `default` | The recommended option. When a new `me.md` is written (bootstrap's starter layer, or the "about you" questions of `configure`, also with `--first-run`), unanswered questions start at this value; without a terminal it takes them silently. |
| `target` | Where the answer is written. See below. |
| `detect` | How an existing answer is recognised. See below. Optional. |
| `agents` | The agents the preference is for, for example `["codex"]`. While all of them are off, it is not asked, not shown by `loadout configure show`, and not applied from an `--answers` file. Optional; without it the preference is for every agent. |
| `generator` | Special handling. The only value is `automode`. Optional. |

Free text must be one line, at most 100 characters, and must not contain `<!--` or `-->`.

### `target`

| Key | Meaning |
|---|---|
| `me_md` | Map of option value to the line written into the managed block of `<personal>/rules/me.md`. `{text}` stands for the free text. `null` means the option writes no line. |
| `setting` | Dotted key in `<personal>/settings.json`, for example `autoMode.environment`. |
| `values` | With `setting`: map of option value to the JSON value to write. `null` removes the key. A value equal to the one in the kit's `settings.base.json` is not written, because the kit default already applies. |

| `loadout` | Dotted key in `<personal>/loadout.json`, for example `codex.serena_approval`. The option value is stored as it is. Used for choices only loadout acts on, such as Codex-only ones. |

A target may have both `me_md` and `setting`. Every change to `loadout.json` keeps its other keys and is backed up first; when the file is not valid JSON, loadout writes nothing (not `me.md` or `settings.json` either) and names the file. Reading it never fails: a broken file counts as no answer.

### `detect`

Existing answers are read so that re-running changes nothing you already decided.

| Key | Meaning |
|---|---|
| `me_md` | Rules `{pattern, value}`. A case-insensitive regex on a whitespace-normalised free-text line of `me.md` sets the answer to `value`. Read-only: the line is never moved or rewritten. |
| `me_md_report` | Rules like `me_md` that never set an answer. They only name a free-text line that also states one, so that loadout can tell you about it. |
| `settings` | Rules `{key, value}` plus one of `equals`, `contains` or `present`. They recognise legacy settings keys, for example `includeCoAuthoredBy`. |

Where an answer is looked for: for a preference with a `setting` target, the settings come first, in order your personal `settings.json`, the kit defaults, then your existing `~/.claude/settings.json`; a value set there wins over `me.md`. Otherwise (and when no setting is set) the answer comes from the managed block, then free text in `me.md`. For a `loadout` target the answer comes from `loadout.json` only.

## The managed block

Text answers live in one block of `rules/me.md`:

```
<!-- loadout:preferences:start -->
- Language: always answer in English.
- Commits: use Conventional Commits (`type(scope): subject`).
<!-- loadout:preferences:end -->
```

The markers are exactly `<!-- loadout:preferences:start -->` and `<!-- loadout:preferences:end -->`, each on a line of its own. There must be one of each, start first. If they are unbalanced, duplicated or out of order, loadout refuses to write and writes nothing; fix them by hand. When the last line leaves the block, the markers go with it.

Your own lines outside the block are never moved or rewritten. Two things can happen to them:

- When you change an answer that one of your lines also states, loadout names that line. In a terminal it offers to remove it, with a backup.
- A line that is exactly one of the kit's own preference lines moves into the block, but only when the block is written anyway.

The file keeps its line endings (LF or CRLF). A backup is made before every change.

If a setting or a `me.md` line still contradicts an answer after it was written, for example a legacy `includeCoAuthoredBy` when `ai_attribution` is `off`, loadout prints `not effective` with the key or line, and `loadout configure set pref-choice` exits with 1.

## The preferences

| id | Question | Options | Default | Written to |
|---|---|---|---|---|
| `answer_language` | Which language should Claude answer in? | `match`, `english`, `german`, `other:<text>` | `match` | `me.md` |
| `commit_style` | Which commit message style? | `conventional`, `free` | `conventional` | `me.md` |
| `ai_attribution` | Add AI attribution (Co-Authored-By, PR footer) to commits and PRs? | `off`, `on` | `off` | `me.md` (for `off`) and the `attribution` setting |
| `answer_style` | How should answers be? | `concise`, `detailed` | `concise` | `me.md` |
| `destructive_actions` | Before deleting, overwriting or removing things? | `ask`, `backup` | `ask` | `me.md` |
| `effort_level` | Default effort level? | `low`, `medium`, `high` | `medium` | `effortLevel` |
| `extended_thinking` | Always use extended thinking? | `yes`, `no` | `yes` | `alwaysThinkingEnabled` |
| `agent_push_notifications` | Push notifications when an agent needs you? | `yes`, `no` | `yes` | `agentPushNotifEnabled` |
| `automode_trust` | Draft the auto mode trust environment from your git repos? | `generate`, `skip` | `generate` | `autoMode.environment` |
| `commit_doc_language` | Language of commit messages, code comments and docs? | `english`, `project` | `english` | `me.md` |
| `codex_serena_approval` | Should Codex approve Serena's tools automatically? | `ask` (ask each time), `approve` (approve automatically) | `ask` | `loadout.json` (`codex.serena_approval`); Codex only |
| `cbm_auto_index` | Should codebase-memory index a new git repo by itself the first time a session opens it? | `on`, `off` | `on` | codebase-memory's own `auto_index` setting; both agents ([below](#codebase-memorys-auto_index)) |

With Codex on, `effort_level` also sets `model_reasoning_effort` and `agent_push_notifications` sets `tui.notifications` in `~/.codex/config.toml`. The preferences written to `me.md` reach Codex through the `AGENTS.md` block. The other settings (`extended_thinking`, `automode_trust`) apply to Claude Code only. See [personal-layer](personal-layer.md).

### Serena's approvals in Codex

Claude Code approves Serena's tools through loadout's hook; Codex asks before every `serena_repl` call. `codex_serena_approval` decides that for Codex. The question states the trade-off: `serena_repl` runs code in Serena's process.

- It is asked only while Codex is on: with the other preferences when bootstrap creates a new personal layer, when you answer yes to bootstrap's `Customize preferences and global add-ons now?`, and in `loadout configure prefs`. A personal layer cloned onto a new machine, or Codex turned on later, gets no question of its own: the default `ask` applies until you change it with `loadout configure prefs` or `loadout configure set pref-choice codex_serena_approval approve`.
- `approve` writes `approval_mode = "approve"` into `[mcp_servers.serena.tools.serena_repl]` in `~/.codex/config.toml`, only while the `serena` table is loadout's. When that section is missing, loadout adds it at the end of the file. The line and the header loadout added are recorded as loadout's.
- `ask` writes nothing, and removes only the line loadout wrote (and the header, when loadout added it and nothing else is in the section). A line you changed or wrote yourself stays.
- With your own Serena table (for example from `serena setup codex`), loadout changes nothing there. With `approve` it says once: `Serena is your own server in config.toml; to approve its tools, choose "Always allow" in Codex`. When loadout's `serena` table becomes yours, its approval line becomes yours too and stays as it is.

The decision and its reasons: [ADR 0036](../adr/0036-codex-tool-approvals-and-serena-approval.md).

`ai_attribution: off` writes `{"commit": "", "pr": "", "sessionUrl": false}` to the `attribution` setting and a "Never add Co-Authored-By" line to `me.md`. `on` removes both and leaves Claude Code's default.

In Codex the `me.md` line reaches the agent through the instruction block, but there is no `attribution` key: Codex adds `Co-authored-by: Codex` to commits when your ChatGPT account has commit attribution turned on, an account setting that loadout cannot change. See [Use loadout with Codex](../how-to/codex.md#what-stays-different).

### codebase-memory's auto_index

`cbm_auto_index: on` runs `codebase-memory-mcp config set auto_index true`, so codebase-memory indexes a new git repo at its first session (up to its `auto_index_limit`, 50 000 files); afterwards its watcher or [loadout's refresh](hooks.md#the-code-graph-refresh) keeps it current. It applies to both agents and needs `codebase-memory-mcp` on `PATH`; with it missing, or with both agents off, nothing happens.

- loadout sets the value only from `false` to `true`. It records that in `cbm-auto-index.json` in [its state folder](state-and-sync.md), and puts the undo (`config set auto_index false`) in the backup first, so `loadout restore` replays it. Restore runs exactly these two `config set auto_index` forms and nothing else.
- A value you set back to `false` after loadout set it `true` stays yours, for good: loadout records that (`cbm-auto-index.json` holds `yours`), `loadout check` shows `off (yours)`, and loadout never changes `auto_index` again, whatever you later set or answer. A failed `config set` leaves no undo step behind.
- The answer `off` reverts only loadout's own change. A `true` you set yourself is left alone.
- codebase-memory's default is `false`. A `false` you set before loadout therefore looks like the default, and loadout turns it on once (undoable).
- If `loadout.json` cannot be read, the answer is unknown and nothing changes.
- When it is applied: by `loadout bootstrap`, `loadout update` (again), the daily sync after a pull ([state and sync](state-and-sync.md#the-daily-sync)), and at once by `loadout configure set pref-choice cbm_auto_index on|off`.
- The `codebase-memory auto_index` row of `loadout check` reads `on`, `off (yours)`, `off (your answer)` or `off (loadout turns it on at the next update)`.

The decision: [ADR 0039](../adr/0039-serena-remind-tools-load-upfront-cbm-refresh.md).

### The auto mode generator

`automode_trust: generate` asks for a code folder (default `~/Documents/Code`) and scans it for git repos. You choose which remote owners are yours; nothing is preselected when several are equally common. The draft is shown in full and saved only after you confirm. It replaces an existing `autoMode.environment` in your personal `settings.json`. If only your own `~/.claude/settings.json` has one, it is not touched; the new lines are saved to your personal layer and the settings merge combines the two lists. Without a terminal this option is skipped, and `set pref-choice ... generate` fails with a message to use `loadout configure prefs` in a terminal.
