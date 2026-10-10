# agent-loadout

**Set up Claude Code the same way on every machine, from a shared kit plus your own settings, and keep it current.**

[![CI](https://github.com/jonasyr/agent-loadout/actions/workflows/ci.yml/badge.svg)](https://github.com/jonasyr/agent-loadout/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Platforms: Linux, macOS, Windows (WSL 2 or native)](https://img.shields.io/badge/platforms-Linux%20%C2%B7%20macOS%20%C2%B7%20Windows%20%28WSL%202%20or%20native%29-informational.svg)](docs/tutorials/getting-started.md)
[![Claude Code plugin](https://img.shields.io/badge/Claude%20Code-plugin-D97757.svg)](.claude-plugin/marketplace.json)

Claude Code gets much better with the right plugins, MCP servers and instructions. But setups drift: every machine ends up different, old tools linger, versions go stale, and half of what is installed never gets used. loadout is a shared kit (this repo) plus a personal layer (your own folder, ideally a private git repo, with your preferences and tools). Its CLI merges both into `~/.claude` and keeps them current; [Architecture](docs/explanation/architecture.md) shows how.

## What you get

- **Curated defaults.** A small set of plugins, MCP servers, command-line tools and rules that complement each other instead of overlapping. Every keep or drop decision has a written reason in [`catalog.json`](catalog.json). See [Included tools](docs/reference/included-tools.md).
- **Works on existing setups.** `loadout adopt` shows what it would change and why, asks first, and backs up what it removes or replaces. See [Handle your own tools](docs/how-to/your-own-tools.md).
- **Stays up to date by itself.** Claude Code updates the plugins; loadout pulls the kit and your personal layer once a day; you get a notice when tool binaries have updates. See [The daily sync](docs/explanation/architecture.md#the-daily-sync).
- **Yours on top.** Your preferences, own tools and profiles live in a separate personal layer, ideally a private git repo. Change them with `loadout configure` or by asking Claude (`/loadout:configure`). See [Set your working preferences](docs/how-to/set-preferences.md).
- **Projects too.** `loadout init` prepares any repo, empty or years old, for agent work, and per-project profiles add domain tools only where you need them. Three skills write and maintain the repo's documentation. See [Documentation strategy](docs/explanation/documentation-strategy.md).

## Why you can trust it

- **It updates itself, so you trust this repo.** Once a day a background job runs `git pull --ff-only` on this repo and your personal layer, and the next session runs that code. Turn it off with `LOADOUT_NO_AUTO_PULL=1`, or point your clone at a fork you review. See [The daily sync](docs/explanation/architecture.md#the-daily-sync).
- **Your own items can be restored.** Before loadout removes or replaces a tool, file or link you own, it moves it into a timestamped backup under `~/.claude/backups/`, and `loadout restore` puts it back (a restore can be undone too). The routine sync of what the kit itself manages (managed settings keys, your personal MCP servers) is not backed up; your personal layer's git history is the record. [Details](docs/how-to/undo-and-restore.md#what-restore-does-not-undo).
- **Your tools never change without your answer.** `loadout adopt` is a dry run until you pass `--apply`, then asks per group and once more before it applies anything (without a terminal it needs an explicit `--yes`, `--groups` or `--own`). Tools loadout does not know stay exactly as they are until you decide, and binary updates show each command and ask first.
- **Secrets stay out of git.** Keys live in `~/.config/loadout/secrets.env` (readable only by you, outside your personal layer) and configs refer to them as `${VAR}`. Your own tools recorded into your personal layer pass a secret guard that refuses what it cannot move safely. Values you set yourself with `configure set pref` are not checked. Printed lines are redacted where the patterns recognise a secret.

What runs automatically, what loadout touches and where the trust boundary is: [Security and trust](docs/explanation/security-and-trust.md). To report a vulnerability, see [SECURITY.md](SECURITY.md).

## Quick start

You need Claude Code, git, Python 3.10+, Node.js and gh; `--install` adds uv and the rest of the tools where it has an install command for your platform. `--install` runs those installers without a further prompt (see [Security and trust](docs/explanation/security-and-trust.md#what-runs-when-you-ask)). Full requirements and every step: [Getting started](docs/tutorials/getting-started.md).

**Linux, macOS and WSL 2** (WSL 2 is the recommended setup on Windows; read [Use loadout on Windows with WSL 2](docs/how-to/wsl.md) first):

```bash
git clone https://github.com/jonasyr/agent-loadout ~/agent-loadout
cd ~/agent-loadout
./bootstrap.sh --install
```

**Native Windows** (PowerShell, with Git for Windows installed; see [Native Windows](docs/tutorials/getting-started.md#native-windows)):

```powershell
git clone https://github.com/jonasyr/agent-loadout $HOME\agent-loadout
cd $HOME\agent-loadout
powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap.ps1 --install
```

If you plan to keep secrets in `secrets.env`, also run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`: `Bypass` only lets this one command run, `RemoteSigned` lets your PowerShell profiles (and with them the secrets loader) run.

Keep the clone where it is: the installed links point into it. Bootstrap walks you through three steps (your personal layer, preferences, your existing setup), and, if it replaced anything, names the backup and the undo command. Then restart Claude Code and run the read-only health check (if `loadout` is not found, add `~/.local/bin` to your `PATH`; on Windows `%USERPROFILE%\.local\bin`):

```bash
loadout check
```

In a project, run `loadout init` and then `/loadout:onboard` in Claude Code.

## Learn more

The full index is [docs/README.md](docs/README.md).

| I want to | Read |
|---|---|
| Install step by step, per platform | [Getting started](docs/tutorials/getting-started.md) |
| Decide what happens to tools I already have | [Handle your own tools](docs/how-to/your-own-tools.md) |
| Undo something loadout changed | [Undo what loadout changed](docs/how-to/undo-and-restore.md) |
| Change my preferences or add tools globally | [Set your working preferences](docs/how-to/set-preferences.md) |
| Add domain tools to one repo | [Write a personal profile](docs/how-to/write-a-profile.md), [Profile format](docs/reference/profile-format.md) |
| Fix a problem | [Troubleshooting](docs/how-to/troubleshooting.md) |
| Look up a command, flag or exit code | [CLI reference](docs/reference/cli.md) |
| See which tools are included and why | [Included tools](docs/reference/included-tools.md) |
| Understand how the parts fit together | [Architecture](docs/explanation/architecture.md) |
| Know why it was built this way | [Decision records](docs/adr/README.md) |
| Remove loadout | [Uninstall loadout](docs/how-to/uninstall.md) |
| Contribute | [CONTRIBUTING.md](CONTRIBUTING.md) |

Other agents (Codex, Gemini CLI, Cursor) are not supported yet; the plan is in [Architecture](docs/explanation/architecture.md#other-agents-planned).

## License

[MIT](LICENSE)
