# Hooks

This page covers two things: the hooks that the loadout plugin ships, and how loadout names hooks of your own.

## Hooks of the loadout plugin

They are defined in `plugins/loadout/hooks/hooks.json` and run from the installed plugin. They are not written into your `~/.claude/settings.json`.

Most commands go through `plugins/loadout/hooks/run.sh`. It runs the command only if its binary is on `PATH`; on a machine without the tool, the hook does nothing and exits 0. With `--soft` it also discards errors and always exits 0.

| Event | Matcher | Runs | Timeout | Purpose |
|---|---|---|---|---|
| `SessionStart` | all | `serena-hooks activate --client=claude-code` | 15 s | Serena's own activation hook. |
| `SessionStart` | all | `loadout hook-session-start` | 10 s | Shows queued notices (for example "updates available, run `loadout update`") and starts the background maintenance when the daily pull or the weekly update check is due. Errors never break the session. |
| `SessionEnd` | all | `serena-hooks cleanup --client=claude-code` | 10 s | Serena's own cleanup hook. |
| `PreToolUse` | `Bash` | `rtk hook claude` | 10 s | rtk rewrites shell commands to its token-saving form. |
| `PreToolUse` | `mcp__plugin_loadout_serena__.*` | `serena-hooks auto-approve --client=claude-code` | 10 s | Serena's own auto-approve hook, for Serena's tools only. |
| `PreToolUse` | `Grep\|Glob` | `--soft codebase-memory-mcp hook-augment` | 5 s | The code-graph server's hook for `Grep` and `Glob`. |
| `PostToolUse` | `Write\|Edit\|MultiEdit` | `--soft python3 hooks/advisor.py record` | 5 s | Remembers a finished implementation plan. |
| `Stop` | all | `--soft python3 hooks/advisor.py stop` | 5 s | Asks once for `/loadout:execution-advisor` after a plan. |
| `SubagentStart` | `*` | `hooks/subagent-context.sh` | 5 s | Gives a subagent one line of tool routing. |

The plugin also declares two MCP servers in `plugins/loadout/.mcp.json`: `serena` and `codebase-memory-mcp`.

### Maintenance

What `loadout hook-session-start` and the background `loadout maintenance` job do: [The daily sync](../explanation/architecture.md#the-daily-sync).

### The execution-advisor hooks

When `advisor.py record` and `advisor.py stop` act, and where they keep state: [When the hook nudges](../explanation/execution-advisor.md#when-the-hook-nudges).

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
