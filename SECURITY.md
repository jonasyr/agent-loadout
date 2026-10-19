# Security policy

loadout changes your Claude Code and Codex configuration and keeps itself current, so it should be clear what it does on its own. That model lives in one place, [Security and trust](docs/explanation/security-and-trust.md), with the code behind each point:

- [What runs automatically](docs/explanation/security-and-trust.md#what-runs-automatically) and [what runs when you ask](docs/explanation/security-and-trust.md#what-runs-when-you-ask)
- [What loadout touches](docs/explanation/security-and-trust.md#what-loadout-touches), and what it leaves alone
- [Where secrets go](docs/explanation/security-and-trust.md#secrets)
- [Backups and restore](docs/explanation/security-and-trust.md#backups-and-restore)
- [The trust boundary](docs/explanation/security-and-trust.md#the-trust-boundary): who can reach your machine through the kit or your personal layer
- [Opting out](docs/explanation/security-and-trust.md#opting-out)

This page says how to report a problem.

## Reporting a vulnerability

Please do not report security problems in a public issue with details.

- Use GitHub's private vulnerability reporting: the repository's **Security** tab, then **Report a vulnerability**.
- If that option is not available yet, open an issue without any details and ask for a private channel.

Include what you found, how to reproduce it, and which commit you tested. You will get an answer as soon as the maintainer can look at it; a fix is released on `main` and noted in the commit history.

## Supported versions

Only the current `main` branch is supported. loadout pulls the branch your clone tracks (`main` by default), so fixes reach users through the daily pull, plugin auto-update in Claude Code and loadout's plugin refresh for the Codex CLI.
