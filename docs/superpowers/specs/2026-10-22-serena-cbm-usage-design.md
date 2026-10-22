# Serena and codebase-memory get used, in sessions and subagents

Status: draft for review, builder check done (user's answers 2026-10-22). Evidence: the debugging findings under the BIG Serena/cbm entry in `.superpowers/handoff/2026-10-13-hardening-backlog.md` (git-ignored), from 14 days of transcripts on the maintainer's machine (Claude Code 2.1.305, Serena 2.1.0, codebase-memory-mcp 0.12.1).

## Why

The user, verbatim: "it still doesn't reliably work at all that they are being used in the session consistently without the user constantly reminding it … doesn't really work at all in subagents … HUUUGE problem". Their goal: "Hauptsache das funktioniert überall danach" (above all, it has to work everywhere afterwards).

The measured causes, strongest first:
1. **Deferred tools.** Claude Code defers MCP tool definitions. A subagent has to call ToolSearch before it can call `find_symbol` or `search_graph`. Only 27 of 585 subagents ever searched for them.
2. **Hints that never block are ignored.** loadout's tool hint (ADR 0026) was shown 109 times. Only 3 times did Serena, the graph or ToolSearch follow within the next 6 calls.
3. **Dead hook paths.**
   - On Linux, macOS and WSL, Claude Code has no Grep or Glob tools; search runs through Bash (12 Grep calls vs 11 217 Bash calls in subagents). So codebase-memory's `hook-augment` on `Grep|Glob` almost never runs.
   - tool_hint recognises only about 12% of shell grep/rg lines.
4. **Use follows the prompt.** In 23 of 34 subagents that used the tools, the parent's prompt named them. The repo's `codex-reviewer` agent (67 runs) cannot use MCP at all (`tools: Read, Grep, Glob, Bash`).

Serena's docs already say this for Claude Code: dynamic tool loading makes agents skip Serena, and Serena "strongly recommends" its hooks, `remind` included. loadout dropped `remind` (ADR 0008).

**Goal:** in every setup loadout supports, an agent or subagent that drifts into grep/Read on code gets Serena's own reminder. It can call Serena and codebase-memory directly without a ToolSearch step. `loadout usage` shows the change.

## Decisions (the user's, 2026-10-22)

1. **Use Serena's hooks as Serena documents them, for Claude Code and Codex.** For Claude Code that means `remind`, `auto-approve`, `activate` and `cleanup` (docs: oraios.github.io/serena/02-usage/030_clients.html).
   - `remind` is new for Claude Code. It denies the 3rd grep, the 3rd code-file read or the 4th mixed call without a Serena symbolic tool in between, once, and then stays silent for 2 minutes.
   - Codex already has all six documented hooks (ADR 0028); this PR keeps them and checks they still match Serena's current docs.
   - A new ADR supersedes ADR 0008's "remind is dropped" and ADR 0026's never-block rule for code searches. Its evidence: the hint numbers above.
2. **`alwaysLoad: true` for both plugin servers** (`serena`, `codebase-memory-mcp` in `plugins/loadout/.mcp.json`). Measured cost: about 50 000 characters of tool definitions (Serena 24 tools, codebase-memory 17), roughly 12-13k tokens in every session and subagent context.
   - A working preference turns it off. The builder names it and wires it through `loadout configure`, following how other preferences reach the plugin's files. If a plugin's `.mcp.json` cannot be varied per user, the builder says so and the preference is dropped (`alwaysLoad` stays on).
3. **loadout's own search hint goes; the docs hint stays.** `tool_hint.py` stops emitting `SEARCH_HINT`/`SEARCH_HINT_PLAIN`, for Claude Code and Codex (in Codex, Serena's `remind` already covers shell searches). It keeps the Context7/Microsoft Learn hint for library-doc web lookups. `loadout usage` loads tool_hint's search parser (`_hint_rules`) to count symbol greps, so the parser moves into a module of its own that `usage` keeps using. It is improved there: alternation patterns, and every search in a compound line, so it is no longer at about 12%. The "before" numbers are recomputed with the improved parser, so before and after compare like with like. The hook's search counting and PostToolUse reset go. `loadout usage` counts Serena's denials as hints shown, from Serena's hook state or from the transcripts (builder's call how).
4. **No system-prompt override.** Serena also suggests `claude --system-prompt="$(serena prompts print-cc-system-prompt-override)"`. Not now: first measure whether `alwaysLoad` + `remind` suffice. It is named in the docs as the next lever.
5. **codex-reviewer** (`.claude/agents/codex-reviewer.md`) gets Serena's and codebase-memory's read-only tools in its `tools:` list, and its prompt says when to use them. Shipping it optionally in the kit is a separate backlog item.

6. **First index by codebase-memory itself** (user, 2026-10-22). It is not a reindex hook: cbm's watcher (`auto_watch`, on by default) already re-indexes the session's git project after changes, and Serena needs no index.
   - The gap is a repo never indexed (`auto_index` is off by default).
   - A working preference, on by default, sets cbm's own `auto_index true` through `codebase-memory-mcp config set`. cbm then indexes a new git project at its first session, up to `auto_index_limit` (50 000 files, unchanged).
   - The old value is recorded and `loadout restore` puts it back. A value the user set themselves stays theirs (the existing own-value rule).
   - The setting is per account, so it covers Claude Code and Codex alike.
   - Builder: run it through `runner.run` as a recorded, undoable command, and include it in `check` (cbm's `config get auto_index`).

7. **Refresh at logical change points** (user, 2026-10-22: "Serena and codebase should reindex themselves at logical change thresholds so they don't sabotage themselves with stale indexes after work is done").
   - **Why cbm's watcher is not enough.** It watches only the git project an open MCP session is rooted in. A repo indexed from another session or with `cli` is not watched, nor is a non-git folder. There is also a poll lag between an edit and the next query.
   - **Triggers** (author's thresholds, the user can change them):
     - (a) The end of a turn (`Stop`, and `SubagentStop` for a subagent's own work) when code files changed since the last refresh.
     - (b) After a shell git command that rewrites the working tree: `checkout`, `switch`, `pull`, `merge`, `rebase`, `reset`, `stash pop`/`apply`, `cherry-pick`, `revert`.
     - (c) Within a long turn, after 20 changed code files since the last refresh.
   - **What changed** comes from the edit tools' PostToolUse (Claude Code `Write|Edit|MultiEdit`, Codex `apply_patch`) plus a cheap snapshot (`git status --porcelain` and HEAD) for shell edits and git commands (builder's call how).
   - **codebase-memory.**
     - An incremental `index_repository` of the session's repo, in the background, detached, and never blocking the agent.
     - Only for a repo cbm has already indexed; a new repo is decision 6's job.
     - At most one refresh per repo at a time, under a lock in loadout's state folder.
     - A refresh cbm refuses ("another index operation … is active") is dropped silently. The next trigger retries.
     - Run through `codebase-memory-mcp cli index_repository` with the same options the repo was indexed with, so it does not hit that refusal. The builder reads them from `index_status`.
   - **Serena needs none (verified 2026-10-22, Serena 2.1.0, Python).** `find_symbol` saw each of these at once, without a reindex:
     - a function appended outside Serena;
     - a new file;
     - a deleted file.

     The builder repeats the check for TypeScript (the second language the tests cover). If TypeScript goes stale, that becomes a finding for the user; it is not silently added. `docs/` records the result.
   - **Both agents.** Claude Code and Codex use the same triggers through their own hooks. The refresh itself is one `loadout` subcommand that both call, run through `run.sh`, so the rule lives in one place.
   - **No refresh when** the binary is missing, the server is not available (as defined under "Every setup variation"), or the folder is no repo cbm indexed.
   - `loadout check` shows the last refresh's result only when it failed.

## What changes beyond the decisions

- **codebase-memory's documented Claude Code hooks.** cbm's own installer sets these for Claude Code (README "Multi-Agent Support"): `SessionStart`, `SubagentStart`, a non-blocking `PreToolUse` for `Grep`/`Glob`/`Bash`, and `PostToolUse` on `Read` (coverage). For Codex it sets `SessionStart` and `SubagentStart`.
  - loadout's plugin mirrors that set, in place of today's `Grep|Glob`-only `hook-augment`.
  - The builder reads the exact commands from cbm's source or installer, never by running a real install. A dry run (`install --dry-run`) in a throwaway `HOME` is allowed.
  - It verifies each command's output on a real repo; `hook-augment` printed nothing in a quick manual try.
- **Subagent context.** `hooks/subagent-context.sh` names the exact tool names to call (for the plugin server and for a user's own server name), so a subagent needs no ToolSearch. It tells the subagent that Serena's project is already active, so it calls `find_symbol` and friends directly.
- **Parent side.** `rules/tooling.md` gains one line: when delegating code work, name the tools in the subagent's prompt (codebase-memory project name, `search_graph`/`trace_path`, Serena `find_symbol`), since subagents use what their prompt names.
- **`auto-approve` matcher** also covers a user's own Serena server named `serena` (`mcp__serena__.*`), not only `mcp__plugin_loadout_serena__.*`. Other names are not matched, as in Serena's docs and as `hooks.md` says for Codex. `remind` itself recognises any tool name containing `serena`.
- **Serena version.** `remind` with Bash counting needs Serena 2.1.0, the version tested here. The catalog's minimum moves there if it is lower, and the existing version check reports an older Serena.

## Every setup variation

The builder covers each with a test (`fake_home`/`fake_runner`) and, where loadout reports state, a `loadout check` row.

| Setup | Expected |
|---|---|
| Claude Code, plugin's Serena and cbm (default) | All Serena and cbm hooks above run once each per event; tools load upfront |
| Claude Code, the user's own Serena server as well (`claude mcp add serena`, user, project or `.mcp.json` scope) | `remind` and `auto-approve` cover both server names. Two Serena servers are a duplicate: `check` names it, and `adopt`/`configure own` offer the choice. loadout never removes the user's server without a yes |
| Claude Code, the user already has Serena's hooks in `~/.claude/settings.json` (or a project's settings) | No hook runs twice. Two `remind`s would share one counter file and deny at half the threshold. An entry that is an exact duplicate of a plugin hook follows the existing rule (`duplicates.py`, ADR 0035): `loadout update` removes it, with a backup, so `loadout restore` brings it back. An equivalent entry that is not exact (the same `serena-hooks` subcommand with another matcher, client flag or wrapper) stays the user's. The plugin's copy stays silent while it exists: a guard in the hook wrapper reads the user's and the project's settings. `check` names it, and `adopt`/`configure own` offer the choice |
| Claude Code, cbm set up by its own `install` (its MCP entry in `~/.claude.json`, agents, skill, hooks in settings) | Same rule: no doubled hooks, no second server without `check` naming it. This settles the "cbm own-setup variants" backlog item (a)-(e) as far as Claude Code is concerned, and Codex's (a) |
| Serena or cbm not available to the agent | Its hooks do nothing, so `remind` never pushes to a tool the agent does not have. "Not available" means any of:<br>- its binary is missing (`run.sh` checks this today);<br>- the loadout plugin is disabled (its hooks do not run then);<br>- the server is disabled in Claude Code's own config for this folder (`disabledMcpServers` in `~/.claude.json`'s project entry, `disabledMcpjsonServers` in settings).<br>The wrapper guard checks the last case |
| Codex CLI, VS Code's Codex extension, both, Windows/WSL sides (ADR 0038, ADR 0033) | Serena's six Codex hooks as today, matched against Serena's current docs. cbm's documented Codex hooks are added. No search hint. Hook approval as today (`/hooks`, or the extension's review) |
| Codex: tools load on demand | The builder checks the Codex docs for an equivalent of `alwaysLoad` (Context7, developers.openai.com/codex). If there is one, Codex gets it; if not, the instruction block's "search first" line stays |
| Windows native Claude Code (Grep/Glob exist; PowerShell) | Hooks run through the same wrappers; `remind` sees Grep, Read and Bash. Tests cover the Windows matcher set |
| VS Code's Claude Code extension | Same plugin hooks; no extra work expected. The builder checks the docs for differences |

## Measurement

- `loadout usage` before (the numbers above) and after, main vs subagent: sessions using Serena or cbm, and symbol greps per session.
- Success: a clear rise in subagents. The user judges it from a week of use; no fixed number.
- The PR description carries the "before" table.

## Docs and ADRs

- New ADR (0039): Serena's documented hooks including `remind`, `alwaysLoad`, and the search hint removed. It supersedes ADR 0008's dropped-`remind` sentence and ADR 0026 for code searches (the docs hint stays as in 0026). Index, AGENTS.md range (0001-0039).
- `docs/reference/hooks.md` (tables for both agents), `docs/explanation/the-toolset.md`, `docs/how-to/codex.md` ("Tool hints" bullet), troubleshooting (a denied grep, and how to read it), `docs/reference/cli.md` (`loadout usage`), the configure skill if its routing names the hint.
- Serena memories that name the hint. Run `loadout:docs-sync` at the end.

## Non-goals

- Serena's system-prompt override (decision 4).
- Shipping codex-reviewer in the kit.
- Blocking anything beyond what Serena's `remind` itself does; loadout writes no deny logic of its own.
- Changing Serena's or cbm's thresholds or texts.

## Anti-goals

- A hook that runs twice for one tool call because the user and the plugin both set it.
- A reminder that points to a tool the agent does not have.
- Removing or rewriting anything the user set up without a yes.
- A check row that cannot clear.

## Constraints

All of AGENTS.md:
- exact-text records and backups before writes;
- `runner.run` argument lists;
- `fake_home`/`fake_runner`, and no real installers or mutating `claude`/`codex` in tests or by agents;
- no plaintext secrets;
- Conventional Commits without attribution.

`remind` adds about 250 ms per matched tool call (measured). The builder narrows its Claude Code matcher to the tools it counts or resets on (`Bash|Read|Grep|Glob` and Serena's tools), which is a "variation thereof" in Serena's words, instead of every tool.

## Builder's calls made by the author (check these)

- `remind`'s counter file is keyed by session id, and Claude Code subagents share the parent's. So parallel subagents share one counter and its 2-minute quiet window. Accepted as Serena's design; measured afterwards.
- `remind` resets only on Serena symbolic tools, not on codebase-memory calls. An agent that uses the graph and then greps can still get Serena's denial. Accepted; Serena's text says "you can continue using grep now".
- The `alwaysLoad` cost (~12-13k tokens per context) is accepted by the user.
- Exact duplicate hooks follow ADR 0035 (removed by `update`, with a backup). Equivalent ones that are not exact stay the user's, and the plugin's copy stays silent.
- "Not available" is defined as binary missing, plugin disabled, or the server disabled in Claude Code's config.
- The grep parser is split out and improved, and "before" is recomputed with it.
- Only the server names `serena` and the plugin's are matched.
- The refresh thresholds in decision 7 ((a) end of turn with changes, (b) tree-rewriting git commands, (c) 20 changed code files) are the author's.
