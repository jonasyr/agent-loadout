# Getting started

This tutorial takes you from nothing to a first session in Claude Code or Codex with loadout. It follows one path. For details on any step, follow the links to the how-to and reference pages.

## Before you start

| | Linux / WSL | macOS | Windows (experimental) |
|---|---|---|---|
| git and curl | `sudo apt install git curl` (Debian/Ubuntu; other distros: their package manager) | `xcode-select --install` (provides git; curl is included) | `winget install --id Git.Git -e`, then open a new PowerShell (Git Bash runs the hooks) |
| After bootstrap | log in to your agents (`claude`, `codex`), then `gh auth login` and `gh auth setup-git` | same | same |

Bootstrap installs everything else that is missing, in your home folder and without sudo: uv (which also provides Python), the agents you chose (Claude Code, Codex), Node.js, gh and the tools in [Included tools](../reference/included-tools.md#command-line-tools). It never replaces a tool you already have. The installers run without a further prompt; see [Security and trust](../explanation/security-and-trust.md#what-runs-when-you-ask).

Optional, only if you turn on Claude Code's sandbox (Linux, WSL 2): `sudo apt-get install bubblewrap socat`.

## Step 1: Run bootstrap

To let Codex or Claude Code run these steps for you, give it [Set loadout up from inside an agent](../how-to/install-with-an-agent.md).

On Linux, macOS and WSL 2, run the one-liner. It clones the kit into `./agent-loadout` (to choose another folder, add `--dir PATH` after the `--`, for example `bash -s -- --install --dir ~/tools/agent-loadout`) and runs bootstrap:

```bash
cd ~
curl -fsSL https://raw.githubusercontent.com/jonasyr/agent-loadout/main/bootstrap.sh | bash -s -- --install
```

The `cd ~` matters because the clone stays where you run this (on WSL, a shell started from Windows opens in `/mnt/c`).

Prefer to read the code first? Clone it and run the same script:

```bash
git clone https://github.com/jonasyr/agent-loadout && cd agent-loadout && ./bootstrap.sh --install
```

Keep the clone where it is. The installed links point into it. `~/.local/bin/loadout` is a small launcher script. Bootstrap adds `~/.local/bin` and the folders of the tools it installed to your shell profile (block `# loadout PATH`), so open a new terminal when it is done. It ends with the steps still open on your machine.

On Windows, use WSL 2: open a WSL terminal, not PowerShell, and follow the steps above inside WSL. Then read [Use loadout on Windows with WSL 2](../how-to/wsl.md) (WSL version, repo location, Windows binaries on your `PATH`, sandbox packages); `loadout check` warns about each of these it can see.

Go on with [What bootstrap asks](#what-bootstrap-asks).

## Experimental: native Windows

Native Windows is experimental and not recommended. Use WSL 2 if you can.

1. Install Git for Windows (`winget install --id Git.Git -e`), then open a new PowerShell. `bootstrap.ps1` only warns when `bash` is missing, but the hooks of both agents run in Git Bash. Python is not needed: uv provides it.
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

   If you plan to keep secrets in `secrets.env`, also run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`: `Bypass` only lets this one command run, `RemoteSigned` lets your PowerShell profiles (and with them the secrets loader) run. Why: [Troubleshooting, Windows](../how-to/troubleshooting.md#windows).
3. Bootstrap writes the secrets loader into both your Windows PowerShell and PowerShell 7 profiles, and adds the tool folders to your user PATH.
4. Bootstrap installs codebase-memory-mcp with its `install.ps1`. The optional rtk has no Windows install command; install it by hand if you want it.
5. Without Developer Mode, Windows cannot create the links, and loadout copies files instead. Enable Developer Mode and re-run bootstrap to switch back to links. See [Troubleshooting](../how-to/troubleshooting.md).

Go on with [What bootstrap asks](#what-bootstrap-asks).

## What bootstrap asks

Bootstrap is safe to re-run. It works in four steps, prints one status line for each (`--verbose` prints every detail) and asks only where it needs your answer.

1. **Your personal layer.** Paste the git URL of your own personal repo to clone it. Leave it empty to create a starter. The starter asks four short questions about you, then shows the recommended working preferences on one screen: Enter takes them, `n` asks each one. If you already have a personal layer on this machine, bootstrap uses it and asks nothing. To sync it across machines, keep it in a private git repo: [Keep your personal layer in a private git repo](../how-to/personal-repo.md).
2. **Your coding agents.** Claude Code, Codex, or both; bootstrap installs and sets up exactly those. It asks only when your personal layer has not chosen yet: a layer you just cloned, or the one already on this machine, brings its choice (`targets.json`), and bootstrap says so. A starter asks before its own questions. `--agents codex` (or `claude,codex`) chooses without asking and wins over the layer's choice. Bootstrap also skips the question and sets up Claude Code with `--yes`, without a terminal, or when a personal layer exists but `codex` is not installed (details: [`loadout bootstrap`](../reference/cli.md#loadout-bootstrap)). See [Use loadout with Codex](../how-to/codex.md).
3. **Preferences and add-ons.** `Customize preferences and global add-ons now? [y/N]` starts the configure wizard. You can run it later with `loadout configure`. See [Set your working preferences](../how-to/set-preferences.md).
4. **Your existing setup.** If Claude Code already has plugins, MCP servers, skills or hooks, `loadout adopt` reviews them. It offers to remove superseded or duplicate tools, to disable per-project tools globally, and to move plaintext secrets into `secrets.env`. For tools loadout does not manage, it asks whether to record them globally, put them in a personal profile, leave them, or remove them. Nothing changes without your answer. See [Handle your own tools](../how-to/your-own-tools.md).

Items you own that bootstrap removes or replaces go into a backup first. The end of the output names it and shows the undo command. See [Undo what loadout changed](../how-to/undo-and-restore.md).

Without a terminal (CI, `ssh host ./bootstrap.sh`, piped input) bootstrap skips the configure prompt and the adopt step and says so. It still runs `--install` when given, links files, creates a starter personal layer with default preferences if none exists, merges settings, applies your MCP servers and sets up plugins. Pass `--yes` to apply adopt's default groups (remove, migrate, scope-down) plus moving plaintext secrets, without asking. The flags are in the [CLI reference](../reference/cli.md#loadout-bootstrap).

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

## Verify

Restart your agent: Claude Code (or run `/reload-plugins`) and Codex; if you chose only one, restart that one. Then run:

```bash
loadout check
```

It is read-only. It prints `Health check: N of M OK`, then only the problems, and each problem line names the fix (`--verbose` lists every check). If you see `loadout: command not found`, open a new terminal: bootstrap added `~/.local/bin` to your profile (Windows: your user PATH). More in [Troubleshooting](../how-to/troubleshooting.md). What each check means is in the [CLI reference](../reference/cli.md#loadout-check).

## Prepare a project

In a repo, new or old:

```bash
cd my-project
loadout init
```

`loadout init` creates `AGENTS.md`, a `docs/` folder and `.gitignore` entries (with Claude Code on also `CLAUDE.md`), and suggests profiles for domain tools. It never overwrites an existing scaffold file. Profiles write the repo's shared files for the agents that are on, which your teammates' agents read too: for Claude Code `.claude/settings.json`, `.mcp.json` and `.claude/skills`, for Codex `.codex/config.toml` and `.agents/skills`; each agent that is on installs the profile's plugins ([ADR 0027](../adr/0027-repo-files-follow-the-agents.md)). The table is in the [CLI reference](../reference/cli.md#loadout-profile). Add `--dry-run` for a preview (it does not show the settings diff). With Codex on, start `codex` in the repo once and accept the trust question, or Codex ignores the repo's `.codex/config.toml` ([project trust](../how-to/codex.md#project-trust)). Then open your agent in the repo and run the onboard skill:

```
/loadout:onboard      # Claude Code
$loadout:onboard      # Codex
```

The skill reads the project and fills in the documentation. To add a profile later, run `loadout profile <name>` (see [Profile format](../reference/profile-format.md)).

## What happens by itself

After setup you do not have to run anything to stay current.

A session hook pulls the kit and your personal layer once a day, and a weekly check tells you when tool binaries have updates (`loadout update` applies them after asking). Claude Code updates its plugins itself; for Codex, loadout refreshes them after a pull that brought new commits. How this works: [The daily sync](../explanation/architecture.md#the-daily-sync). What runs without asking, and how to opt out, is in [Security and trust](../explanation/security-and-trust.md).

## Next

- Questions or changes from now on: ask your agent in plain words ([Ask your agent about loadout](../how-to/ask-about-loadout.md)).
- Change preferences: [Set your working preferences](../how-to/set-preferences.md).
- Something went wrong: [Undo what loadout changed](../how-to/undo-and-restore.md).
- All commands: [CLI reference](../reference/cli.md).
