# Security policy

loadout changes your Claude Code configuration and keeps itself current, so it should be clear what it does on its own. The full model, with the code behind each point, is in [Security and trust](docs/explanation/security-and-trust.md). This page is the short version and says how to report a problem.

## What runs automatically

- **Plugin updates.** Claude Code updates plugins from marketplaces with `"autoUpdate": true`: the kit's own and the third-party ones in `settings.base.json`. A plugin can ship hooks, so an update can run new code in your next session.
- **A daily pull.** A session hook starts a background job that runs `git pull --ff-only` on the kit and your personal layer, at most once a day and only when the checkout has no local changes. After a pull with new commits it re-merges settings, applies your personal MCP servers and relinks skills and hook scripts. `LOADOUT_NO_AUTO_PULL=1` turns it off.
- **A weekly version check.** It only queues a notice. Tool binaries are updated only when you run `loadout update`, which shows each command and asks.

Whoever can push to the kit repo, or to your personal layer, reaches every machine that follows it. For a team, use a fork you control. See [The trust boundary](docs/explanation/security-and-trust.md#the-trust-boundary).

## What loadout touches

The kit-managed keys in `~/.claude/settings.json`, links under `~/.claude`, user-scope MCP servers and plugins through the `claude` CLI, `~/.config/loadout/`, one line in your shell startup file, `loadout` on your `PATH`, and git's credential helper for `github.com` when `gh` is logged in. It does not touch your account, claude.ai connectors or credentials. The complete list, including what it leaves alone: [What loadout touches](docs/explanation/security-and-trust.md#what-loadout-touches).

## Where secrets go

Secrets belong in `~/.config/loadout/secrets.env`, which bootstrap creates readable only by you, outside your personal layer. Configs refer to them as `${VAR}`. `loadout adopt` finds plaintext keys and never prints them, and recording your own tools into the personal layer refuses anything that looks like a secret or a private file. See [Secrets](docs/explanation/security-and-trust.md#secrets).

## Backups

Before loadout removes or replaces something, it moves the old item into `~/.claude/backups/loadout-<timestamp>` with a manifest of undo steps, and `loadout restore` replays them. Backups can contain old configs and secrets, so they are created readable only by you (0700, files 0600). Delete old ones when you no longer need them. What restore does not undo: [Undo what loadout changed](docs/how-to/undo-and-restore.md#what-restore-does-not-undo).

## Reporting a vulnerability

Please do not report security problems in a public issue with details.

- Use GitHub's private vulnerability reporting: the repository's **Security** tab, then **Report a vulnerability**.
- If that option is not available yet, open an issue without any details and ask for a private channel.

Include what you found, how to reproduce it, and which commit you tested. You will get an answer as soon as the maintainer can look at it; a fix is released on `main` and noted in the commit history.

## Supported versions

Only the current `main` branch is supported. loadout updates itself from `main`, so fixes reach users through the daily pull and plugin auto-update.
