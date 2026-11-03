# Design: use loadout's Serena ("start clean")

- Status: implemented on branch feat/start-clean (2026-11-02). The plan is [2026-11-02-start-clean](../plans/2026-11-02-start-clean.md); the user-facing description is [Your own Serena](../../reference/cli.md#your-own-serena) and the decision is [ADR 0045](../../adr/0045-a-tuned-serena-is-kept.md).
- Source: backlog "IDEA (2026-10-29)" in `.superpowers/handoff/2026-10-13-hardening-backlog.md`; produced by an agent-team test (mapper, designer, critic). Working notes: `.superpowers/handoff/team/{mapper,designer,critic}.md`.

## 1. Premise correction

The backlog assumed an existing Serena is always kept. That holds for Codex only.

- Claude Code: an own Serena in `~/.claude.json` matches catalog `mcp-serena` (`core`), so `classify` makes it `migrate`. `migrate` is in `adopt.DEFAULT_ALL`, so Enter and `bootstrap --yes` already remove it, backed up with an `add-json` undo. Unlike codebase-memory (ADR 0041) there was no exemption for a Serena with its own settings, so a tuned fork or env variant went silently on `--yes`.
- Codex: an own Serena table was never an adopt item; loadout wrote no table of its own and printed `codex.SERENA_KEPT` (ADR 0028).
- Bootstrap ran the Codex step before adopt, and adopt needs Claude Code on, so a Codex-only machine never got the choice.
- No `--clean` flag existed.

So the real gaps were: the Codex table, Codex-only machines, an explicit non-interactive consent, and silent removal of tuned Claude variants.

## 2. Decision (v1: Serena only)

No new module. `inventory` gets a `use_loadout` mode in ADR 0041's style: only in that mode an own Codex Serena becomes `migrate`. Bootstrap runs a Serena-only adopt pass (`adopt.serena_pass`) after the plugin install and before `codex_step`, for every agent that is on (also Codex-only). Nothing is shown when there is no duplicate.

### Question (terminal and Codex)

```
Serena: yours (Codex config.toml "NAME") runs next to loadout's.
Use loadout's and remove yours? Backed up; `loadout restore` brings it back.
[y] use loadout's (recommended)  [n] keep mine, don't ask again  Enter: decide later
```

Enter stores nothing (ADR 0016); `n` is a remembered leave, and it beats `--use-loadout`.

### Flags

- `bootstrap --use-loadout` and `adopt --apply --use-loadout`: a durable yes, but only for **plain duplicates**. Opposite: `--keep-own` (not remembered). Both together is an error (exit 2). Name chosen over `--clean`: it says what it does and does not promise a clean machine.
- Plain duplicate, fail-closed: command, args and env equal what loadout writes. Any unknown key, env entry, extra arg, other `--context` or custom path counts as own settings: it is kept, and the line names the exact command (`loadout adopt --apply --own NAME=remove`).
- A remembered leave beats the flag (printed "kept (you chose leave)").
- `--yes` alone changes nothing new for Codex. The flag's real delta over `--yes`: the Codex table, Codex-only machines, an explicit non-interactive choice.

### Scope

Claude user scope (`~/.claude.json`, `~/.claude/.mcp.json`) and the Codex `config.toml` table (any name, recognised by `codex.is_serena`). Project-scope servers, repo `.mcp.json` and `hooks.json` entries are only named. Runs that ask nothing add a "Still to do" line, and check's "two Serena servers" row names the fix.

### Agents and sides

- An agent off in `targets.json`: nothing read or asked (Code Review Rules, P1).
- Codex side = the side bootstrap acts on (`--codex-side windows` leaves the WSL side untouched; the Codex home path must equal that side).
- VS Code extension without the Codex CLI: `codex.remove_server` uses the extension's `codex`.

### Musts (P1 if skipped)

1. **Replacement works before removal.** Codex's `SERENA` table is written without checking that `serena` exists, so the pass requires `runner.have("serena")` first; otherwise `--no-install` would swap a working Serena for a broken one.
2. **Claude guard.** `migrate` never checks that loadout's plugin is installed, so `--no-plugins` or a failed clone would remove the own Serena with nothing in its place. The pass keeps a Claude Code Serena unless `cbm_installer.claude_plugin_on()` says the plugin is enabled and installed, and prints one line.
3. **Rollback.** The pass runs before `codex_step`; if loadout's table is not in `config.toml` at the end of the run, the removed table text is put back (exact text, atomic). If that fails, the run prints the backup path and exits 1. Never end a run without a Serena silently.
4. **Plain duplicate fail-closed**, as defined above.

### Backup and restore

Reuse `adopt._apply_mcp`: Claude records the `add-json` undo and runs `claude mcp remove -s user`; Codex saves `config.toml` first and runs `codex.remove_server`. `restore --show` lists the undo. A Codex table written inline or with dotted keys cannot be put back exactly, so it is never removed automatically. A symlinked `config.toml` is skipped with a line.

### Separate change: ADR 0045

A Claude Code Serena with own settings: `migrate` becomes `keep`, so `--yes` no longer removes it; a typed `own NAME=remove` still does. As ADR 0041 did for codebase-memory. Amends ADR 0016 and 0028.

## 3. Tests (`fake_home`, `fake_runner`)

- Codex own Serena + flag: saved, removed, loadout's table written in the same run.
- Plain vs env-only vs extra-arg vs other-context variants; own-settings ones are kept.
- `--yes` alone: Codex untouched. Claude tuned variant kept on `--yes` (ADR 0045).
- Codex off / Claude off: no reads, no calls.
- Codex-only machine + flag runs the pass.
- Plugin missing / `--no-plugins`: kept + one line. `serena` missing: Codex table kept + one line.
- `y` / `n` (leave remembered) / Enter (nothing stored); leave beats flag; `--keep-own` not stored; both flags → error.
- Rollback when `codex_step` fails, and when the rollback itself fails.
- Symlinked config skipped; extension-only and `--codex-side windows`.
- Redaction in output and `restore --show`; restore round-trip including the exact-text record.
- No duplicate → no output. User `hooks.json` untouched.

## 4. Decided and open

Decided by the user (2026-10-31):
- Enter = decide later (ADR 0016), as everywhere else in adopt; only a typed `y` replaces.
- ADR 0045 goes in: `--yes` keeps a Claude Code Serena with its own settings; only exact copies of loadout's go.

Open:
1. Symlink behaviour of `codex mcp remove` and of the backup copy: not verified. The pass skips a symlinked `config.toml` with a line.
2. Smaller alternative (critic, conceded): only an adopt choice, no bootstrap question. Rejected because the Codex-only gap needs bootstrap.

## 5. Calls made while planning

The plan ([2026-11-02-start-clean](../plans/2026-11-02-start-clean.md)) made three calls the spec did not settle:

1. **One question per server.** Interactively the pass asks only about the **Codex** Serena. A plain Claude Code Serena stays with adopt's existing `migrate` group (Enter there removes it, as today). The pass acts on a Claude Code Serena only under `--use-loadout`. Reason: two questions about one server, with opposite Enter defaults, would contradict each other.
2. **Tuned means kept, not asked.** A Serena with its own settings is never removed by `--use-loadout`; it is kept with a reason that names `loadout adopt --apply --own NAME=remove` (the ADR 0041 pattern). The spec's "typed `y`" for tuned ones is that command.
3. **What counts as plain.** A plain duplicate has the command basename `serena` (or `serena.exe`), the argument **set** of loadout's for that agent, and no keys beyond `command`, `args`, `type`, `enabled`, `alwaysLoad`, `startup_timeout_sec` and `env` (`env` only when empty). Anything else is own settings (fail closed).
