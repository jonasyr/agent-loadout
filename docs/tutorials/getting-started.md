# Getting started

This tutorial takes you from nothing to a first session in Claude Code or Codex with loadout. It follows one path: Linux, macOS or WSL 2, in a terminal, with bootstrap asking its questions. To choose your platform, agents and surface (terminal, VS Code or both) first, read [Pick your setup](../reference/setup-matrix.md); it names the flags for each path. For details on any step, follow the links.

## Before you start

| | Linux / WSL | macOS | Windows (experimental) |
|---|---|---|---|
| git and curl | `sudo apt install git curl` (Debian/Ubuntu; other distros: their package manager) | `xcode-select --install` (provides git; curl is included) | `winget install --id Git.Git -e`, then open a new PowerShell (Git Bash runs the hooks) |
| After bootstrap | log in to your agents (`claude`, `codex`), then `gh auth login` and `gh auth setup-git` | same | same |

Bootstrap installs everything else that is missing, in your home folder and without sudo: uv (which also provides Python), the agents you chose (Claude Code, Codex), Node.js, gh and the tools in [Included tools](../reference/included-tools.md#command-line-tools). It never replaces a tool you already have. The installers run without a further prompt (one exception: with VS Code's Codex extension and no Codex CLI, bootstrap asks before it installs the Codex CLI); see [Security and trust](../explanation/security-and-trust.md#what-runs-when-you-ask).

Optional, only if you turn on Claude Code's sandbox (Linux, WSL 2): `sudo apt-get install bubblewrap socat`.

Working in VS Code? The steps are the same; what differs is in [Use loadout with VS Code](../how-to/vscode.md).

## Step 1: Run bootstrap

On Linux, macOS and WSL 2, run the one-liner. It clones the kit into `./agent-loadout` (to choose another folder, add `--dir PATH` after the `--`, for example `bash -s -- --install --dir ~/tools/agent-loadout`) and runs bootstrap:

```bash
cd ~
curl -fsSL https://raw.githubusercontent.com/jonasyr/agent-loadout/main/bootstrap.sh | bash -s -- --install
```

The `cd ~` matters because the clone stays where you run this (in WSL, a shell started from Windows opens in `/mnt/c`).

Prefer to read the code first? Clone it and run the same script:

```bash
git clone https://github.com/jonasyr/agent-loadout && cd agent-loadout && ./bootstrap.sh --install
```

Keep the clone where it is. The installed links point into it. `~/.local/bin/loadout` is a small launcher script. Bootstrap adds `~/.local/bin` and the folders of the tools it installed to your shell profile (block `# loadout PATH`), so open a new terminal when it is done. It ends with the steps still open on your machine.

On Windows, use WSL 2: open a WSL terminal, not PowerShell, and run the steps above inside WSL. Then read [Use loadout on Windows with WSL 2](../how-to/wsl.md); `loadout check` warns about each problem from that page it can see.

Go on with [What bootstrap asks](#what-bootstrap-asks).

## Experimental: native Windows

Native Windows is experimental and not recommended. Use WSL 2 if you can.

1. Install Git for Windows (`winget install --id Git.Git -e`), then open a new PowerShell. The hooks of both agents run in Git Bash. Python is not needed: uv provides it.
2. In PowerShell, run the one-liner (it clones into `.\agent-loadout` in the current folder):

   ```powershell
   cd $HOME
   & ([scriptblock]::Create((irm https://raw.githubusercontent.com/jonasyr/agent-loadout/main/bootstrap.ps1))) --install
   ```

   Or clone and run the script, bypassing the execution policy for this one command:

   ```powershell
   git clone https://github.com/jonasyr/agent-loadout $HOME\agent-loadout
   cd $HOME\agent-loadout
   powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap.ps1 --install
   ```

What differs from the path above:

- Bootstrap writes the secrets loader into your Windows PowerShell and PowerShell 7 profiles and adds the tool folders to your user PATH. If you keep secrets in `secrets.env`, also run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` so those profiles run ([why](../how-to/troubleshooting.md#windows)).
- codebase-memory-mcp is installed with its `install.ps1`. The optional rtk has no Windows install command; install it by hand if you want it.
- Without Developer Mode, Windows cannot create links, and loadout copies files instead. Turn on Developer Mode and re-run bootstrap to switch back to links ([Troubleshooting](../how-to/troubleshooting.md#windows)).

Go on with [What bootstrap asks](#what-bootstrap-asks).

## What bootstrap asks

Bootstrap is safe to re-run. It prints one status line per stage (`--verbose` prints every detail) and asks only where it needs your answer, in this order:

1. **Your personal layer.** `Personal layer: git URL to clone (empty = create a starter one):` Paste the git URL of your own personal repo to clone it, or press Enter to create a starter. If a personal layer already exists on this machine, bootstrap uses it and asks nothing. To sync it across machines, keep it in a private git repo: [Keep your personal layer in a private git repo](../how-to/personal-repo.md).
2. **Your coding agents.** `Which coding agents should loadout set up?  1) Claude Code  2) Codex  3) both  [1]`. Bootstrap installs and sets up exactly those. Enter takes the default in brackets: both (`[3]`) when bootstrap sees a Codex (a Codex CLI; VS Code's Codex extension alone does not count), that is a `codex` on your PATH or, in WSL, a Windows `codex.exe`; otherwise Claude Code (`[1]`). A layer that already chose brings its choice (`targets.json`); after a clone bootstrap says so (`using your personal layer's agents: ...`). With an existing personal layer and no Codex on PATH, it asks nothing and sets up Claude Code. With a starter, this question comes before the starter's own questions. See [Use loadout with Codex](../how-to/codex.md); flags, and when bootstrap does not ask: [`loadout bootstrap`](../reference/cli.md#loadout-bootstrap).
3. **About you (starter only).** Four short questions (name, role, main languages, anything else about how you work), then the recommended working preferences on one screen: `Use these? [Y/n]`. Enter takes them; `n` asks each one.
4. **Only in some setups.** In WSL with a Codex on Windows: which side to set up (`Your Codex runs on Windows. Set loadout up for:  1) Codex in WSL (…)  2) Codex on Windows (…)  [1]`) and whether to switch VS Code's Codex extension to WSL ([Codex in WSL](../how-to/wsl.md#codex)). With VS Code's Codex extension, no Codex CLI and `--install`: `Install the Codex CLI too (optional, for codex in a terminal)? [y/N]`; Enter (no) is fine ([The Codex CLI alongside VS Code](../how-to/vscode.md#the-codex-cli-alongside-vs-code)).
5. **Preferences and add-ons.** `Customize preferences and global add-ons now? [y/N]` starts the configure wizard. Enter skips it; the defaults are the recommended ones, and you can run it later with `loadout configure`. See [Set your working preferences](../how-to/set-preferences.md).
6. **Your existing setup (with Claude Code on).** If Claude Code already has plugins, MCP servers, skills or hooks, `loadout adopt` reviews them. It offers to remove superseded or duplicate tools, to disable per-project tools globally, and to move plaintext secrets into `secrets.env`. For tools loadout does not manage, it asks whether to record them globally, put them in a personal profile, leave them, or remove them. Nothing changes without your answer. See [Handle your own tools](../how-to/your-own-tools.md).
7. **VS Code's PATH (WSL only).** In WSL with VS Code's Remote-WSL server (`~/.vscode-server`), when a tool folder is missing from its PATH, bootstrap prints a plan and asks `Add loadout's tool folders to PATH for VS Code's Remote-WSL windows (~/.vscode-server/server-env-setup, backup first)? [y/N]` ([MCP servers in a Remote-WSL window](../how-to/vscode.md#mcp-servers-in-a-remote-wsl-window)).

Items you own that bootstrap removes or replaces go into a backup first. The end of the output shows how to undo it (`Undo any time: loadout restore --list`); `--verbose` also names the backup folder. See [Undo what loadout changed](../how-to/undo-and-restore.md).

Without a terminal (CI, `ssh host ./bootstrap.sh`, piped input), or with `--yes`, bootstrap asks nothing and takes the defaults. What it then does and skips is in the [CLI reference](../reference/cli.md#when-bootstrap-does-not-ask).

## Log in

Open a new terminal so the new PATH applies. Then do the "Still to do" items bootstrap printed:

```bash
claude                                  # log in to Claude Code
codex                                   # log in to Codex (if you chose it)
gh auth login && gh auth setup-git      # log in to GitHub
```

Log in only to the agents you chose.

### Codex only: approve the hooks

Codex runs plugin hooks, and the Serena hooks loadout writes into `~/.codex/hooks.json`, only after you approve them. Start `codex`, run `/hooks` and approve them. loadout never does this for you; which hooks there are is in [Hooks](../reference/hooks.md).

Using VS Code's Codex extension without the Codex CLI? The extension has its own hook review instead of `/hooks`, and you log in to MCP servers in the extension. The steps are in [Codex in VS Code without the CLI](../how-to/vscode.md#codex-in-vs-code-without-the-cli).

## Verify

Restart your agent: Claude Code (or run `/reload-plugins`) and Codex; if you chose only one, restart that one. In VS Code, reload the window (Developer: Reload Window). Then run:

```bash
loadout check
```

It is read-only. It prints `Health check: N of M OK`, then only the problems, and each problem line names the fix (`--verbose` lists every check). If you see `loadout: command not found`, open a new terminal: bootstrap added `~/.local/bin` to your profile (Windows: your user PATH). More in [Troubleshooting](../how-to/troubleshooting.md). What each check means is in the [CLI reference](../reference/cli.md#loadout-check).

## Prepare a project

In a project folder (`loadout init` offers `git init` if it is not a git repo yet):

```bash
cd my-project
loadout init
```

1. **Agents.** `Which agents is this repo for? 1 Claude Code, 2 Codex, 3 both`. Enter takes the agents you use. The answer decides the repo's files for everyone who clones it, so pick the agents your team uses. A repo whose `.loadout.json` already names its agents is not asked.
2. **Profiles.** It prints the profiles (domain tools) it suggests for what it finds in the repo, then asks `profiles to apply (comma separated, empty = suggested, '-' = none):`. Enter takes the suggested ones.
3. **The plan.** It lists every file it would write: `.loadout.json` (the repo's agents, commit it), `AGENTS.md`, a `docs/` folder, `.gitignore` entries (with Claude Code also `CLAUDE.md`), and the shared files the profiles write for the repo's agents. It never overwrites an existing scaffold file. Which files each agent gets: [`loadout profile`](../reference/cli.md#loadout-profile).
4. **Apply.** `Apply these changes? [y/N]`: answer `y`. The run ends with `undo: loadout restore <dir>`; a planned `git init` is the one step restore does not undo.
5. **Codex only: trust the repo.** Start `codex` in the repo once and accept the trust question, or Codex ignores the repo's `.codex/config.toml` ([Project trust](../how-to/codex.md#project-trust)).

Then open your agent in the repo and run the onboard skill:

```
/loadout:onboard      # Claude Code
$loadout:onboard      # Codex
```

The skill reads the project and fills in the documentation. To add a profile later, run `loadout profile <name>`: it shows its plan and asks too (see [Profile format](../reference/profile-format.md)).

## What happens by itself

After setup you do not have to run anything to stay current.

A session hook pulls the kit and your personal layer once a day, and a weekly check tells you when tool binaries have updates. `loadout update` is the one command that brings a machine current: it pulls, shows one plan, and after one yes re-applies the setup, installs what is new and updates the tools; it ends with what to do next ([`loadout update`](../reference/cli.md#loadout-update)). Claude Code updates its plugins itself; for Codex, loadout refreshes them after a pull that brought new commits, when Codex is usable (the Codex CLI, or VS Code's Codex extension's own codex). How this works: [The daily sync](../reference/state-and-sync.md#the-daily-sync). What runs without asking, and how to opt out, is in [Security and trust](../explanation/security-and-trust.md).

## Next

- Questions or changes from now on: ask your agent in plain words ([Ask your agent about loadout](../how-to/ask-about-loadout.md)).
- Let your agent run these steps on the next machine: [Set loadout up from inside an agent](../how-to/install-with-an-agent.md).
- Change preferences: [Set your working preferences](../how-to/set-preferences.md).
- Something went wrong: [Undo what loadout changed](../how-to/undo-and-restore.md).
- All commands: [CLI reference](../reference/cli.md).
