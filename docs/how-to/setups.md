# Pick your setup

loadout runs on Linux, macOS, WSL 2 and (experimental) native Windows, for Claude Code, Codex or both, in a terminal, in VS Code or in both, and on machines that already have parts set up. This page names one recommended path for each combination and links the page that holds the details. Find your platform, agents and surface in the first section, then your starting point in the second; both apply.

To let your agent run the steps, give it [Set loadout up from inside an agent](install-with-an-agent.md).

## Recommended setups

Run bootstrap as [Getting started](../tutorials/getting-started.md#step-1-run-bootstrap) shows it, with the flags the tables name: on Linux, macOS and in WSL `./bootstrap.sh` in the clone (or the one-liner, with the flags after `bash -s --`); on native Windows `powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap.ps1` in the clone ([native Windows](../tutorials/getting-started.md#experimental-native-windows)).

`--agents` takes `claude`, `codex` or `claude,codex`. Without it, a personal layer that already chose (`targets.json`) decides; otherwise bootstrap asks in a terminal and sets up Claude Code without one. The default answer is both when bootstrap sees a Codex CLI on your PATH (VS Code's Codex extension alone does not count), else Claude Code ([Use loadout with Codex](codex.md#switch-it-on)). "Surface" is where you use the agent: the CLI in a terminal, the VS Code extension, or both. In VS Code, the recommended surface is the extension with the CLI next to it.

### Linux and macOS

| Surface | Claude Code | Codex | Both |
|---|---|---|---|
| CLI only | `--install --agents claude` | `--install --agents codex`, then `codex login` and approve the hooks once in `/hooks` ([Getting started](../tutorials/getting-started.md#codex-only-approve-the-hooks)) | `--install --agents claude,codex`, then `codex login` and `/hooks` in Codex |
| VS Code extension + CLI (recommended in VS Code) | `--install --agents claude`. The extension reads the same `~/.claude` as the CLI ([Use loadout with VS Code](vscode.md)). | `--install --agents codex`. Bootstrap asks whether to install the Codex CLI next to the extension: answer yes (Enter). Then, in VS Code's terminal, run `codex login`, start `codex` and approve the hooks in `/hooks` ([The Codex CLI alongside VS Code](vscode.md#the-codex-cli-alongside-vs-code)). | `--install --agents claude,codex`, Codex as in the Codex column |
| VS Code extension only | Not a separate path: `--install` also installs the Claude Code CLI, and there is no flag to leave it out. Use the row above. Without `--install`, loadout runs the extension's own `claude` ([Claude Code in VS Code without the CLI](vscode.md#claude-code-in-vs-code-without-the-cli)). | Supported, not recommended: `--install --agents codex --without-codex-cli`. Install the extension first; the flag acts only when the extension's own Codex is new enough ([version](codex.md#switch-it-on)) and no Codex CLI is on your PATH. Without the CLI you lose plugins and `/hooks` ([Codex in VS Code without the CLI](vscode.md#codex-in-vs-code-without-the-cli)). Recommended instead: the row above. | Claude Code as in the row above; Codex as in the Codex column |

### WSL 2 (recommended on Windows)

Run everything inside WSL, with the clone and your repos in the Linux home ([Use loadout on Windows with WSL 2](wsl.md)). In VS Code, open repos in a Remote-WSL window (`code .` from WSL): both extensions then read what loadout set up in WSL ([Windows and WSL](vscode.md#windows-and-wsl)). After the first `code .`, run `loadout check` in WSL; if it warns `VS Code PATH`, run `loadout bootstrap --vscode-path`, then restart VS Code's WSL server (close every Remote-WSL window, run `wsl --shutdown` in Windows, which stops every WSL distro, then reopen the folder; [MCP servers in a Remote-WSL window](vscode.md#mcp-servers-in-a-remote-wsl-window)).

| Surface | Claude Code | Codex | Both |
|---|---|---|---|
| CLI only | `--install --agents claude` | `--install --agents codex`, then `codex login` and `/hooks` in WSL. If your only Codex is the Windows one, answer 1 (WSL) when bootstrap asks which side; without a terminal add `--codex-side wsl` ([which side](wsl.md#when-your-only-codex-is-the-windows-one)). | `--install --agents claude,codex`, Codex as in the Codex column |
| VS Code extension + CLI (recommended in VS Code) | `--install --agents claude`, then `code .` from WSL | `--install --agents codex`, as in the CLI row, then `code .` from WSL. The steps are in [Codex only on Windows with VS Code](#codex-only-on-windows-with-vs-code). | `--install --agents claude,codex`, then `code .` from WSL |
| VS Code extension only | Not a separate path, as on Linux: use the row above. | Supported, not recommended: first install VS Code's Codex extension in WSL (open a Remote-WSL window with `code .` from WSL and install it from the Extensions view there; [VS Code's WSL docs](https://code.visualstudio.com/docs/remote/wsl)), then `--install --agents codex --without-codex-cli`. If bootstrap asks which side, answer 1 (WSL); without a terminal add `--codex-side wsl`, as in the CLI row (VS Code's Codex extension on Windows counts as a Windows Codex until its WSL switch is on). Until the extension is installed in WSL, the flag does nothing and bootstrap installs the CLI. You lose what the Linux row names. Recommended instead: the row above. | Claude Code as in the row above; Codex as in the Codex column |
| A Windows window anyway (not recommended) | The Windows window reads `%USERPROFILE%\.claude`, which loadout in WSL does not set up: `loadout check` warns `VS Code (Claude Code, Windows window)`. Recommended: a Remote-WSL window; or set loadout up on Windows too with `bootstrap.ps1`. | Add `--vscode-wsl`: it switches VS Code's Codex extension to the Codex in WSL, with a backup. In a terminal, bootstrap offers the switch when it sees a Windows Codex. | `--vscode-wsl` covers the Codex extension only; Claude Code as in the Claude Code column |

#### Codex on Windows, or on both sides

| Codex runs | Claude Code | Codex | Both |
|---|---|---|---|
| On Windows only | Not affected: Claude Code in WSL, as in the table above. | `--install --agents codex` with `bootstrap.ps1`, on Windows only (experimental). loadout in WSL does not set up a Codex that runs on Windows ([ADR 0029](../adr/0029-codex-on-windows-and-wsl.md)). | Both sides with `--install --agents claude,codex`: in WSL with `--codex-side windows`, which skips the Codex step there, and `bootstrap.ps1` on Windows, which also sets up Claude Code on Windows (see the note below). |
| On both sides | As in the table above. | `--install --agents codex` on both sides: in WSL as in the table above, on Windows with `bootstrap.ps1`. `loadout check` in WSL warns `Codex (Windows side)` until the Windows side is set up ([Codex on both sides](wsl.md#codex-on-both-sides)). | `--install --agents claude,codex` on both sides; in WSL as in the table above. |

### Native Windows (experimental)

Not recommended: use WSL 2 (the section above) unless you cannot ([why](wsl.md)). With `bootstrap.ps1`, the flags are the same as on Linux and macOS, row for row: `--install --agents claude`, `codex` or `claude,codex`, `--without-codex-cli` for VS Code's Codex extension only (supported, not recommended). It sets up `%USERPROFILE%\.claude` and `%USERPROFILE%\.codex`, which the CLIs and a local VS Code window read. loadout on Windows does not report a Codex in WSL.

### One agent choice for every machine

`--agents` is stored in your personal layer (`targets.json`), and every machine that uses the layer reads the same choice ([Personal layer](../reference/personal-layer.md#files)). Pass the same `--agents` on each side, or the last run's choice reaches the others once the personal layer syncs. A split with one personal layer, such as Claude Code only in WSL and Codex only on Windows, is not supported.

Not supported either: one loadout that writes both Codex homes, and a WSL `CODEX_HOME` that points into Windows (`loadout check` warns `Codex home`; [why](wsl.md#a-codex_home-that-points-into-windows)). On a second machine or side, clone your personal layer instead of creating a new one ([Keep your personal layer in a private git repo](personal-repo.md#on-every-further-machine)).

## Starting point

| You start with | What to do | What loadout does |
|---|---|---|
| A fresh machine | The path from [Recommended setups](#recommended-setups). | Installs what is missing and asks only what it needs ([What bootstrap asks](../tutorials/getting-started.md#what-bootstrap-asks)). |
| Agents and tools you set up yourself | The same path. With Claude Code on, bootstrap ends with a review of your existing setup (`loadout adopt`); nothing changes without your answer. With Codex only, bootstrap skips that review: run `loadout adopt` yourself afterwards, which lists the MCP servers and skills only Codex has ([Tools only one agent has](your-own-tools.md#tools-only-one-agent-has)). | Keeps what you set up and asks about each tool it does not manage ([Handle your own tools](your-own-tools.md)). Items it removes or replaces go into a backup first ([Undo](undo-and-restore.md)). |
| Serena already set up for Codex (`serena setup codex`) | The same path. | Keeps your Serena server and hooks ([Serena already set up](codex.md#what-stays-different)). |
| VS Code with the Claude Code or Codex extension, with or without the CLIs | The VS Code row of [Recommended setups](#recommended-setups) for your platform. | Sets up the agent folders the extensions read; `loadout check` reports per extension and window what it lacks, with the fix ([Use loadout with VS Code](vscode.md)). |
| A repo shared with people who use the other agent | `loadout init` or `loadout profile NAME` in the repo. With Codex on, start `codex` there once and accept the trust question ([Project trust](codex.md#project-trust)). | Writes the repo files of the agents named in the repo's `.loadout.json`, whichever agents are on for you (a repo without the file gets yours, and the plan adds the file). It links a teammate's skills into the agents' skill folders and never moves or deletes files that are already there. It shows a plan and asks before it writes, and `loadout restore` undoes it ([`.loadout.json`](../reference/cli.md#loadoutjson), [ADR 0030](../adr/0030-repo-files-follow-the-repos-agents.md), [Prepare a project](../tutorials/getting-started.md#prepare-a-project)). |
| A repo shared with a teammate on Windows | The same as above. If the teammate's Git has no symlinks (Windows without Developer Mode), the committed skill links arrive as plain files. | Reports it once, with the fix, in `loadout check`, `init` and `profile`; never replaces the files ([Troubleshooting](troubleshooting.md#windows)). |
| A repo on a Windows drive (`/mnt/d`), used from WSL | It works; moving it into the Linux home is faster. | Prints one note in `loadout init` and `loadout profile` ([Repos on /mnt/d](wsl.md#repos-on-mntd)). |

## Codex only on Windows with VS Code

loadout recommends WSL 2 on Windows ([why](wsl.md)). OpenAI names WSL2 for Codex when you need Linux-native tooling, your repos and workflow already live in WSL2, or the Windows sandbox does not meet your needs, and describes this layout ([Codex on Windows with WSL](https://learn.chatgpt.com/docs/windows/wsl)): Codex and loadout in WSL, repos in the Linux home, VS Code opened from WSL so its Codex extension runs the Codex in WSL. These steps install the Codex CLI next to VS Code's Codex extension, the recommended setup. For an agent, the deltas are in [Set loadout up from inside an agent](install-with-an-agent.md#codex-only-on-windows-with-vs-code).

1. **WSL 2:** in PowerShell, `wsl -l -v` shows version 2 ([WSL 2](wsl.md#1-use-wsl-2-not-wsl-1)). Then open the WSL terminal and run `cd ~`.
2. **bootstrap** inside WSL, as [Getting started](../tutorials/getting-started.md#step-1-run-bootstrap) shows it, with `--install --agents codex --codex-side wsl`. `--codex-side wsl` sets up Codex in WSL even when a Windows Codex exists ([which side](wsl.md#when-your-only-codex-is-the-windows-one)). If you also open repos in a Windows window, add `--vscode-wsl`: it switches VS Code's Codex extension to the Codex in WSL, with a backup.
3. **`codex login`** in the WSL terminal.
4. **`/hooks`:** start `codex` in the WSL terminal and approve loadout's hooks once ([Use loadout with Codex](codex.md#switch-it-on)).
5. **The first repo** in the Linux home: `loadout init --agents codex` there shows a plan and asks before it writes. Start `codex` once in the WSL terminal in that repo and accept the trust question ([Project trust](codex.md#project-trust)), then open the repo with `code .` from WSL. This opens a Remote-WSL window; if VS Code's Codex extension is not installed in WSL yet, install it from the Extensions view there ([VS Code's WSL docs](https://code.visualstudio.com/docs/remote/wsl)).
6. **`loadout check`** in the WSL terminal: each `warn` line names its fix. If it warns `VS Code PATH`, run `loadout bootstrap --vscode-path`, then restart VS Code's WSL server (close every Remote-WSL window, run `wsl --shutdown` in Windows, which stops every WSL distro, then reopen the folder): bootstrap could not add that PATH block in step 2, before the first `code .` ([MCP servers in a Remote-WSL window](vscode.md#mcp-servers-in-a-remote-wsl-window)). Its `VS Code` row warns while a Windows window's Codex extension still runs the Windows Codex, and for each folder's `.vscode/settings.json` or VS Code profile that sets the switch to `false`, which wins over your user settings ([Windows and WSL](vscode.md#windows-and-wsl)).

## Afterwards

Run `loadout check`. Each problem line names its fix; the rest is in [Troubleshooting](troubleshooting.md).
