# Tool routing (loadout)

Pick the tool by the question, not by habit:

| When you need | Use |
|---|---|
| Who calls X, a call chain, the architecture, dead code, the impact of a change | codebase-memory-mcp (`search_graph`, `trace_path`, `get_architecture`, `query_graph`) before grep. If the repo is not indexed yet, run `index_repository` first. |
| A definition or its references, a rename, a function body to replace, code to insert next to a symbol | Serena symbolic tools |
| Type errors and diagnostics | LSP plugins (Claude Code) or the type-check hook (Codex) report them after edits; fix them before moving on |
| Text, config files, docs, non-code | Grep / Glob / Read (Codex: search and read in the shell) |
| Library, framework or API documentation, also while planning | Context7 first; Microsoft Learn for .NET/Azure/Windows/Microsoft APIs; web search last |
| UI verification and browser checks | `playwright-cli` (read `playwright-cli --help` first); screenshots and snapshots go to disk, open only what you need |
| Questions about loadout, or changes to the loadout setup (tools, preferences, agents, profiles, undo) | The `loadout:configure` skill, even when the user does not name it; never edit `~/.claude` or `~/.codex` settings by hand |
| Shell commands | rtk rewrites them automatically when installed; use `rtk proxy <cmd>` when you need raw output |

loadout's hooks add a one-line hint when a search or a web lookup would be better answered by these tools (in Codex: shell searches only); follow it when it fits.

Before ending a task that touched UI, verify it in a browser with playwright-cli. Never claim it "looks right" without having looked. If playwright-cli is missing or fails, say so (and suggest `loadout check`) instead of launching a browser binary yourself.
