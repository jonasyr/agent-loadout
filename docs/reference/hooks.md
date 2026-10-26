# Hooks

This page covers two things: the hooks that the loadout plugin ships, and how loadout names hooks of your own.

## Hooks of the loadout plugin

They are defined in `plugins/loadout/hooks/hooks.json` and run from the installed plugin. They are not written into your `~/.claude/settings.json`.

Most commands go through `plugins/loadout/hooks/run.sh`. It runs the command only if its binary is on `PATH`; on a machine without the tool, the hook does nothing and exits 0. With `--soft` it also discards errors and always exits 0. With `--python` it runs a Python script with `python3` or `python` 3.11+, else a uv-managed Python. The `PATH` that counts is the one the agent was started with. In a Remote-WSL window, VS Code's Codex extension gets VS Code's server `PATH`, where no shell startup file runs, so a hook whose binary lives in loadout's tool folders (such as `~/.local/bin`) finds nothing there; `loadout bootstrap --vscode-path` puts those folders on that `PATH` ([MCP servers in a Remote-WSL window](../how-to/vscode.md#mcp-servers-in-a-remote-wsl-window)).

The last column says how `plugins/loadout/hooks/codex.json` differs: `same` means the same command, matcher and timeout; `argument` means the same hook with Codex arguments; `—` means Codex has no such hook.

| Event | Matcher | Runs | Timeout | Purpose | In Codex |
|---|---|---|---|---|---|
| `SessionStart` | all | `hooks/mcp_guard.py serena serena-hooks activate --client=claude-code` | 15 s | Serena's own activation hook, through [the guard](#the-guard). | — (in `~/.codex/hooks.json`, see [Serena's hooks in Codex](#serenas-hooks-in-codex)) |
| `SessionStart` | all | `loadout hook-session-start --agent claude` (Codex: `--agent codex`) | 10 s | Shows queued notices (for example "updates available, run `loadout update`") and that agent's open "Now do this" steps, and starts the background maintenance when the daily pull or the weekly update check is due. A Claude Code step is cleared at a fresh start only (the hook's `source` is `startup`, not `resume`, `clear` or `compact`), without being shown, since that session already loaded the new plugins; Codex's `restart Codex` step is cleared the same way at a Codex start. A bootstrap step stays until the health rows that produced it pass. Codex does not run an unapproved hook, so the `/hooks` step cannot appear at a Codex session start while the hooks are unapproved: the `Codex hooks` row of `loadout check`, and the open steps `loadout check`, `loadout update` and `loadout bootstrap` print at their end, say it instead. An older plugin copy passes no `--agent` and gets the notices only. Errors never break the session. | same |
| `SessionStart` | all | `--soft --python hooks/reload_check.py` | 5 s | Tells you once per session to run `/reload-plugins` when Claude Code updated the plugin after the session started (the session keeps the old skills and hooks until then). State: `~/.local/state/loadout/reload-notified.json`. When the running plugin folder is the current install, it also removes the open `/reload-plugins` step that loadout saved for its own plugin ([when steps clear](state-and-sync.md#at-each-session-start)). | — (Codex loads plugins per session) |
| `SessionEnd` | all | `hooks/mcp_guard.py serena serena-hooks cleanup --client=claude-code` | 10 s | Serena's own cleanup hook, through the guard. | — (in `~/.codex/hooks.json`, see [Serena's hooks in Codex](#serenas-hooks-in-codex)) |
| `PreToolUse` | `Bash` | `rtk hook claude` | 10 s | rtk rewrites shell commands to its token-saving form. | argument (`rtk hook codex`) |
| `PreToolUse` | `mcp__plugin_loadout_serena__.*\|mcp__serena__.*` | `hooks/mcp_guard.py serena serena-hooks auto-approve --client=claude-code` | 10 s | Serena's own auto-approve hook, for Serena's tools only, through the guard. | — (Serena documents none for Codex) |
| `PreToolUse` | `Bash\|Read\|Grep\|Glob\|mcp__plugin_loadout_serena__.*\|mcp__serena__.*` | `hooks/mcp_guard.py serena serena-hooks remind --client=claude-code` | 5 s | Serena's own reminder, through the guard ([what it does](#serenas-reminder)). The matcher lists the tools it counts or resets on. | argument (`--agent codex … remind --client=codex`, matcher `Bash`; it replaces the `remind` entry in `~/.codex/hooks.json` once the installed copy carries it, see [Serena's hooks in Codex](#serenas-hooks-in-codex)) |
| `PreToolUse` | `WebSearch\|WebFetch` | `hooks/tool_hint.sh` (a bash filter; it starts `hooks/tool_hint.py` only when the call is a web tool, with `python3`, or through `run.sh --python` when `python3` is missing or does not run) | 5 s | The docs hint: a library-docs web lookup (a docs host, or a web search naming docs, an API or a library) gets one fact of at most 300 characters naming Context7 and Microsoft Learn, at most once per 10 docs lookups. Never blocks. Code searches get no loadout hint any more: Serena's `remind` covers them ([ADR 0039](../adr/0039-serena-remind-tools-load-upfront-cbm-refresh.md)). Claude Code subagents share their parent's session, so they share its count. State: `$XDG_STATE_HOME/loadout/tool-hint/<session>.json` (`~/.local/state/loadout/tool-hint/` by default); files older than 7 days are removed when a session's first docs lookup creates its state file. | — (Codex gives hooks no web tools, so no docs hint) |
| `PostToolUse` | `Write\|Edit\|MultiEdit` | `--soft --python hooks/advisor.py record` | 5 s | Remembers a finished implementation plan. | matcher `Edit\|Write`; in Codex it reads `apply_patch` headers (see below) |
| `PostToolUse` | `Write\|Edit\|MultiEdit\|Bash` | `--soft --python hooks/refresh.py --agent claude` | 5 s | Notes edits and shell commands, and re-indexes the code graph in the background when it is stale ([details](#the-code-graph-refresh)). | matcher `Edit\|Write\|Bash`, argument `--agent codex` |
| `Stop` | all | `--soft --python hooks/advisor.py stop` | 5 s | Asks once for `/loadout:execution-advisor` after a plan. | same |
| `Stop` | all | `--soft --python hooks/reload_check.py` | 5 s | Same check at the end of a turn, for sessions that run long, including removing the open `/reload-plugins` step that loadout saved for its own plugin once the session runs the current install. | — |
| `Stop` | all | `--soft --python hooks/refresh.py --agent claude` | 5 s | The end-of-turn trigger of the code-graph refresh. | argument (`--agent codex`: Codex's own `enabled` switch, never Claude Code's files) |
| `SubagentStop` | all | `--soft --python hooks/refresh.py --agent claude` | 5 s | Same, at the end of a subagent. | — |
| `SessionStart` | all | `--soft --python hooks/cbm_project.py session-start --agent claude` | 5 s | Names the folder's codebase-memory project ([details](#the-codebase-memory-project-pointer)). | argument (`--agent codex`) |
| `SubagentStart` | `*` | `hooks/subagent-context.sh claude` | 5 s | Gives a subagent the tool routing, triggers first, with the exact tool names (`mcp__plugin_loadout_serena__find_symbol`, `mcp__plugin_loadout_codebase-memory-mcp__search_graph` and the like). It says both servers are loaded and Serena's project is active. The "loaded, call them directly" sentence appears only when both binaries are on `PATH` and `hooks/mcp_guard.py --available claude serena codebase-memory-mcp` agrees, that is, neither server is switched off for the folder in Claude Code ([the guard](#the-guard)). Otherwise a short card without tool names is printed. | argument (`codex`): Codex loads MCP tools on demand, so its card says to search for them first and names no `mcp__plugin_loadout_` tools |
| `SubagentStart` | `*` | `--soft --python hooks/cbm_project.py subagent-start --agent claude` | 5 s | The same project pointer for a subagent. | argument (`--agent codex`) |
| `PostToolUse` | `Edit\|Write` | `--soft --python hooks/typecheck.py` | 90 s | Codex only. Runs `pyright`, `tsc --noEmit` or `cargo check` on the changed files and reports the errors, because Codex has no LSP plugins. Each check is capped at 20 s; after that it reports itself as skipped. Silent when clean. | Codex only. Serena's diagnostics tool also reports type errors when asked. |

Measure the effect with `loadout usage` ([CLI](cli.md#loadout-usage)), or ask for the report with `/loadout:usage` (Codex: `$loadout:usage`).

The plugin also declares two MCP servers in `plugins/loadout/.mcp.json`: `serena` and `codebase-memory-mcp`. Both have `"alwaysLoad": true`, so Claude Code puts their tools in every session and subagent upfront and the agent calls them directly, without a `ToolSearch` step. That costs about 50 000 characters (roughly 12k to 13k tokens) of tool definitions each time. There is no per-user switch, because the plugin's file is the same for everyone. To get on-demand loading back for all servers, set `ENABLE_TOOL_SEARCH` as Claude Code's docs describe. Why: [ADR 0039](../adr/0039-serena-remind-tools-load-upfront-cbm-refresh.md). For Codex it declares only `codebase-memory-mcp` (`plugins/loadout/.codex-mcp.json`): Codex gets Serena from `~/.codex/config.toml` instead.

### The guard

`hooks/mcp_guard.py [--agent codex] <server> <program> <subcommand> ...` runs Serena's hooks: for Claude Code, and with `--agent codex` Serena's `remind` for Codex. It stays silent (no output, exit 0) when:

- for `remind` only: the call is a harmless search or read that Serena's symbolic tools cannot help with (`hooks/harmless.py`, [ADR 0040](../adr/0040-serena-remind-skips-harmless.md)). Only a simple `Bash` line (Claude Code's tool, or Codex's shell) can be harmless: commands joined by `&&`, `||`, `;` and pipes. A line with a `cd`, a loop, a `{ }` group or `( )` subshell, a `$(...)` or backtick substitution, a `<(...)` or a `<` before its command goes to Serena whole. In a simple line, every grep-family search (`grep`, `rg`, `ag`, `ack`, `egrep`, `fgrep`, `ugrep`, `ug`) must be one of these:
  - behind a pipe, filtering another command's output, when it names no file of its own and no earlier command of the line names a code file of the project;
  - over config, doc or text files (`.md`, `.txt`, `.json`, `.toml`, `.yaml`, `.ini`, `.env`, `.log` and the like, or names like `.gitignore`, `Makefile`, `Dockerfile`). A folder with such a name is a folder, and a wildcard such as `*.md` counts only when it matches something and none of its matches is a folder;
  - over files outside the project (`~/.codex/config.toml`, `/tmp/...`). The project is Claude Code's `CLAUDE_PROJECT_DIR` when the session's folder lies in it, else the session's folder;
  - over folders, or with no path, limited to doc types (`-t md`, `-tmd`, `--include='*.yml'`). Every inclusion filter must be one, and an exclusion such as `-g '!*.lock'` limits nothing. A file named explicitly is read whatever the filter says (`rg -t md x src/a.py` goes to Serena).

  The line must also read no code file with `cat`, `head`, `tail`, `sed`, `awk`, `less`, `more` or `bat`. A code file here is one with a code suffix, an existing file without a suffix (`bin/loadout`), a wildcard (`bin/*`, but not `docs/*.md`) or a file named by a variable (`"$f"`). A sed script or an awk program is no file. Patterns given as `-e`, `-efoo`, `--regexp=foo` or `-f` are recognised, and a pattern file (`-f src/a.py`, `--file=…`) counts as a read. `-T` takes a value only for ripgrep (`-T TYPE`); for GNU grep it is a flag. After `--`, an operand starting with `-` is a file. A file given with `<` counts as an operand of the command it feeds.

  A `Read` of a non-code file or of a file outside the project is harmless too, and so is a `Grep` tool call over such a path, or over a folder with a doc-type filter. Anything else goes to Serena: a code file, a folder search without a doc filter (`grep -r x .`), no path at all, an unknown suffix, a mixed line, or a line that does not parse;

- the program is not on `PATH`;
- Claude Code has the server off for the folder (`~/.claude.json`, `projects[<folder or a parent>].disabledMcpServers` lists `plugin:loadout:serena` or `serena`), unless your own `serena` server is on (in `mcpServers` of `~/.claude.json`, in the project's entry, or in `<repo>/.mcp.json` and not in `disabledMcpjsonServers`);
- Claude Code: your settings (`~/.claude/settings.json`, `.claude/settings.json`, `.claude/settings.local.json`) already run the same program and subcommand for that event, under a matcher that matches the current tool (a `remind` of yours on `Grep` silences the plugin's for Grep only). Flags are ignored; an `echo ...` that only mentions it does not count;
- Codex (`--agent codex`): `config.toml` switches the server off (`[mcp_servers.<server>] enabled = false`), or a hook in `~/.codex/hooks.json` (or `$CODEX_HOME`), in `[hooks]` of `config.toml` or in `<repo>/.codex/hooks.json` already runs the same program and subcommand under a matcher that matches the tool (Codex's matchers are regular expressions searched in the tool name). loadout's own `remind` entry in `hooks.json` counts too, so no call is reminded twice while it moves. In this mode the guard reads none of Claude Code's files.

`hooks/mcp_guard.py --available AGENT SERVER...` is the guard's second mode. It reads the hook payload on stdin and exits 0 when the agent has every named server here, else 1: each binary is on `PATH`, and the server is on for the folder (Claude Code: the per-folder switch above; Codex: not `enabled = false` in `config.toml`; each agent reads only its own files). `subagent-context.sh`, `cbm_project.py` and `refresh.py` use it.

The program's own run ends before the hook's timeout (14 s for `activate`, 9 s for `cleanup` and `auto-approve`, 4 s otherwise). An exact copy of a plugin hook (same event, matcher and command) in your `~/.claude/settings.json` is still removed by `loadout update`; the same command under another matcher, as in Serena's docs (matcher `""`), stays yours and makes the plugin's copy silent, after a backup ([ADR 0035](../adr/0035-loadout-update-brings-a-machine-current.md)); the guard prefix is stripped when it compares.

### Serena's reminder

`serena-hooks remind` is Serena's own and the only loadout-shipped hook that can deny a call. It denies the 3rd grep, the 3rd read of a code file or the 4th mixed call made without a Serena symbolic tool in between. It does so once, then stays silent for 2 minutes. The reason reads "Too many consecutive grep calls without using symbolic tools. You can continue using grep now if needed, the counter was reset." The next call goes through. It adds about 0.5 s to each matched call. Two `remind` hooks would share one counter and deny at half the threshold, which is why the guard skips a duplicate. Harmless searches (config, docs, piped output, files outside the folder) never reach it ([the guard](#the-guard)). Why loadout ships it: [ADR 0039](../adr/0039-serena-remind-tools-load-upfront-cbm-refresh.md); what to do when it fires: [Troubleshooting](../how-to/troubleshooting.md).

codebase-memory's own `hook-augment` (the old `Grep|Glob` hook) is not wired. It prints nothing and only delays the call in the current codebase-memory; the reason and the upstream issues are in [ADR 0039](../adr/0039-serena-remind-tools-load-upfront-cbm-refresh.md).

### The codebase-memory project pointer

`hooks/cbm_project.py session-start` and `subagent-start` print "codebase-memory: this folder is indexed as project <name>; pass project="<name>" to search_graph, trace_path and get_code_snippet." when the folder is indexed and the agent has codebase-memory (its binary is on `PATH`; in Claude Code the server is not switched off for the folder, in Codex not `enabled = false` in `config.toml`; each agent reads only its own files). It is a file check, with no daemon call (an index is accepted only when its recorded root is the folder or is absent): the default project name is the path without its leading `/`, with `/` turned into `-` and runs of `-` collapsed; else it reads `root_path` of up to 64 index files in `$CBM_CACHE_DIR` (default `~/.cache/codebase-memory-mcp`), read-only. Silent when the folder is not indexed, and when your own hooks for that event already run codebase-memory-mcp or one of its installer's wrapper scripts (`codebase-memory-session.sh`, `codebase-memory-coverage.sh`), so the pointer is not said twice. Only a hook whose matcher matches the event counts (a `startup`-only hook leaves the pointer on at `resume`), and an `echo` that only names codebase-memory-mcp does not count.

### The code-graph refresh

`hooks/refresh.py` re-indexes an indexed git repo that codebase-memory's own watcher does not watch. It never blocks: the hook only notes and decides, and a detached child does the work. It acts on:

- the end of a turn (`Stop`, `SubagentStop`) with changed code files, or with a moved `HEAD` or working tree;
- a git command that rewrites the tree (checkout, switch, pull, merge, rebase, reset, stash pop or apply, cherry-pick, revert);
- 20 changed code files in one turn.

The child takes a lock per repo (stale after 2160 s), asks `codebase-memory-mcp cli --quiet index_status --project <name> --format json`, and leaves a watched project alone (the watcher re-indexes within about 6 s). Otherwise it runs `codebase-memory-mcp cli --quiet index_repository --repo-path <root>` (with `--name <name>` for a project indexed under another name). An "another index operation" refusal is silent; another failure is recorded, and no mid-turn trigger runs for 10 minutes (the next `Stop` retries). It does nothing when the program is not on `PATH`, the server is off for the folder (the guard's rules), the folder is no git repo, or codebase-memory never indexed it: the first index is the job of [`cbm_auto_index`](preferences-format.md#codebase-memorys-auto_index). State: `$XDG_STATE_HOME/loadout/cbm-refresh/` (`~/.local/state/loadout/cbm-refresh/` by default, mode 0700). The hook caches the project name and the guard's verdict for 10 minutes; state files are pruned after 30 days or when the repo is gone. `loadout check` shows a row only after a failed last refresh, with the fix `codebase-memory-mcp cli index_repository --repo-path <root>` ([CLI](cli.md#loadout-check)).

Serena needs no such refresh ([why](../explanation/the-toolset.md#why-the-graph-needs-a-refresh-and-serena-does-not)).

### Serena's hooks in Codex

In Codex, Serena's hooks are not in the plugin, except `remind` (below). loadout writes the six that Serena documents for Codex ([Serena: clients](https://oraios.github.io/serena/02-usage/030_clients.html)) into `~/.codex/hooks.json`, each only if no hook of that event already runs the same `serena-hooks` subcommand with `--client=codex`:

| Event | Matcher | Runs | Timeout |
|---|---|---|---|
| `PreToolUse` | `Bash` | `serena-hooks remind --client=codex` | 5 s |
| `PreToolUse` | `^mcp__serena__` | `serena-hooks plan-guard --client=codex` | 5 s |
| `PostToolUse` | `^mcp__serena__.*$` | `serena-hooks reset --client=codex` | Codex default |
| `SessionStart` | `startup\|resume` | `serena-hooks activate --client=codex` | 5 s |
| `UserPromptSubmit` | — | `serena-hooks plan-context --client=codex` | 5 s |
| `SessionEnd` | — | `serena-hooks cleanup --client=codex` (a `cleanup` under `Stop` counts too) | 3 s |

`remind` moves into the plugin, behind [the guard](#the-guard), once the installed Codex copy of `loadout@agent-loadout` (in `~/.codex/plugins/cache/agent-loadout/loadout/`; without a `local` copy, the version `codex plugin list` reports as installed, since old versions stay cached) carries the guarded hook and `config.toml` has `[plugins."loadout@agent-loadout"] enabled = true`. The next foreground run (`loadout bootstrap`, `loadout update`; never the background daily sync) then removes loadout's own `remind` entry from `hooks.json`, after a backup, in the same run as the plugin upgrade. It says "removed loadout's Serena remind (loadout's plugin runs it now)", and the hooks step asks you to trust the changed hooks when Codex asks at start (or review them in `/hooks`), because the positions Codex keys its approvals on shift. With an older copy, the plugin switched off or removed, `remind` stays in, or comes back to, `hooks.json`. A `remind` entry of your own stays yours, and the plugin's copy then stays silent.

When Serena changes an entry (as with the 5 s timeouts it added to `plan-guard`, `activate` and `plan-context`), the next loadout run replaces the entry loadout wrote earlier, with a backup first; Codex then asks you to approve it again in `/hooks`. An entry you changed yourself stays yours.

loadout records the entries it wrote and never changes yours. It adds its entries in the file's own format (two-space, four-space or tab indent or one line, LF or CRLF line endings, `\uXXXX` escapes, all kept), after a backup; only when it cannot reproduce the file byte for byte does it leave it as it is, and `loadout check` lists the entries to add by hand. Serena hooks you keep inline as `[hooks]` in `config.toml` count as present too, and next to inline hooks loadout creates no `hooks.json` (Codex warns about mixed forms); it lists what to add there instead. When neither `serena-hooks` nor `serena` is on `PATH`, it removes its own entries (with only `serena` on `PATH` it keeps them and changes nothing), but never in the background daily sync, whose `PATH` can lack Serena's folder. An entry of loadout's that you delete comes back on the next run, as a `config.toml` section does; to keep Serena's hooks out, turn Serena off. The matchers name the server `serena`: with your own Serena under another name, Serena's `mcp__serena__` hooks do not match its tools, as in Serena's own docs. Codex runs them only after you review them in `/hooks`, and `loadout check` waits for that approval of every Serena hook there, yours included ([ADR 0028](../adr/0028-serena-codex-hooks-in-hooks-json.md)).

### Maintenance

What `loadout hook-session-start` and the background `loadout maintenance` job do: [The daily sync](state-and-sync.md#the-daily-sync).

### The execution-advisor hooks

When `advisor.py record` and `advisor.py stop` act, and where they keep state: [When the hook nudges](../explanation/execution-advisor.md#when-the-hook-nudges). Both also run in Codex, where `record` also sees plans written through `apply_patch`, so the nudge works there too (details on the same page).

### In Codex

Codex reads the plugin's `.codex-plugin/plugin.json`, which points to `hooks/codex.json` instead of `hooks/hooks.json`; the last column above shows how the two differ. Codex runs plugin hooks only after you approve them once in `/hooks`, and again after they change. loadout never approves them for you: that is Codex's safety gate. `loadout check` (`Codex hooks`), bootstrap's "Still to do" and `loadout configure set target codex on` list the approval while it is open. More on Codex: [Use loadout with Codex](../how-to/codex.md#what-stays-different).

VS Code's Codex extension loads the plugins and has its own hook review instead of `/hooks`. Approve the hooks there: the hooks icon in the prompt bar ("Review hooks · N need approval"), then Allow all, or Settings > Hooks. The approval lands in `config.toml` (`[hooks.state]`), as with the CLI; loadout never writes it. The loadout plugin's hooks need approval only while the plugin is on in `config.toml`; Serena's hooks in `~/.codex/hooks.json` always do ([Codex in VS Code without the CLI](../how-to/vscode.md#codex-in-vs-code-without-the-cli)).

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
