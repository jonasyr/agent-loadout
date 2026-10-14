# Hooks

This page covers two things: the hooks that the loadout plugin ships, and how loadout names hooks of your own.

## Hooks of the loadout plugin

They are defined in `plugins/loadout/hooks/hooks.json` and run from the installed plugin. They are not written into your `~/.claude/settings.json`.

Most commands go through `plugins/loadout/hooks/run.sh`. It runs the command only if its binary is on `PATH`; on a machine without the tool, the hook does nothing and exits 0. With `--soft` it also discards errors and always exits 0. With `--python` it runs a Python script with `python3` or `python` 3.11+, else a uv-managed Python.

The last column says how `plugins/loadout/hooks/codex.json` differs: `same` means the same command, matcher and timeout; `argument` means the same hook with Codex arguments; `—` means Codex has no such hook.

| Event | Matcher | Runs | Timeout | Purpose | In Codex |
|---|---|---|---|---|---|
| `SessionStart` | all | `serena-hooks activate --client=claude-code` | 15 s | Serena's own activation hook. | argument (`--client=codex`) |
| `SessionStart` | all | `loadout hook-session-start` | 10 s | Shows queued notices (for example "updates available, run `loadout update`") and starts the background maintenance when the daily pull or the weekly update check is due. Errors never break the session. | same |
| `SessionStart` | all | `--soft --python hooks/reload_check.py` | 5 s | Tells you once per session to run `/reload-plugins` when Claude Code updated the plugin after the session started (the session keeps the old skills and hooks until then). State: `~/.local/state/loadout/reload-notified.json`. | — (Codex loads plugins per session) |
| `SessionEnd` | all | `serena-hooks cleanup --client=claude-code` | 10 s | Serena's own cleanup hook. | argument (`--client=codex`), timeout 3 s |
| `PreToolUse` | `Bash` | `rtk hook claude` | 10 s | rtk rewrites shell commands to its token-saving form. | argument (`rtk hook codex`) |
| `PreToolUse` | `mcp__plugin_loadout_serena__.*` | `serena-hooks auto-approve --client=claude-code` | 10 s | Serena's own auto-approve hook, for Serena's tools only. | argument (`--client=codex`), matcher `mcp__serena__.*` |
| `PreToolUse` | `Grep\|Glob` | `--soft codebase-memory-mcp hook-augment` | 5 s | The code-graph server's hook for `Grep` and `Glob`. It watches only those two tools; loadout's own hint also covers shell searches. | — (Codex has no such tools) |
| `PreToolUse` | `Grep\|Glob\|Bash\|WebSearch\|WebFetch` | `hooks/tool_hint.sh` (a bash filter; it starts `hooks/tool_hint.py` only when the call mentions grep, rg, find, Glob, a web tool or an MCP tool) | 5 s | From the 3rd symbol search on (Grep, Glob of code files, shell `rg`/`grep`/`git grep`, or `find -name` of code files) since Serena or the code graph was last used, adds one fact naming them. Only in a code repo (its top level has a code file, a build file or `src/`). A grep after a pipe, a search limited to docs or config files (`-t md`, `-g '*.json'`), and a `find` that deletes or executes do not count. A library-docs web lookup (a docs host, or a web search naming docs, an API or a library) gets one fact naming Context7 and Microsoft Learn. At most one hint per 10 matched calls; never blocks; never switched off for a session. State: `$XDG_STATE_HOME/loadout/tool-hint/<session>.json` (`~/.local/state/loadout/tool-hint/` by default); files older than 7 days are removed when a new session counts its first search or docs lookup. | matcher `Bash` (Codex has no Grep, Glob or web tools for hooks) |
| `PostToolUse` | `Write\|Edit\|MultiEdit` | `--soft --python hooks/advisor.py record` | 5 s | Remembers a finished implementation plan. | matcher `Edit\|Write`; in Codex it reads `apply_patch` headers (see below) |
| `PostToolUse` | `mcp__plugin_loadout_serena__.*\|mcp__plugin_loadout_codebase-memory-mcp__.*` | `hooks/tool_hint.sh` | 5 s | Resets the search count when Serena or the graph was used. | matcher `mcp__serena__.*\|mcp__codebase-memory-mcp__.*` |
| `Stop` | all | `--soft --python hooks/advisor.py stop` | 5 s | Asks once for `/loadout:execution-advisor` after a plan. | same |
| `Stop` | all | `--soft --python hooks/reload_check.py` | 5 s | Same check at the end of a turn, for sessions that run long. | — |
| `SubagentStart` | `*` | `hooks/subagent-context.sh` | 5 s | Gives a subagent the tool routing, triggers first (code structure, symbols, library docs also while planning). | same |
| `PostToolUse` | `Edit\|Write` | `--soft --python hooks/typecheck.py` | 90 s | Codex only. Runs `pyright`, `tsc --noEmit` or `cargo check` on the changed files and reports the errors, because Codex has no LSP plugins. Each check is capped at 20 s; after that it reports itself as skipped. Silent when clean. | Codex only. Serena's diagnostics tool also reports type errors when asked. |

Measure the effect with `loadout usage` ([CLI](cli.md#loadout-usage)).

The plugin also declares two MCP servers in `plugins/loadout/.mcp.json`: `serena` and `codebase-memory-mcp`.

### Maintenance

What `loadout hook-session-start` and the background `loadout maintenance` job do: [The daily sync](../explanation/architecture.md#the-daily-sync).

### The execution-advisor hooks

When `advisor.py record` and `advisor.py stop` act, and where they keep state: [When the hook nudges](../explanation/execution-advisor.md#when-the-hook-nudges). Both also run in Codex, where `record` also sees plans written through `apply_patch`, so the nudge works there too (details on the same page).

### In Codex

Codex reads the plugin's `.codex-plugin/plugin.json`, which points to `hooks/codex.json` instead of `hooks/hooks.json`; the last column above shows how the two differ. Codex runs plugin hooks only after you approve them once in `/hooks`, and again after they change. loadout never approves them for you: that is Codex's safety gate. `loadout check` (`Codex hooks`), bootstrap's "Still to do" and `loadout configure set target codex on` list the approval while it is open. More on Codex: [Use loadout with Codex](../how-to/codex.md#what-stays-different).

## Naming hooks of your own tools

[`loadout adopt --own`](cli.md#loadout-adopt) and [`loadout configure set own`](cli.md#loadout-configure) take a name for each tool. A hook has no name of its own, so loadout builds one from its event and matcher:

| Name | Hook |
|---|---|
| `PreToolUse:Bash` | Event `PreToolUse`, matcher `Bash`. |
| `Stop:` | Event `Stop`, no matcher. A missing matcher and `""` are the same. |
| `PreToolUse:Bash#2` | The second of several hooks that share the name `PreToolUse:Bash`. |

Rules:

- When several hooks share a name, a plain name is refused with a message that lists the choices. Add `#n`. The count is 1-based and follows the order of `loadout configure own --all`, which includes the tools you left.
- If a name matches several kinds of item, write `<kind>:<name>`, for example `hook:Stop:`. The kinds are `plugin`, `marketplace`, `mcp`, `skill` and `hook`.
- A comma separates the entries of `--own`, so a name that contains one (a matcher such as `Bash,Edit`) cannot be given there. Choose it in the interactive prompt of `loadout adopt --apply`.
- Result lines print a hook without a matcher as `hook Stop (no matcher)`.

How hooks that you record as global are stored and merged is described in [settings-merge](settings-merge.md#hook-merge). A hook's identity there is not this name, but event, matcher and command.
