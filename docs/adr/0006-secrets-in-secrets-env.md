# 0006. Secrets live in secrets.env and are referenced as ${VAR}

- Status: Accepted
- Date: 2026-10-08
- Source: [Design spec, decision D6 and section 13](../superpowers/specs/2026-10-08-agent-loadout-design.md#2-decisions)

## Context
MCP servers often need API keys. Users put them straight into `~/.claude.json` or into a repo, where they leak. The kit must never add a plaintext secret to a git repo, to `~/.claude.json` or to `settings.json`.

## Decision
Secrets live in an untracked file, `~/.config/loadout/secrets.env` (mode 600). The shell loads it at start. MCP configs refer to a value as `${VAR}`. `bootstrap` adds the loading line to the shell profile, and `adopt` moves plaintext keys of user-scope servers into the file.

## Alternatives considered
- Store secrets in the personal repo: even a private repo is a poor place for them and it syncs them to every machine.
- Use an OS keychain: not the same on Linux, macOS and Windows, and Claude Code expands `${VAR}` from the environment.

## Consequences
- Configs in git hold only `${VAR}` names. A new machine needs the values entered once.
- The shell profile must load the file, so an app started without that shell does not see the variables.
- Printed output is masked where the patterns recognise a secret (see [0018](0018-secret-guard-fails-closed.md) for the stricter guard on recorded tools).

## In the code
- `cli/loadout/bootstrap.py` (`setup_secrets`, `RC_LINE`, `PS_BLOCK`)
- `cli/loadout/secrets.py` (`scan`, `rewrite`, `append_env`, `redact`, `load_env`)
- `cli/loadout/adopt.py` (`fix_secrets`)
- `secrets.env.example`
