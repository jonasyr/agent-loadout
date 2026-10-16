# Repos for chosen agents, shared repos, and changes a careful user can trust: design

Status: approved in chat 2026-10-16 (Parts 0–6). Goal from the user: setup and daily use work perfectly and are easy, through an agent that follows the repo's docs and the CLI, or through the CLI directly; especially for Codex only on Windows/WSL with VS Code. A repo can be for chosen agents (some Codex only). A repo shared by two loadout users works for both: the user (Claude Code and Codex) and a friend (Codex only, Windows/WSL, VS Code). A careful, skeptical user who documented their setup and their scientific repos must always know exactly what loadout will change, agree to it, and be able to undo it; nothing they set up is changed behind their back.

## Facts this rests on (2026-10-16)

- Codex reads repo skills from `.agents/skills` in every folder from the working directory up to the repo root, and follows symlinked skill folders (learn.chatgpt.com/docs/build-skills). Claude Code reads repo skills only from `.claude/skills` and follows a linked skill folder there (ADR 0027).
- OpenAI's recommended Windows setup for Codex with WSL: repos in the Linux home, VS Code opened from WSL (`code .`, a Remote-WSL window), `chatgpt.runCodexInWindowsSubsystemForLinux: true`; `/mnt/c` is slower and has "symlink and permission issues" (learn.chatgpt.com/docs/windows/wsl).
- Git with `core.symlinks=false` (the default on Windows without Developer Mode) checks a committed link out as a plain file whose content is the target path.
- Today (code, 2026-10-16):
  - which agents loadout sets up is global only (`targets.json`); ADR 0027 makes repo files follow those agents; loadout keeps no list of repos.
  - `loadout profile` merges into the repo's `.claude/settings.json` and `.mcp.json` with `deep_merge` (scalars: the profile wins; lists: union) and re-serializes the whole file; no backup, `loadout restore` does not undo it (docs/reference/profile-format.md). `--dry-run` does not show the settings change.
  - the repo's `.codex/config.toml` is append-only (owned text, same-name tables stay).
  - `.gitignore`: a new `# loadout` header on each run that adds a line.
  - `codex_gate` returns before the VS Code offer when `--codex-side wsl` is given (`cli/loadout/bootstrap.py`); `loadout check` has no VS Code row.
  - a committed skill link that is a plain file in the checkout is reported as "not a link to …, left as is" and the run exits 1; not detected as a broken checkout.
  - `profiles.link_skills` builds link targets with `os.path.join`, so on native Windows the target uses `\`; what Git stores for it is not verified.
  - `loadout restore` without a path lists backups newest first (path, date, steps, restored state, description); the user copies a path to restore.

## Decisions (from the user)

1. A repo's agents are chosen per repo, committed in the repo; the user's global setup is not changed by it.
2. In a repo for both agents, skills keep one real folder and a committed link; a link a checkout turned into a plain file is detected and the fix printed, never silently repaired.
3. Repo JSON files get a three-way merge against a committed record of what each profile wrote: profile updates apply by themselves, a teammate's change is kept and asked about once.
4. Every repo write is previewed, agreed to, backed up and undoable (Part 0). A repo can switch loadout off (`manage: false`).
5. Codex only on Windows/WSL with VS Code follows OpenAI's recommended setup, end to end, through the agent and the CLI.
6. `loadout restore` offers a numbered list of recent backups with their age and picks one.
7. The same careful-user audit of the global flows (bootstrap, adopt, the daily sync, configure, rule updates that change how agents work) is the next spec, not this one.

## Part 0: the careful user (applies to every part)

- **Preview first.** `init`, `profile` and `configure new skill --to repo` first build a plan: each file, each entry, as a diff (created files listed with their content size; JSON and TOML as added/changed keys; text files as unified diff lines). In a terminal: the plan, then `Apply these changes? [y/N]`. Without a terminal: the plan, and nothing is written unless `--yes` is given. `--dry-run` prints the same plan (settings included) and exits 0. The plan and the write come from one computation, so what is shown is what is written.
- **One-line reasons.** Each planned change names its source in one line (`profile web: enables the Playwright plugin for UI checks`, `init: AGENTS.md for agents that read it`). Profiles gain an optional `why` per entry; without one, the line names the profile and the entry.
- **Undo for every repo write.** Before writing, loadout saves a copy of every repo file it changes and records every file and folder it creates (the existing `Backup` with `save_copy`/`record_created`), and ends with `undo: loadout restore <dir>`. Restore puts changed files back byte for byte and removes created ones (a created folder only when it is empty again or holds only what loadout created). The backup's manifest records the repo path.
- **The user's bytes stay theirs.** loadout changes only entries it can name. JSON: indentation (detected), key order of existing keys and line endings (LF/CRLF) are kept; new keys are appended at the end of their object. A run that changes nothing does not touch the file (mtime unchanged). A file loadout cannot parse, or one with comments it cannot keep (JSONC), is left byte for byte and the entries to add by hand are printed.
- **Nothing silent.** In a repo where nobody ran `loadout init` or `loadout profile`, loadout writes nothing, not even `.loadout.json`. The session hook and the daily sync never write repo files.
- **Hands off.** `.loadout.json` with `"manage": false`: every loadout command that would write in that repo prints its plan headed `manage is false in .loadout.json: nothing written` and exits 0. Agents get the same answer through the CLI.
- **Explain.** `loadout explain <file>` (read-only) lists the entries in a repo file that loadout wrote, from which profile, and whether each still has loadout's value.

## Part 1: the repo's agent choice

- `.loadout.json` at the repo root, committed: `{"agents": ["codex"]}` (`"claude"`, `"codex"`, or both). Unknown keys are kept on rewrite; an invalid file stops every repo-writing command with the reason (`.loadout.json: agents must be a list of "claude" and "codex"`), before anything changes.
- `loadout init --agents claude|codex|claude,codex` writes it. In a terminal without the flag, init asks (default: the agents on for this user). Without a terminal: the user's agents, and the plan says so.
- With the file, `init`, `profile` and `configure new skill --to repo` write the files of the repo's agents, whichever agents are on for the user running it. A Codex-only user in a both-agents repo writes Claude Code's repo files too (they are shared repo files; ADR 0027's rule about the user's own agent folders is unchanged). A user with both agents on writes no Claude Code files in a Codex-only repo.
- Without the file: the user's agents, as today; the first `init` or `profile` adds `.loadout.json` to its plan.
- Changing the agents (`init --agents …` in a repo that has the file): an added agent gets its missing files and skill links; a removed agent's files stay, and the plan lists them as no longer needed (removing them is the user's).
- Opening a Codex-only repo in Claude Code changes nothing in the user's global setup.
- ADR 0030 "Repo files follow the repo's agents" supersedes ADR 0027's decision line "A repo gets the files of the agents that are on (`targets.json`)"; the rest of 0027 stands.

## Part 2: shared repos, three-way

- `.loadout.json` records what each profile wrote: `"profiles": {"web": {".claude/settings.json": {"enabledPlugins/X": true, "permissions/allow": ["Bash(npm test)"]}, ".mcp.json": {…}}}` (JSON pointer–style paths; lists recorded as the entries loadout added).
- Re-running a profile compares, per entry, the recorded value (base), the file's value (theirs) and the profile's value (new):
  - file == base, new differs: a profile update; applied, the plan says `update`.
  - file differs from base: someone changed it; kept. In a terminal the plan groups these and asks once: `This repo differs from profile web in N entries: … Use the profile's values for these? [y/N]`. Without a terminal they are listed; `--take-profile` applies them.
  - a list entry loadout added that is gone from the file: kept removed (a decision). A list entry new in the profile: added.
  - an entry missing from the file and not in the record: added.
- No record (a repo from before this change, or a profile never applied): add-only (only missing keys; an existing key with another value kept and reported); the record is created from what was added.
- `.codex/config.toml` keeps its owned-text rule; its entries are recorded the same way so `explain` covers them.
- `.gitignore`: one `# loadout` header; new lines go under it.
- Two-user correctness: after any sequence of runs by users with different agents, each user's agents' files are complete and no run reverses an entry a person changed without a yes.

## Part 3: skill links a checkout broke

- Detection in `loadout check` (inside a git repo), `init` and `profile`: a path git records as a link (`git ls-files -s`, mode `120000`) under `.claude/skills` or `.agents/skills` that is a regular file in the working tree. One line per repo: `N skill links in .agents/skills are plain files in this checkout (Git without symlinks), so Codex does not see these skills`, then the fix: best, Codex in WSL with the repo in the Linux home (Part 4); otherwise turn on Windows Developer Mode, `git config core.symlinks true`, `git checkout -- .agents/skills .claude/skills`. loadout prints these and runs none of them; it never replaces the plain files.
- Such entries no longer make `profile` exit 1; they are reported as this one problem.
- Native Windows link targets: a CI test on the Windows runner creates a repo skill link through `link_skills`, commits it, and reads the stored target (`git cat-file -p`). If it contains `\`, loadout creates links with `/` targets on Windows; the test pins the result either way.
- Docs: troubleshooting row; `setups.md` row "A repo shared with a teammate on Windows".

## Part 4: Codex only on Windows/WSL with VS Code

- Main path: loadout and Codex in WSL, repos in the Linux home, VS Code opened with `code .` from WSL, the extension in WSL mode.
- Bootstrap: with `--codex-side wsl` in a terminal, the VS Code offer is asked too. New flag `--vscode-wsl`: the same edit as answering yes (only that key; copy saved first; `loadout restore` undoes it); for agents and scripts. Without the flag and without a terminal, bootstrap prints the manual step (also with `--codex-side wsl`).
- `loadout check` in WSL with Codex set up in WSL: a `VS Code` row warns when `settings.json` exists and the setting is not `true` (or not set while the Codex extension is installed), with the fix (`--vscode-wsl`, or the manual step).
- Codex on Windows on a `\\wsl$` repo is not detectable from WSL; the docs and the `/mnt` note say to open repos with `code .` from WSL.
- `/hooks` and project trust in the VS Code extension: the live tour finds out whether the extension offers both or a one-time `codex` run in the WSL terminal is needed; bootstrap's "Still to do", `check` and the docs then name that exact place.
- One walkthrough, "Codex only on Windows with VS Code", in `setups.md` and the agent page, same steps in the same order: WSL 2, bootstrap (side, VS Code switch), `codex login` in WSL, `/hooks`, the first repo (`loadout init --agents codex`), `loadout check`.

## Part 5: proof

- CI (Linux, Windows, WSL2), `fake_home`/`fake_runner`, a test file per part:
  - Part 1: Codex-only repo gets no Claude Code files from a both-agents user; a Codex-only user in a both-agents repo writes Claude Code's repo files; changing agents removes nothing; invalid `.loadout.json` stops before any change; `manage: false` writes nothing.
  - Part 2: profile update applied; teammate change kept, asked once, `--take-profile`; removed list entry stays removed; no-record add-only; byte-for-byte formatting (indent 4, CRLF, no-op run keeps mtime); unparsable file untouched.
  - Part 0: plan equals what is written; no terminal and no `--yes` writes nothing; restore returns every repo file exactly and removes created ones; `explain`.
  - Part 3: plain-file link detected and the fix printed, nothing run; Windows runner pins the stored link target.
  - Part 4: `--vscode-wsl` edits one key, backup, restore; `check`'s VS Code row.
  - Part 6: the list, the pick, the confirm, the filters, no picking without a terminal.
- Two-user simulation test: two fake homes (both agents; Codex only, WSL) on one git repo: init, profile, commit, the other pulls and re-runs, a teammate edits a value, the other re-runs; after each step both users' agents' files are complete and nothing a person changed was reversed.
- Live tour (real Codex, the user's login in an isolated test home, never the real `~/.codex`): Codex only in WSL with VS Code, through the agent page and through the CLI; Serena already set up (`serena setup codex`); a Codex-only repo on the both-agents machine; the shared repo with both setups; a documented repo with `manage: false` (nothing changes). Each: bootstrap, `/hooks`, a real prompt that uses Serena and the graph, `loadout check` clean. Findings become fixes with tests. Then a guided first install on the friend's machine.

## Part 6: restore picks a backup

- In a terminal, `loadout restore` without a path shows the last 10 backups, numbered: age (`2 hours ago`) and date, the command that made it, where (`home` or `repo <path>`), what it holds (`3 files, 2 commands`), and `restored <date>` when restored. Prompt: `Restore which? [1-10, m = more, Enter = cancel]`.
- After the pick: exactly what will go back (each file, each undo command), then `Restore this? [y/N]`. The restore is backed up as today.
- `--repo PATH` filters to one repo's backups; `--last` takes the newest; `--list` prints the list (agents, scripts). Without a terminal nothing is picked: a path or `--last` is needed.

## PRs

1. Parts 0 and 1: plan/preview/apply engine for repo writes, repo backups and restore, `.loadout.json` with `agents` and `manage`, `explain`, ADR 0030.
2. Part 2: the three-way repo merge and the record.
3. Part 3: broken-link detection and the Windows link-target test.
4. Part 4 and Part 6: VS Code flag and check row; the restore picker.
5. Docs (`setups.md`, the agent page walkthrough, troubleshooting, reference pages) and the live tour with its fixes.

## Not in scope

- The global-flow audit (decision 7; next spec).
- Turning loadout's global rules, hooks or tools off per repo.
- Repairing links or changing a user's git config.
- Writing the other side's Codex home (ADR 0029).
