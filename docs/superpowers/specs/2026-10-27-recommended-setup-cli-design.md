# The recommended setup in the CLI — design

## Intent

The recommended path for each platform, agent choice and surface exists only in the docs: `docs/reference/setup-matrix.md`, linked from `docs/how-to/setups.md#recommended-setups`. Someone installing loadout for the first time does not know which cell they are in or which flags that cell needs. The maintainer's friend will be the next such person. Someone who set loadout up months ago does not know whether their machine still matches a recommended cell. The CLI already knows most of the facts it needs: the platform (`wsl.detect`, `os_key`), the agents (`targets`), the CLIs on PATH (`runner.have`) and VS Code's extensions per window type (`vscode.extensions`). But it never says "this is your cell, and this is what is recommended for it". (Backlog item 2026-10-19, "CLI side of 'one recommended way per platform and usage'".)

## Goals

- **`loadout check`: one new first row, `Setup`.** It names the cell loadout sees on this machine:
  - the platform: Linux, macOS, WSL 2, or native Windows (experimental);
  - the agents that are on (`targets.json`);
  - the surfaces it found per agent: the CLI on PATH, and VS Code's extension with its window type (local, Remote-WSL, Windows window).

  It also links the matching section of the setup matrix. The row is informational and always `ok`. It does not repeat the warnings that existing rows already give: the Windows window in WSL, `CODEX_HOME` pointing into Windows, the Codex side. The health count gains this one row.
- **`bootstrap`: a short "This machine" block.** It comes after the agent choice and the Codex side are settled (the WSL gate) and before `Prerequisites`, so before anything installs. It shows:
  - the same detected cell;
  - the recommended flags for it (the steps after bootstrap stay in the existing end list; see "Decided after the builder check").

  When the flags or answers of this run differ from the recommendation, it names each difference in one line. The list of differences is under "Decided after the builder check". Then bootstrap carries on with the person's choice (user's choice: "just say it").
- **Same behaviour on every platform.** This includes `bootstrap.ps1` on native Windows, which marks the cell experimental.
- **One source.** The recommendations live in one small table in code (cell → flags and steps after), and a test pins it against `docs/reference/setup-matrix.md`, so the docs and the CLI cannot drift apart silently. The matrix stays the human home of the facts (one home per fact: the code mirrors it, guarded by the test).
- **Docs:**
  - the `Setup` row in `docs/how-to/troubleshooting.md` (every check row is covered there) and in the CLI reference for `loadout check`;
  - one sentence in `docs/how-to/setups.md#recommended-setups` saying that `loadout check` and bootstrap name your cell;
  - the getting-started tutorial's bootstrap output, if it shows the output.

## Non-goals

- No new command (no `loadout recommend`). The user picked bootstrap and check.
- No new question in bootstrap, and no "take the recommended flags? [Y/n]" (user's choice).
- No change to what bootstrap installs or sets up. Only text is added.
- No `loadout update` change.
- No detection of intent. loadout reports what it sees and what is recommended for that. It does not guess what the person meant.

## Anti-goals

- A run without a terminal (an agent's shell, `--yes`) that waits on input, or a run whose exit code changes because of the new text.
- A `Setup` row that warns or fails. Then a healthy machine would look unhealthy, and the existing specific rows would be said twice.
- A recommendation that contradicts the setup matrix, or the matrix changes and the CLI keeps the old text.
- A long block. The bootstrap block and the check row should read in a few seconds: a handful of lines in calm mode, more only with `--verbose` if needed.
- Reading or changing anything of an agent that is turned off, beyond what check already reads (ADR 0030 and AGENTS.md "User files").

## Constraints

- Kit conventions apply (AGENTS.md): standard-library Python in `cli/loadout/`, tests with `fake_home`/`fake_runner`, no real `claude`/`codex`, Conventional Commits, no AI attribution.
- Detection reuses the existing functions (`wsl.detect`, `wsl.codex_side`/`check._wsl_codex_side`, `targets`, `runner.have`, `vscode.extensions`, `vscode.bundled_claude`). It adds no new probes of the machine, and no external commands beyond those check already runs.
- The check row goes first in `check.run_checks`. Both `format_results` and `format_summary` (bootstrap's calm health line) must stay correct.
- In WSL with Codex on the Windows side (`--codex-side windows`, or `run_checks(codex_windows=True)`), the cell is the matrix's "Codex on Windows, or on both sides" table, not the plain WSL one.

## Decided after the builder check

- **When (user):** the block shows on every `bootstrap` run, not only the first. The heading "First `bootstrap`" above means the bootstrap flow, whichever run it is.
- **What a difference is (my call):**
  - The matrix never recommends which agents to pick; it is keyed by the agent choice. So the recommendation follows from the agents chosen in this run, the platform and the surfaces found for those agents.
  - Reported differences, each one line:
    - (a) No `--install` while a tool the cell needs is missing.
    - (b) Codex chosen in WSL, Codex's VS Code extension on Windows seen (only when Codex is on), and no `--vscode-wsl`.
    - (c) A Codex CLI on PATH while Codex is not chosen. This reads PATH only, the same signal bootstrap's own default uses; it reads no file of the agent that is off.
    - (d) `--without-codex-cli` given while a Codex CLI is on PATH.
  - The example in Goals ("CLI or extension present") is replaced by (c). Nothing reads VS Code's extensions for an agent that is off (`vscode.extensions(on)` stays as is).
- **Fresh machine, no surface found (my call):** the cell is the "CLI only" row for the chosen agents, and the block adds one line: "using VS Code? see <matrix section>". The "+ CLI (optional)" row is chosen only when both the extension and that agent's CLI are found. Bootstrap's existing Codex CLI question stays the place where that choice is made.
- **Steps after bootstrap (my call):** the block shows the cell and the recommended flags only. The steps after bootstrap stay in the existing end list ("Still to do", `steps.print_pending`), which shows only what is still open. Nothing appears twice, and the block stays short. Goals' "steps the matrix lists after bootstrap" is dropped from the block. The code table holds the flags per cell, and the test pins those against the matrix.
- **WSL with Codex on Windows (my call):** the row comes from `wsl.codex_side()` (`windows` → "On Windows only", `both` → "On both sides"). In bootstrap the gate's outcome overrides it (`WINDOWS_WAY in gate` → windows), as `run_checks(codex_windows=True)` already does. With Codex off, the plain WSL table applies and nothing about a Windows Codex is read.
- **Native Windows (my call):** the cell uses the Linux and macOS flags, marked "experimental". It links `setup-matrix.md#native-windows-experimental` and says nothing about WSL. `bootstrap.ps1` needs no change: it hands off to `bin/loadout bootstrap`, so the Python block runs there too.

## Left to the builder

- The exact wording of the row and the block, in the kit's plain style.
- How a cell is keyed in code, and how the test reads the matrix: the section anchors and the flag cells per surface.
- How "surface" is shown when several extensions or window types are present.
- Whether `--verbose` shows more in either place.
