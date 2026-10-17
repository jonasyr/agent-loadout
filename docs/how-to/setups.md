# Find the path for your setup

loadout runs on several platforms, for Claude Code, Codex or both, and on machines that already have parts set up. This page names the path for each combination and links the page that holds the details. Find your platform and agents in the first table, then your starting point in the second; both apply.

To let your agent run the steps, give it [Set loadout up from inside an agent](install-with-an-agent.md).

## Platform and agents

Run bootstrap as [Getting started](../tutorials/getting-started.md#step-1-run-bootstrap) shows it: on Linux, macOS and in WSL `./bootstrap.sh` in the clone (or the one-liner, with the flags after `bash -s --`); on native Windows `powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap.ps1` in the clone ([native Windows](../tutorials/getting-started.md#experimental-native-windows)). The table names the flags to add. `--agents` takes `claude`, `codex` or `claude,codex`; without it, bootstrap asks in a terminal and sets up Claude Code without one ([Use loadout with Codex](codex.md#switch-it-on)).

| Platform | Claude Code | Codex | Both |
|---|---|---|---|
| Linux, macOS | `--install --agents claude` | `--install --agents codex`. Approve the hooks in `/hooks` once. | `--install --agents claude,codex` |
| Native Windows (experimental) | `--install --agents claude` with `bootstrap.ps1` | `--install --agents codex` with `bootstrap.ps1`; it sets up the Windows Codex home (`%USERPROFILE%\.codex`). | `--install --agents claude,codex` with `bootstrap.ps1`. loadout on Windows does not report a Codex in WSL. |
| WSL 2, Codex in WSL | `--install --agents claude` inside WSL ([WSL 2](wsl.md)) | `--install --agents codex` inside WSL, in a terminal: bootstrap asks which side when it finds only a Windows Codex, and offers to switch the VS Code extension to WSL. Without a terminal add `--codex-side wsl --vscode-wsl` ([which side, the switch](wsl.md#when-your-only-codex-is-the-windows-one)). Log in with `codex login` in WSL. | `--install --agents claude,codex` inside WSL, as in the Codex column |
| WSL 2, Codex on Windows | Not affected: Claude Code in WSL, as in the row above. | `--install --agents codex` with `bootstrap.ps1`, on Windows only (experimental). loadout in WSL does not set up a Codex that runs on Windows ([ADR 0029](../adr/0029-codex-on-windows-and-wsl.md)). | Both sides with `--install --agents claude,codex`: in WSL with `--codex-side windows`, which skips the Codex step there, and `bootstrap.ps1` on Windows, which also sets up Claude Code on Windows (see the note below). |
| WSL 2, Codex on both sides | As in the rows above. | `--install --agents codex` on both sides: in WSL as in the "Codex in WSL" row, on Windows with `bootstrap.ps1`. `loadout check` in WSL warns `Codex (Windows side)` until the Windows side is set up ([Codex on both sides](wsl.md#codex-on-both-sides)). | `--install --agents claude,codex` on both sides; in WSL as in the "Codex in WSL" row. |

**One agent choice for every machine.** `--agents` is stored in your personal layer (`targets.json`), and every machine that uses the layer reads the same choice ([Personal layer](../reference/personal-layer.md#files)). Pass the same `--agents` on each side, or the last run decides for all of them. A split with one personal layer, such as Claude Code only in WSL and Codex only on Windows, is not supported.

Not supported either: one loadout that writes both Codex homes, and a WSL `CODEX_HOME` that points into Windows (`loadout check` warns `Codex home`; [why](wsl.md#a-codex_home-that-points-into-windows)). On a second machine or side, clone your personal layer instead of creating a new one ([Keep your personal layer in a private git repo](personal-repo.md#on-every-further-machine)).

## Starting point

| You start with | What to do | What loadout does |
|---|---|---|
| A fresh machine | The path from the table above. | Installs what is missing and asks only what it needs ([What bootstrap asks](../tutorials/getting-started.md#what-bootstrap-asks)). |
| Agents and tools you set up yourself | The same path. With Claude Code on, bootstrap ends with a review of your existing setup (`loadout adopt`); nothing changes without your answer. With Codex only, bootstrap skips that review: run `loadout adopt` yourself afterwards, which lists the MCP servers and skills only Codex has ([Tools only one agent has](your-own-tools.md#tools-only-one-agent-has)). | Keeps what you set up and asks about each tool it does not manage ([Handle your own tools](your-own-tools.md)). Items it removes or replaces go into a backup first ([Undo](undo-and-restore.md)). |
| Serena already set up for Codex (`serena setup codex`) | The same path. | Uses your Serena server whatever its name, adds no second one, and adds only the Serena hooks your `~/.codex/hooks.json` lacks. If that file is not in loadout's format, it names the entries to add by hand ([Serena's hooks in Codex](../reference/hooks.md#serenas-hooks-in-codex), [ADR 0028](../adr/0028-serena-codex-hooks-in-hooks-json.md)). |
| A repo shared with people who use the other agent | `loadout init` or `loadout profile NAME` in the repo. With Codex on, start `codex` there once and accept the trust question ([Project trust](codex.md#project-trust)). | Writes the repo files of the agents named in the repo's `.loadout.json`, whichever agents are on for you (a repo without the file gets yours, and the plan adds the file). It links a teammate's skills into the agents' skill folders and never moves or deletes files that are already there. It shows a plan and asks before it writes, and `loadout restore` undoes it ([`.loadout.json`](../reference/cli.md#loadoutjson), [ADR 0030](../adr/0030-repo-files-follow-the-repos-agents.md), [Prepare a project](../tutorials/getting-started.md#prepare-a-project)). |
| A repo shared with a teammate on Windows | The same as above. If the teammate's Git has no symlinks (Windows without Developer Mode), the committed skill links arrive as plain files. | Reports it once, with the fix, in `loadout check`, `init` and `profile`; never replaces the files ([Troubleshooting](troubleshooting.md#windows)). |
| A repo on a Windows drive (`/mnt/d`), used from WSL | It works; moving it into the Linux home is faster. | Prints one note in `loadout init` and `loadout profile` ([Repos on /mnt/d](wsl.md#repos-on-mntd)). |

## Codex only on Windows with VS Code

This is OpenAI's recommended setup ([Codex on Windows with WSL](https://learn.chatgpt.com/docs/windows/wsl)): Codex and loadout in WSL, repos in the Linux home, VS Code opened from WSL so its Codex extension runs the Codex in WSL. For an agent, the same steps are in [Set loadout up from inside an agent](install-with-an-agent.md#codex-only-on-windows-with-vs-code).

1. **WSL 2:** in PowerShell, `wsl -l -v` shows version 2 ([WSL 2](wsl.md#1-use-wsl-2-not-wsl-1)). Then open the WSL terminal and run `cd ~`.
2. **bootstrap** inside WSL, as [Getting started](../tutorials/getting-started.md#step-1-run-bootstrap) shows it, with `--install --agents codex --codex-side wsl --vscode-wsl`. `--codex-side wsl` sets up Codex in WSL even when a Windows Codex exists, and `--vscode-wsl` switches VS Code's Codex extension to it, with a backup ([which side, the switch](wsl.md#when-your-only-codex-is-the-windows-one)). Leave out `--vscode-wsl` if you do not use VS Code.
3. **`codex login`** in the WSL terminal.
4. **`/hooks`:** start `codex` in the WSL terminal and approve loadout's hooks once ([Use loadout with Codex](codex.md#switch-it-on)).
5. **The first repo** in the Linux home: `loadout init --agents codex` there shows a plan and asks before it writes. Start `codex` once in the WSL terminal in that repo and accept the trust question ([Project trust](codex.md#project-trust)), then open the repo with `code .` from WSL.
6. **`loadout check`:** each `warn` line names its fix. Its `VS Code` row warns while the extension still runs the Windows Codex.

## Afterwards

Run `loadout check`. Each problem line names its fix; the rest is in [Troubleshooting](troubleshooting.md).
