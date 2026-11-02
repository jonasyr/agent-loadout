# Design: use loadout's Serena ("start clean"), draft

- Status: draft for review (2026-10-31), not committed
- Source: backlog "IDEA (2026-10-29)" in `.superpowers/handoff/2026-10-13-hardening-backlog.md`; produced by an agent-team test (mapper, designer, critic). Working notes: `.superpowers/handoff/team/{mapper,designer,critic}.md`.

## 1. Premise correction

The backlog assumed an existing Serena is always kept. That holds for Codex only.

- Claude Code: an own Serena in `~/.claude.json` matches catalog `mcp-serena` (`core`), so `classify` makes it `migrate` (`cli/loadout/inventory.py:224-234`). `migrate` is in `adopt.DEFAULT_ALL` (`cli/loadout/adopt.py:18`), so Enter and `bootstrap --yes` already remove it, backed up with an `add-json` undo (`adopt.py:309-311`). Unlike codebase-memory (`inventory.py:217`, ADR 0041) there is no exemption for a Serena with its own settings, so a tuned fork or env variant goes silently on `--yes`.
- Codex: an own Serena table is never an adopt item (`inventory.py:130`); loadout writes no table of its own and prints `codex.SERENA_KEPT` (`bootstrap.py:1143`, ADR 0028).
- Bootstrap runs the Codex step (`bootstrap.py:1139`) before adopt (`:1146`), and adopt needs Claude Code on, so a Codex-only machine never gets the choice.
- No `--clean` flag exists.

So the real gaps: the Codex table, Codex-only machines, an explicit non-interactive consent, and silent removal of tuned Claude variants.

## 2. Decision (v1: Serena only)

No new module or bootstrap step. `inventory` gets a `use_loadout` mode in ADR 0041's style: only in that mode an own Codex Serena becomes `migrate`. Bootstrap runs a Serena-only adopt pass after the plugin install and before `codex_step`, for every agent that is on (also Codex-only). Nothing is shown when there is no duplicate.

### Question (terminal)

```
Serena: yours (Codex config.toml "serena"; --context ide, env) runs next to loadout's.
Use loadout's and remove yours? Backed up; `loadout restore` brings it back.
[y] use loadout's (recommended)  [n] keep mine, don't ask again  Enter: decide later
```

Enter stores nothing (ADR 0016); `n` is a remembered leave.

### Flags

- `bootstrap --use-loadout` and `adopt --apply --use-loadout`: a durable yes, but only for **plain duplicates**. Opposite: `--keep-own` (not remembered). Both together is an error. Name chosen over `--clean`: it says what it does and does not promise a clean machine.
- Plain duplicate, fail-closed: command, args and env equal what loadout writes. Any unknown key, env entry, extra arg, other `--context` or custom path counts as own settings: it is named with the exact command (`loadout adopt --apply --own serena=remove`) and removed only on a typed `y`.
- A remembered leave beats the flag (printed "kept (you chose leave)").
- `--yes` alone changes nothing new. Help and ADR state the flag's real delta over `--yes`: the Codex table, Codex-only machines, non-interactive intent.

### Scope

Claude user scope (`~/.claude.json`, `~/.claude/.mcp.json`) and the Codex `config.toml` table (any name, recognised by `codex.is_serena`). Project-scope servers, repo `.mcp.json` and `hooks.json` entries are only named; the wording never says "clean" or "done". Not-asked runs add a "Still to do" line and the fix to check's "two Serena servers" row.

### Agents and sides

- An agent off in `targets.json`: nothing read or asked (Code Review Rules, P1).
- Codex side = the side bootstrap acts on (`--codex-side windows` leaves the WSL side untouched; the Codex home path must equal that side).
- VS Code extension without the Codex CLI: `codex.remove_server` uses the extension's `codex`; unsupported cases are named, not removed.

### Musts (P1 if skipped)

1. **Replacement works before removal.** loadout writes its Codex `SERENA` table without checking that `serena` exists (`codex.py:362-363`, `desired_tables` `:569-571`). Require `runner.have("serena")` (or the installed uvx tool) first; otherwise `--no-install` would swap a working Serena for a broken one.
2. **Claude guard.** `migrate` never checks that loadout's plugin is installed; `--no-plugins` or a failed clone removes the own Serena with nothing in its place. Require the `_claude_plugin_on` pattern (`cbm_installer.py:136-145`: enabled in settings and present in `installed_plugins.json`). Open: a fresh install may have an empty `installed_plugins.json` at that moment (ADR 0015); then keep and print one line.
3. **Rollback.** The pass runs before `codex_step`; if loadout's table is not written in the same run, re-insert only the removed table text (exact text, atomic). If that fails, report it and print the backup path. Never end a run without a Serena silently. Test both paths.
4. **Plain duplicate fail-closed**, as defined above.

### Backup and restore

Reuse `adopt._apply_mcp`: Claude records the `add-json` undo and runs `claude mcp remove -s user`; Codex saves `config.toml` and runs `codex.remove_server`. `restore --show` lists "run: claude mcp add-json … (masked)" or "put back ~/.codex/config.toml". A restored Codex table is not taken for loadout's (exact-text record). Output is redacted. Restore after a later `loadout update` behaves as today.

P2: a symlinked `config.toml`, `.claude.json` or `hooks.json` is skipped with a line (`write_atomic` keeps links, but `codex mcp remove` writes itself and restore's `copy2` writes through; untested).

### Separate change: ADR 0045

Claude Serena with own settings: `migrate` → `keep` on `--yes` (typed `y` still removes), as ADR 0041 did for codebase-memory. Amends ADR 0016 and 0028; separate commit or PR; changes `tests/test_inventory.py:28`.

## 3. Tests (`fake_home`, `fake_runner`)

- Codex own Serena + flag: saved, removed, loadout's table written in the same run.
- Plain vs env-only vs extra-arg vs other-context variants; own-settings ones need a typed `y`.
- `--yes` alone: Codex untouched. Claude tuned variant kept on `--yes` (ADR 0045), removed on typed `y`.
- Codex off / Claude off: no reads, no calls.
- Codex-only machine + flag runs the pass.
- Plugin missing / `--no-plugins`: kept + one line. `serena` missing: Codex table kept + one line.
- `y` / `n` (leave remembered, check row silent) / Enter (nothing stored); leave beats flag; `--keep-own` not stored; both flags → error.
- Rollback when `codex_step` fails, and when the rollback itself fails.
- Symlinked config skipped; extension-only and `--codex-side windows`.
- Redaction in output and `restore --show`; restore round-trip including the exact-text record.
- No duplicate → no output. User `hooks.json` untouched.

## 4. Decided and open

Decided by the user (2026-10-31):
- Enter = decide later (ADR 0016), as everywhere else in adopt; only a typed `y` replaces.
- ADR 0045 goes in: `--yes` keeps a Claude Code Serena with its own settings; only exact copies of loadout's go.

Open:
3. Symlink behaviour of `save_copy` and `codex mcp remove`: unverified.
4. Smaller alternative (critic, conceded): only an adopt choice, no bootstrap question. Rejected because the Codex-only gap needs bootstrap.

## 5. Pre-existing finding (separate from this feature)

`Backup.record_command` stores the undo `claude mcp add-json … <cfg>` verbatim, so `env`/`headers` secrets sit in plaintext in `manifest.json` (`backup.py:114-118`, `adopt.py:309-311`); only the folder mode protects it, restore passes them in argv, and `restore --show` masks by `redact()` heuristics. AGENTS.md "Secrets" lists the backup manifest as P1. Not caused by this feature, but `--use-loadout` multiplies it. Needs its own fix (e.g. store the secret in `secrets.env` and the undo with `${VAR}`, or keep the config in a 0600 side file referenced from the manifest).
