# Pick your setup

loadout runs on Linux, macOS, WSL 2 and (experimental) native Windows, for Claude Code, Codex or both, in a terminal, in VS Code or in both, and on machines that already have parts set up. This page shows how to pick your path. The flags for each combination are in the [Setup matrix](../reference/setup-matrix.md).

To let your agent run the steps, give it [Set loadout up from inside an agent](install-with-an-agent.md).

## How to pick

1. Find your platform: Linux or macOS, WSL 2, or native Windows (experimental). On Windows, use WSL 2 unless you cannot ([Use loadout on Windows with WSL 2](wsl.md)).
2. Decide the agents: Claude Code, Codex or both. Without a choice, bootstrap asks in a terminal ([the `--agents` flag](../reference/setup-matrix.md#the-flags-and-terms)).
3. Decide the surface: the CLI in a terminal, the VS Code extension, or both.
4. Find your cell in the [Setup matrix](../reference/setup-matrix.md): [Linux and macOS](../reference/setup-matrix.md#linux-and-macos), [WSL 2](../reference/setup-matrix.md#wsl-2), [Codex on Windows or on both sides](../reference/setup-matrix.md#codex-on-windows-or-on-both-sides), [native Windows](../reference/setup-matrix.md#native-windows-experimental). Check your starting point below.
5. Run bootstrap with the flags of your cell ([Getting started](../tutorials/getting-started.md#step-1-run-bootstrap)).
6. Do the steps after it (login, approving the hooks) and run `loadout check`.

## Recommended setups

One recommended path for each platform, agent choice and surface is in the [Setup matrix](../reference/setup-matrix.md). For Codex only on Windows with VS Code, the walkthrough [below](#codex-only-on-windows-with-vs-code) shows the steps in order.

### Linux and macOS

Flags and steps: [Setup matrix, Linux and macOS](../reference/setup-matrix.md#linux-and-macos).

### WSL 2 (recommended on Windows)

Flags and steps: [Setup matrix, WSL 2](../reference/setup-matrix.md#wsl-2).

### Native Windows (experimental)

Flags and steps: [Setup matrix, native Windows](../reference/setup-matrix.md#native-windows-experimental).

### One agent choice for every machine

What `--agents` stores and what is not supported: [Setup matrix](../reference/setup-matrix.md#one-agent-choice-for-every-machine).

## Starting point

| You start with | What to do | What loadout does |
|---|---|---|
| A fresh machine | The path from the [Setup matrix](../reference/setup-matrix.md). | Installs what is missing and asks only what it needs ([What bootstrap asks](../tutorials/getting-started.md#what-bootstrap-asks)). |
| Agents and tools you set up yourself | The same path. With Claude Code on, bootstrap ends with a review of your existing setup (`loadout adopt`); nothing changes without your answer. With Codex only, bootstrap skips that review: run `loadout adopt` yourself afterwards, which lists the MCP servers and skills only Codex has ([Tools only one agent has](../reference/own-tools.md#tools-only-one-agent-has)). | Keeps what you set up and asks about each tool it does not manage ([Handle your own tools](your-own-tools.md)). Items it removes or replaces go into a backup first ([Undo](undo-and-restore.md)). |
| Serena already set up for Codex (`serena setup codex`) | The same path. | Keeps your Serena server and hooks ([Serena already set up](codex.md#what-stays-different)). |
| VS Code with the Claude Code or Codex extension, with or without the CLIs | The VS Code row of the [Setup matrix](../reference/setup-matrix.md) for your platform. | Sets up the agent folders the extensions read; `loadout check` reports per extension and window what it lacks, with the fix ([Use loadout with VS Code](vscode.md)). |
| A repo shared with people who use the other agent | `loadout init` or `loadout profile NAME` in the repo. With Codex on, start `codex` there once and accept the trust question ([Project trust](codex.md#project-trust)). | Writes the repo files of the agents named in the repo's `.loadout.json`, whichever agents are on for you (a repo without the file gets yours, and the plan adds the file). It links a teammate's skills into the agents' skill folders and never moves or deletes files that are already there. It shows a plan and asks before it writes, and `loadout restore` undoes it ([`.loadout.json`](../reference/cli.md#loadoutjson), [ADR 0030](../adr/0030-repo-files-follow-the-repos-agents.md), [Prepare a project](../tutorials/getting-started.md#prepare-a-project)). |
| A repo shared with a teammate on Windows | The same as above. If the teammate's Git has no symlinks (Windows without Developer Mode), the committed skill links arrive as plain files. | Reports it once, with the fix, in `loadout check`, `init` and `profile`; never replaces the files ([Troubleshooting](troubleshooting.md#windows)). |
| A repo on a Windows drive (`/mnt/d`), used from WSL | It works; moving it into the Linux home is faster. | Prints one note in `loadout init` and `loadout profile` ([Repos on /mnt/d](wsl.md#repos-on-mntd)). |

## Codex only on Windows with VS Code

This puts Codex and loadout in WSL, repos in the Linux home, and VS Code opened from WSL so its Codex extension runs the Codex in WSL. The steps use the Codex CLI, which is optional next to VS Code's Codex extension (the extension in WSL alone is a full setup: leave out the CLI answer and approve the hooks in the extension). For an agent, the deltas are in [Set loadout up from inside an agent](install-with-an-agent.md#codex-only-on-windows-with-vs-code).

1. **WSL 2:** in PowerShell, `wsl -l -v` shows version 2 ([WSL 2](wsl.md#1-use-wsl-2-not-wsl-1)). Then open the WSL terminal and run `cd ~`.
2. **bootstrap** inside WSL, as [Getting started](../tutorials/getting-started.md#step-1-run-bootstrap) shows it, with `--install --agents codex --codex-side wsl`. `--codex-side wsl` sets up Codex in WSL even when a Windows Codex exists ([which side](wsl.md#when-your-only-codex-is-the-windows-one)). If you also open repos in a Windows window, add `--vscode-wsl`: it switches VS Code's Codex extension to the Codex in WSL, with a backup.
3. **`codex login`** in the WSL terminal.
4. **Hooks:** start `codex` in the WSL terminal and approve loadout's hooks once in `/hooks` ([Use loadout with Codex](codex.md#switch-it-on)). In VS Code's Codex extension you approve them there instead ([how](vscode.md#codex-in-vs-code-without-the-cli)).
5. **The first repo** in the Linux home: `loadout init --agents codex` there shows a plan and asks before it writes. Start `codex` once in the WSL terminal in that repo and accept the trust question ([Project trust](codex.md#project-trust)), then open the repo with `code .` from WSL. This opens a Remote-WSL window: choose Trust Folder & Continue there, and install VS Code's Codex extension from the Extensions view if it is not in WSL yet ([Codex in VS Code without the CLI](vscode.md#codex-in-vs-code-without-the-cli)).
6. **`loadout check`** in the WSL terminal: each `warn` line names its fix. If it warns `VS Code PATH`, run `loadout bootstrap --vscode-path`, then restart VS Code's WSL server ([how](vscode.md#mcp-servers-in-a-remote-wsl-window)); bootstrap could not add that PATH block in step 2, before the first `code .`. Its `VS Code` row warns while a Windows window's Codex extension still runs the Windows Codex, and for each folder's `.vscode/settings.json` or VS Code profile that sets the switch to `false`, which wins over your user settings ([Windows and WSL](vscode.md#windows-and-wsl)).

## Afterwards

Run `loadout check`. Each problem line names its fix; the rest is in [Troubleshooting](troubleshooting.md).
