# Preferences format

Working preferences are a fixed set of questions in `preferences.json` at the kit root. `loadout configure prefs` asks them, `loadout configure set pref-choice ID OPTION` sets one, and `loadout configure show` lists them. The code is `cli/loadout/preferences.py`.

Answers go only into your [personal layer](personal-layer.md): as lines in a managed block of `rules/me.md`, as keys in `settings.json`, or both.

## File structure

`preferences.json` is an object with a `$comment` and a `preferences` list. Each preference has these fields:

| Field | Meaning |
|---|---|
| `id` | Used on the command line: `loadout configure set pref-choice <id> <option>`. |
| `question` | The text of the prompt. |
| `options` | List of `{value, label}`. `value` is what you type; matching is case-insensitive, and a number picks an option by position in the prompt. An option with `"free_text": true` takes text after a colon, for example `other:French`. |
| `default` | The recommended option. A first run (bootstrap's starter layer, `configure --first-run`) starts unanswered questions at this value; without a terminal it takes them silently. |
| `target` | Where the answer is written. See below. |
| `detect` | How an existing answer is recognised. See below. Optional. |
| `generator` | Special handling. The only value is `automode`. Optional. |

Free text must be one line, at most 100 characters, and must not contain `<!--` or `-->`.

### `target`

| Key | Meaning |
|---|---|
| `me_md` | Map of option value to the line written into the managed block of `<personal>/rules/me.md`. `{text}` stands for the free text. `null` means the option writes no line. |
| `setting` | Dotted key in `<personal>/settings.json`, for example `autoMode.environment`. |
| `values` | With `setting`: map of option value to the JSON value to write. `null` removes the key. A value equal to the one in the kit's `settings.base.json` is not written, because the kit default already applies. |

A target may have both `me_md` and `setting`.

### `detect`

Existing answers are read so that re-running changes nothing you already decided.

| Key | Meaning |
|---|---|
| `me_md` | Rules `{pattern, value}`. A case-insensitive regex on a whitespace-normalised free-text line of `me.md` sets the answer to `value`. Read-only: the line is never moved or rewritten. |
| `me_md_report` | Rules like `me_md` that never set an answer. They only name a free-text line that also states one, so that loadout can tell you about it. |
| `settings` | Rules `{key, value}` plus one of `equals`, `contains` or `present`. They recognise legacy settings keys, for example `includeCoAuthoredBy`. |

Where an answer is looked for, in order: the managed block, free text in `me.md`, your personal `settings.json`, the kit defaults, then your existing `~/.claude/settings.json`.

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
| `ai_attribution` | Add AI attribution to commits and PRs? | `off`, `on` | `off` | `me.md` (for `off`) and the `attribution` setting |
| `answer_style` | How should answers be? | `concise`, `detailed` | `concise` | `me.md` |
| `destructive_actions` | Before deleting, overwriting or removing things? | `ask`, `backup` | `ask` | `me.md` |
| `effort_level` | Default effort level? | `low`, `medium`, `high` | `medium` | `effortLevel` |
| `extended_thinking` | Always use extended thinking? | `yes`, `no` | `yes` | `alwaysThinkingEnabled` |
| `agent_push_notifications` | Push notifications when an agent needs you? | `yes`, `no` | `yes` | `agentPushNotifEnabled` |
| `automode_trust` | Draft the auto mode trust environment from your git repos? | `generate`, `skip` | `generate` | `autoMode.environment` |
| `commit_doc_language` | Language of commit messages, code comments and docs? | `english`, `project` | `english` | `me.md` |

`ai_attribution: off` writes `{"commit": "", "pr": "", "sessionUrl": false}` to the `attribution` setting and a "Never add Co-Authored-By" line to `me.md`. `on` removes both and leaves Claude Code's default.

### The auto mode generator

`automode_trust: generate` asks for a code folder (default `~/Documents/Code`) and scans it for git repos. You choose which remote owners are yours; nothing is preselected when several are equally common. The draft is shown in full and saved only after you confirm. It replaces an existing `autoMode.environment` in your personal `settings.json`. If only your own `~/.claude/settings.json` has one, it is not touched; the new lines are saved to your personal layer and the settings merge combines the two lists. Without a terminal this option is skipped, and `set pref-choice ... generate` fails with a message to use `loadout configure prefs` in a terminal.
