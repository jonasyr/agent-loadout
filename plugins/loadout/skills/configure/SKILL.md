---
name: configure
description: Conversationally adjust the user's loadout setup — working preferences (answer language, commit style, AI attribution, effort, thinking, ...), global add-ons (plugins, MCP servers) and opt-outs of kit defaults — stored in their personal layer. Use when the user wants to add, remove or change tools or preferences globally (not for a single project; use `loadout profile` there).
---

# Configure loadout

The kit's defaults stay untouched; every choice goes into the user's personal layer through the `loadout configure` engine.

1. Run `loadout configure show` and `loadout configure own` (both, every time). `configure show` gives the current state: each add-on on/off, whether that is the kit default or a personal override, its reason, the id to use with `set` (e.g. `id: mcp addon-dbhub-global`, `id: plugin hookify@claude-plugins-official`), and the working preferences (`id: pref-choice <id>`, current answer and where it was found, the valid options). `configure own` lists the tools the user installed themselves that loadout does not manage, with their options (add `--all` to include the ones they chose to leave on this machine).
2. Ask what the user wants in their own words ("I do a lot of frontend debugging", "I never use Rust", "I want database access everywhere"). Ask one question at a time.
3. Map the answers to concrete changes, using the categories and reasons that `configure show` and the wizard print. Prefer the kit's scoping: suggest a project profile (`loadout profile <name>`) when something is only needed in some repos, and global only when it is needed almost everywhere. Mention context cost for heavy add-ons (e.g. chrome-devtools, many-skill plugins).
4. Present the planned changes as a short list and get a yes.
5. Apply each with the id from `configure show`: `loadout configure set plugin <id> on|off`, `loadout configure set mcp <id> on|off` (the catalog id or the server name, e.g. `dbhub`), or `loadout configure set pref-choice <id> <option>` for a working preference (one of the listed options; a free-text option as `other:<text>`, e.g. `other:French`). Use exactly `on` or `off` for add-ons. Use `loadout configure set pref <key> <json>` only for settings no preference covers. Relay any notes, e.g. missing environment variables and where to put them.
   - For one of the user's own tools: `loadout configure set own <name> global|project:<profile>|leave|remove` (write `<kind>:<name>` when the engine says the name is ambiguous). Before asking, explain the four choices in one line each: global follows them to every machine; project keeps it out of other repos (a personal profile, applied per repo with `loadout profile <name>`); leave keeps it on this machine only; remove takes it away (restorable with `loadout restore`).
   - If `set pref-choice` prints `not effective` (it then exits 1), relay the key and file it names; do not edit them yourself, the user decides (`loadout configure prefs` in a terminal offers to remove it with a backup).
   - `automode_trust generate` drafts the auto mode environment from the user's git repos and needs their confirmation in a terminal: tell them to run `loadout configure prefs` themselves.
6. Tell the user to restart Claude Code or run `/reload-plugins`. The engine does not commit: if `~/.config/loadout/personal` is a git repo and the user agrees, run `git add -A`, `git commit` and `git push` there yourself.

Never edit `~/.claude/settings.json` or `~/.claude.json` directly; the engine keeps kit-managed and personal values apart.
