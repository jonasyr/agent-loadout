# Security policy

loadout changes your Claude Code configuration and keeps itself current, so it should be clear what it does on its own. The full model, with the code behind each point, is in [Security and trust](docs/explanation/security-and-trust.md). This page is the short version and says how to report a problem.

## What runs automatically

- **Plugin updates.** Claude Code updates plugins from `claude-plugins-official` (on by default) and from the marketplaces `settings.base.json` sets to `autoUpdate: true` (agent-loadout, impeccable, academic-research-skills). A plugin can ship hooks, so an update can run new code in your next session.
- **A daily pull and a weekly version check.** A background job pulls the kit and your personal layer and re-applies them; the weekly check only queues a notice. How it works and how to turn it off: [The daily sync](docs/explanation/architecture.md#the-daily-sync).
- **Only when you ask: `bootstrap --install`.** It runs the catalog's install commands without a further prompt, including `curl … | sh` installers from the upstream default branch. Tool binaries are otherwise updated only by `loadout update`, which shows each command and asks.

Whoever can push to the kit repo, or to your personal layer, reaches every machine that follows it. For a team, use a fork you control. See [The trust boundary](docs/explanation/security-and-trust.md#the-trust-boundary).

## What loadout touches

The kit-managed keys in `~/.claude/settings.json`, links under `~/.claude`, user-scope MCP servers and plugins through the `claude` CLI, `~/.config/loadout/`, a two-line secrets-loading block in each existing `.bashrc` and `.zshrc` plus the startup file of your `$SHELL` (both PowerShell profiles on Windows), a `loadout` link in `~/.local/bin` (your `PATH` is not edited), and git's credential helper for `github.com` when `gh` is logged in. The plugin's hooks and the kit's settings also pre-approve some tool calls (see [Permissions](docs/explanation/security-and-trust.md#what-loadout-touches)). It does not read or change your Claude login or claude.ai connectors. The complete list, including what it leaves alone: [What loadout touches](docs/explanation/security-and-trust.md#what-loadout-touches).

## Where secrets go

Secrets belong in `~/.config/loadout/secrets.env`, which bootstrap creates readable only by you, outside your personal layer. Configs refer to them as `${VAR}`. `loadout adopt` finds plaintext keys and masks what its patterns recognise when it prints, and recording your own tools into the personal layer refuses anything that looks like a secret or a private file. Values you set with `loadout configure set pref` are not checked. See [Secrets](docs/explanation/security-and-trust.md#secrets).

## Backups

Items you own that loadout removes or replaces go into a private backup under `~/.claude/backups/`, which can hold old configs and secrets; the routine sync of kit-managed state is not backed up. Details, file modes and what restore does not undo: [Undo what loadout changed](docs/how-to/undo-and-restore.md).

## Reporting a vulnerability

Please do not report security problems in a public issue with details.

- Use GitHub's private vulnerability reporting: the repository's **Security** tab, then **Report a vulnerability**.
- If that option is not available yet, open an issue without any details and ask for a private channel.

Include what you found, how to reproduce it, and which commit you tested. You will get an answer as soon as the maintainer can look at it; a fix is released on `main` and noted in the commit history.

## Supported versions

Only the current `main` branch is supported. loadout pulls the branch your clone tracks (`main` by default), so fixes reach users through the daily pull and plugin auto-update.
