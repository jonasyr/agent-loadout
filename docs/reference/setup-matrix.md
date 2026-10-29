# Setup matrix

For each platform, agent choice and surface, the bootstrap flags and the steps after it. How to pick your cell: [Pick your setup](../how-to/setups.md). Run bootstrap as [Getting started](../tutorials/getting-started.md#step-1-run-bootstrap) shows it, with the flags the tables name: on Linux, macOS and in WSL `./bootstrap.sh` in the clone (or the one-liner, with the flags after `bash -s --`); on native Windows `powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap.ps1` in the clone ([native Windows](../tutorials/getting-started.md#experimental-native-windows)).

## The flags and terms

- **`--agents`** takes `claude`, `codex` or `claude,codex`. Without it, a personal layer that already chose (`targets.json`) decides. Otherwise bootstrap asks in a terminal; with an existing personal layer and no Codex on PATH it asks nothing and sets up Claude Code. The default answer is both when bootstrap sees a Codex CLI on your PATH (VS Code's Codex extension alone does not count), else Claude Code ([Use loadout with Codex](../how-to/codex.md#switch-it-on)).
- **Surface** is where you use the agent: the CLI in a terminal, the VS Code extension, or both.
- **`--install`** runs the installers for missing tools. With the Claude Code extension the Claude Code CLI is optional, like the Codex CLI: in a terminal bootstrap asks `Install the Claude Code CLI too (optional, for claude in a terminal)? [y/N]` (default No); without a terminal, or with `--yes`, it installs it. Without `--install`, or when you decline, loadout runs the extension's own `claude` ([Claude Code in VS Code without the CLI](../how-to/vscode.md#claude-code-in-vs-code-without-the-cli)).
- **`--without-codex-cli`** skips the optional Codex CLI question and its install, when VS Code's Codex extension runs its own codex ([The Codex CLI alongside VS Code](../how-to/vscode.md#the-codex-cli-alongside-vs-code)).
- **`--without-claude-cli`** skips the optional Claude Code CLI question and its install, when VS Code's Claude Code extension is there and no `claude` is on PATH ([Claude Code in VS Code without the CLI](../how-to/vscode.md#claude-code-in-vs-code-without-the-cli)).
- **`--codex-side wsl|windows`** (WSL) picks the side bootstrap sets Codex up for, without asking ([which side](../how-to/wsl.md#when-your-only-codex-is-the-windows-one)).
- **`--vscode-wsl`** (WSL) switches VS Code's Codex extension to the Codex in WSL, with a backup ([Windows and WSL](../how-to/vscode.md#windows-and-wsl)).
- **`--vscode-path`** (WSL) adds loadout's tool folders to the PATH of VS Code's Remote-WSL server ([MCP servers in a Remote-WSL window](../how-to/vscode.md#mcp-servers-in-a-remote-wsl-window)).
- **Approve the hooks** means: in the Codex CLI, start `codex` and trust them when it asks (or review them in `/hooks`); in VS Code's Codex extension, the hooks icon in the prompt bar, then Allow all ([Codex in VS Code without the CLI](../how-to/vscode.md#codex-in-vs-code-without-the-cli)). Do it once, and again after loadout's hooks change.

## Linux and macOS

| Surface | Claude Code | Codex | Both |
|---|---|---|---|
| CLI only | `--install --agents claude` | `--install --agents codex`, then `codex login` and approve the hooks | `--install --agents claude,codex`, then `codex login` and approve the hooks |
| VS Code extension | `--install --agents claude`. The extension reads the same `~/.claude` as the CLI ([Use loadout with VS Code](../how-to/vscode.md)). In a terminal bootstrap asks whether to also install the Claude Code CLI (optional, default No); add --without-claude-cli to skip it. | First open the folder in VS Code and choose Trust Folder & Continue. Then `--install --agents codex`: loadout installs its plugins with the extension's own Codex. In a terminal bootstrap asks whether to also install the Codex CLI (optional, default No). Then approve the hooks. | `--install --agents claude,codex`, Codex as in the Codex column |
| VS Code extension + CLI (optional) | As in the row above. | As in the row above, and answer yes to the Codex CLI question. Run `codex login` in VS Code's terminal if you use `codex` there; both read the same `~/.codex`. | As in the row above |

## WSL 2

Run everything inside WSL, with the clone and your repos in the Linux home ([Use loadout on Windows with WSL 2](../how-to/wsl.md)). In VS Code, open repos in a Remote-WSL window (`code .` from WSL) ([Windows and WSL](../how-to/vscode.md#windows-and-wsl)). After the first `code .`, run `loadout check` in WSL; if it warns `VS Code PATH`, run `loadout bootstrap --vscode-path`, then restart VS Code's WSL server ([how](../how-to/vscode.md#mcp-servers-in-a-remote-wsl-window)).

| Surface | Claude Code | Codex | Both |
|---|---|---|---|
| CLI only | `--install --agents claude` | `--install --agents codex`, then `codex login` and approve the hooks. If your only Codex is the Windows one, answer 1 (WSL) when bootstrap asks which side; without a terminal add `--codex-side wsl` ([which side](../how-to/wsl.md#when-your-only-codex-is-the-windows-one)). | `--install --agents claude,codex`, Codex as in the Codex column |
| VS Code extension | `--install --agents claude`, then `code .` from WSL | First install VS Code's Codex extension in WSL (open a Remote-WSL window with `code .` from WSL and install it from the Extensions view there; [VS Code's WSL docs](https://code.visualstudio.com/docs/remote/wsl)) and choose Trust Folder & Continue. Then `--install --agents codex`. If bootstrap asks which side, answer 1 (WSL); without a terminal add `--codex-side wsl`, as in the CLI row (VS Code's Codex extension on Windows counts as a Windows Codex until its WSL switch is on). Then approve the hooks. Until the extension is installed in WSL, bootstrap sets up the Codex CLI instead. More: [Codex only on Windows with VS Code](../how-to/setups.md#codex-only-on-windows-with-vs-code). | `--install --agents claude,codex`, then `code .` from WSL |
| VS Code extension + CLI (optional) | As in the row above. | As in the row above, and answer yes to the Codex CLI question. | As in the row above |
| A Windows window anyway (not recommended) | The Windows window reads `%USERPROFILE%\.claude`, which loadout in WSL does not set up: `loadout check` warns `VS Code (Claude Code, Windows window)`. Use a Remote-WSL window instead, or set loadout up on Windows too with `bootstrap.ps1`. | Add `--vscode-wsl`. In a terminal, bootstrap offers the switch when it sees a Windows Codex. | `--vscode-wsl` covers the Codex extension only; Claude Code as in the Claude Code column |

### Codex on Windows, or on both sides

| Codex runs | Claude Code | Codex | Both |
|---|---|---|---|
| On Windows only | Not affected: Claude Code in WSL, as in the table above. | `--install --agents codex` with `bootstrap.ps1`, on Windows only (experimental). loadout in WSL does not set up a Codex that runs on Windows ([ADR 0029](../adr/0029-codex-on-windows-and-wsl.md)). | Both sides with `--install --agents claude,codex`: in WSL with `--codex-side windows`, which skips the Codex step there, and `bootstrap.ps1` on Windows, which also sets up Claude Code on Windows. |
| On both sides | As in the table above. | `--install --agents codex` on both sides: in WSL as in the table above, on Windows with `bootstrap.ps1`. `loadout check` in WSL warns `Codex (Windows side)` until the Windows side is set up ([Codex on both sides](../how-to/wsl.md#codex-on-both-sides)). | `--install --agents claude,codex` on both sides; in WSL as in the table above. |

## Native Windows (experimental)

With `bootstrap.ps1`, the flags are the same as on Linux and macOS, row for row: `--install --agents claude`, `codex` or `claude,codex`, `--without-codex-cli` to skip the optional Codex CLI question, and `--without-claude-cli` for the Claude Code CLI. It sets up `%USERPROFILE%\.claude` and `%USERPROFILE%\.codex`, which the CLIs and a local VS Code window read ([VS Code on native Windows](../how-to/vscode.md#vs-code-on-native-windows)). loadout on Windows does not report a Codex in WSL.

## One agent choice for every machine

`--agents` is stored in your personal layer (`targets.json`), and every machine that uses the layer reads the same choice ([Personal layer](personal-layer.md#files)). Pass the same `--agents` on each side, or the last run's choice reaches the others once the personal layer syncs. A split with one personal layer, such as Claude Code only in WSL and Codex only on Windows, is not supported.

Not supported either: one loadout that writes both Codex homes, and a WSL `CODEX_HOME` that points into Windows (`loadout check` warns `Codex home`; [details](../how-to/wsl.md#a-codex_home-that-points-into-windows)). On a second machine or side, clone your personal layer instead of creating a new one ([Keep your personal layer in a private git repo](../how-to/personal-repo.md#on-every-further-machine)).
