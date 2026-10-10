# 0018. The secret guard fails closed

- Status: Accepted
- Date: 2026-10-10
- Source: [Adopt design, section 5](../superpowers/specs/2026-10-10-adopt-own-tools-design.md#5-errors-undo-safety) and the rulings from the review and fix passes (summarised below)

## Context
Recording your own tools copies hooks, skill files, MCP configs and marketplace sources into the personal layer, which the commit offer can push to a remote. A secret that gets in there is published. Heuristics for "looks like a secret" have both kinds of error, and the reviews found cases of each: a hook token that copied any home file (including an SSH key), binary and UTF-16 files that were never scanned, and patterns that took seconds on long input.

## Decision
Nothing that looks like a secret or a private file is written to the personal layer. When the guard cannot tell (for example an unreadable file), it refuses and the item stays as it is. MCP `env` and `headers` values become `${VAR}` with the value moved to `secrets.env`. Secrets in args, URLs, hook commands, skill files or marketplace sources are refused with an instruction to move them by hand. A denylist of private paths applies, and every printed line is redacted. Scans of long input run in linear time.

## Alternatives considered
- Fail open (copy what the scan could not read): a single missed file leaks.
- Warn and let the user decide: the user cannot see the content that was masked, and the commit offer could push it.
- A secret-scanning dependency: the kit is stdlib only.

## Consequences
- Some ordinary items are refused, for example a skill with a line like `auth: bearer-token-required`, or a dev default such as `POSTGRES_PASSWORD: postgres`. The user fixes the item and retries. This is deliberate.
- Scanning skills takes roughly 2 s per MB.
- The commit offer refuses while a private file would be committed.
- Detection is heuristic. It lowers the risk, and the personal repo still has to be private.

## In the code
- `cli/loadout/own.py` (`_refuse_if_secret`, `_scan_tree`, `_secret_free`, `_private_in_raw`, `_portable_hook`)
- `cli/loadout/secrets.py` (`redact`, `looks_secret`, `private_path`, `PRIVATE_DIRS`, `PRIVATE_NAMES`)
- `cli/loadout/configure.py` (`offer_commit`)
- Guide: [the secret guard](../how-to/your-own-tools.md#secret-guard)
