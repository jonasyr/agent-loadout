---
name: configure
description: Answer any question about loadout (agent-loadout) from its docs, and make changes to the user's loadout setup through the `loadout` CLI - preferences, plugins, MCP servers, own tools, agents (Claude Code, Codex), project profiles, checks, updates, restore. Use whenever the user asks how loadout works or wants their setup changed.
---

# Configure loadout

The one place for loadout questions and changes. Never edit `~/.claude/settings.json`, `~/.claude.json`, `~/.codex/config.toml` or the personal layer's files by hand: the `loadout` commands keep kit and personal values apart and record undo steps.

## Answer a question

1. Find the docs: `loadout kit-path` prints the kit's folder; open its `docs/README.md` (the map: which page answers which question), then read only the page that answers this question. Without loadout, read the same paths in https://github.com/jonasyr/agent-loadout.
2. Answer from that page, in short, and end with the page's title and path (for example "Undo what loadout changed, `docs/how-to/undo-and-restore.md`") so the user can read on. When the user's own state matters ("is X on for me?"), run `loadout configure show`, `loadout configure own` or `loadout check` first, all read-only.
3. If the docs do not answer it, say so; do not guess how loadout behaves.

## Other changes

Map the request to a command, show the planned commands as a short list, and run them only after a yes. Your shell has no terminal, so a command that would ask again gets its answer as a flag (the user's yes is that answer):

| Request | Command |
|---|---|
| Turn an agent on or off | `loadout configure set target <claude or codex> <on or off>` |
| Tools for one repo | `loadout profile <name>` in that repo; a new repo: `loadout init <names> --yes` (it also runs `git init` when the folder is not a repo yet; say so in the plan) |
| Is everything working? | `loadout check` |
| Do my agents use Serena, the graph or Context7? | The `loadout:usage` skill, which reads `loadout usage --json` (read-only, counts only) |
| Review the existing setup | `loadout adopt` (a dry run); after a yes, `loadout adopt --apply --groups <the agreed groups>` (add `,secrets` only when the user agreed to move the plaintext secrets the dry run listed) or `--own NAME=CHOICE`; when the groups include `update` or `install`, add `--yes` (naming `secrets` is its consent) |
| Update tools | `loadout update` lists what is outdated; after a yes, `loadout update --yes` |
| Undo a change | `loadout restore --list`, then `loadout restore <dir>` after a yes |
| They installed a tool themselves (`npx ...`, `claude mcp add`, `/plugin install`) and ask what now | Answer from "You installed a tool yourself" in `docs/how-to/your-own-tools.md`; run `loadout configure own` to show where it is and its options, then decide it as under "Preferences, add-ons and your own tools" below |
| Create a skill of their own | Ask where it should live (every machine: global; some repos: project:<profile>; this repo for everyone: repo), then `loadout configure new skill NAME --to ... --description "..."`; then fill in the SKILL.md it printed. Never write into the skills folders directly. |

When no command covers the request, say which doc page describes the manual way and let the user decide; never edit the files yourself.

## Preferences, add-ons and your own tools

The kit's defaults stay untouched; every choice goes into the user's personal layer through the `loadout configure` engine.

1. Run `loadout configure show` and `loadout configure own` (both, every time). `configure show` gives the current state: each add-on on/off, whether that is the kit default or a personal override, its reason, the id to use with `set` (e.g. `id: mcp addon-dbhub-global`, `id: plugin hookify@claude-plugins-official`), and the working preferences (`id: pref-choice <id>`, current answer and where it was found, the valid options). `configure own` lists the tools the user installed themselves that loadout does not manage, with their options (add `--all` to include the ones they chose to leave on this machine).
2. Ask what the user wants in their own words ("I do a lot of frontend debugging", "I never use Rust", "I want database access everywhere"). Ask one question at a time.
3. Map the answers to concrete changes, using the categories and reasons that `configure show` and the wizard print. Prefer the kit's scoping: suggest a project profile (`loadout profile <name>`) when something is only needed in some repos, and global only when it is needed almost everywhere. Mention context cost for heavy add-ons (e.g. chrome-devtools, many-skill plugins).
4. Present the planned changes as a short list and get a yes.
5. Apply each with the id from `configure show`: `loadout configure set plugin <id> on|off`, `loadout configure set mcp <id> on|off` (the catalog id or the server name, e.g. `dbhub`), or `loadout configure set pref-choice <id> <option>` for a working preference (one of the listed options; a free-text option as `other:<text>`, e.g. `other:French`). Use exactly `on` or `off` for add-ons. Use `loadout configure set pref <key> <json>` only for settings no preference covers. Relay any notes, e.g. missing environment variables and where to put them.
   - For one of the user's own tools: `loadout configure set own <name> global|project:<profile>|leave|remove`. Use the name as `configure own` prints it (a hook is `Event:matcher`; write `<kind>:<name>` or add `#n` when the engine says the name is ambiguous). Offer only the choices listed under `options:` for that item. Before asking, explain them in one line each: global follows them to every machine; project keeps it out of other repos (a personal profile, applied per repo with `loadout profile <name>`); leave keeps it on this machine only and loadout stops asking about it; remove takes it away (restorable with `loadout restore`).
   - If `set own` exits 1, the item was not recorded, or recorded but not active on this machine (see the `skipped:`/`failed:` line); relay the reason from that line. Do not retry the same choice; the user decides what to change (for example move a secret to `secrets.env`).
   - If `set pref-choice` prints `not effective` (it then exits 1), relay the key and file it names; do not edit them yourself, the user decides (`loadout configure prefs` in a terminal offers to remove a contradicting settings key with a backup; a contradicting `me.md` line the user edits by hand).
   - `automode_trust generate` drafts the auto mode environment from the user's git repos and needs their confirmation in a terminal: tell them to run `loadout configure prefs` themselves.
6. Tell the user to restart the agents that are on (Claude Code: or run `/reload-plugins`). The engine does not commit, and global and project choices reach other machines only once the personal layer is committed and pushed: remind the user of this. Never commit or push the personal layer (`~/.config/loadout/personal`, or `$LOADOUT_PERSONAL` when set) yourself: if it is a git repo, tell the user to run `loadout configure prefs` in a terminal (Enter keeps each answer); it lists the changes and offers to commit and push, and refuses while a private file (a `*.env` file, a key or credential) would be committed.

The engine keeps kit-managed and personal values apart; the same applies to Codex, where `loadout configure` writes `~/.codex/config.toml` itself.
