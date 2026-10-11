# Calm CLI output and a newcomer-friendly README demo

Date: 2026-10-11. Status: approved in conversation (sections 1 and 2), awaiting spec review.

## Why

The first demo (PR #8) works but is fast, and a reader who has never heard of loadout cannot tell what the wall of
text means. The cause is mostly the CLI itself, not the recording:

- `adopt --apply` prints the whole plan, then asks all questions on one or two lines (answers run together).
- Reasons repeat themselves ("Provided by loadout; this copy duplicates it. loadout provides the Serena MCP server;
  a user-level copy duplicates it.").
- Group names are jargon (MIGRATE, SCOPE-DOWN); KEEP lists 25 items nobody needs to read.
- `check` prints 24 `[ok]` lines and no summary; bootstrap prints every detail of every step.
- Nothing shows the payoff: Claude Code starting with the kit loaded.

**Goal:** someone landing on the README understands "what loadout is, what it did, what I get" in under a minute,
without pausing the GIF. The CLI changes must help real users, not only the recording.

**Non-goals:** a rich TUI (spinners, boxes, full-screen); new features; changing what any command *does*.

## Part 1: calm CLI output

Principle: one short status line per step; details only for problems, decisions, or `--verbose`.
Standard library only, works the same on Linux, macOS, Windows and WSL, and degrades to plain text without a terminal
(no colour or symbols that break when piped; `✓` falls back to `ok` when stdout cannot encode it).

### bootstrap

- Opens with one sentence: `loadout sets up Claude Code with a reviewed kit of plugins, rules and tools.`
- Each step (WSL, Prerequisites, Personal layer, Links, Settings, Marketplaces and plugins, Secrets, PATH) prints one
  line: a mark, the step name padded to a column, and a short result (`12 tools found, 0 to install`,
  `linked, settings merged`, `14 kit plugins installed`).
- A step's detail lines are printed under its status line only when the step warned or failed, or with
  `--verbose` (new flag on `bootstrap`). Installer output on failure keeps today's `_tail` and hints.
- Questions (personal layer, "Customize preferences…", adopt) are still asked where they are today, each on its own line.
- The run ends with one block instead of today's check dump:
  ```
  ✓ Applied 7 changes. Undo any time: loadout restore
  ✓ Health check       24 of 24 OK
  Next: run `claude`. The kit loads automatically.
  ```
  With problems, the health-check line says `22 of 24 OK` and the problems follow (same text as `check`).
  "Still to do" items and "Open a new terminal" stay, below the summary.

### adopt

- Plain-language group headings (the internal group keys stay unchanged):

  | Key | Heading |
  |---|---|
  | remove | Remove: superseded by something better |
  | migrate | Already provided by loadout |
  | scope-down | Only useful in some projects |
  | own | Your own tools: loadout doesn't know these |
  | keep | (not listed; a count in the header line) |

- Header line: `Your existing setup: 7 suggestions (25 other items are fine)`.
- One line per item: `• <name> <kind>  → <short reason>`. Short reasons come from a new optional catalog field
  `short` (one line, max ~60 characters); the long `reason` stays for `--verbose` and the docs. Missing `short`
  falls back to the first sentence of `reason`. Duplicate wording between the generic group text and the item reason
  is removed.
- `--verbose` prints today's full detail (command line, long reason, replacement, notes, the KEEP list).
- `adopt --apply` no longer prints the plan first: each group is shown right before its own question, every answer
  ends the line, and the final `Apply N change(s)? [y/N]` confirmation stays (ADR 0012).
- Plaintext secrets: one line naming where the token is and what will happen; values stay hidden.
- After applying: one `✓` line per change group instead of one line per command; failures are listed in full.
  The backup line becomes `Undo any time: loadout restore` (the path is shown with `--verbose` and in `restore --list`).

### check

- Default: `Health check: 24 of 24 OK`, then only the warnings and failures in today's format
  (`[FAIL] name: detail` / `fix: …`), so CI's `grep -F '[FAIL]'` keeps working.
- `--verbose` prints today's full list. Exit codes are unchanged.

### Consumers checked

Only CI parses this output (`grep -F '[FAIL]'` on `loadout check`); failures remain printed with `[FAIL]`.
No plugin skill or hook parses `check` or `adopt` output. Docs that quote the output (`docs/reference/cli.md`,
`docs/tutorials/getting-started.md`, `docs/how-to/your-own-tools.md`, troubleshooting) are updated to match.

## Part 2: the demo

### Storyline (about 60 s)

1. Title card: `loadout` / `A reviewed Claude Code setup in one command`.
2. Card `① An existing Claude Code setup`: `claude mcp list` and `ls ~/.claude/plugins` show the messy start (~5 s).
3. Card `② One command`: the README one-liner, typed exactly as published. Calm bootstrap output; adopt questions
   answered at a readable pace (~1.5 s per answer, 4–5 s on each summary).
4. Card `③ Done. Undo any time.`: the final summary stays on screen.
5. Card `④ Claude Code starts with the kit`: the real Claude Code clip.

### Running the one-liner offline

- `demo/bin/curl`: a stub that answers only `https://raw.githubusercontent.com/jonasyr/agent-loadout/main/bootstrap.sh`
  by printing the kit's own `bootstrap.sh`; any other URL exits non-zero. The clone comes from `/kit` through the
  existing `LOADOUT_REPO_URL` hook, set in the hidden setup.
- The `uv` stub answers `python find` with the container's `python3`, so `bootstrap.sh` runs unchanged.
- Both stubs, like `demo/bin/claude`, refuse to run without the sandbox marker `~/.loadout-demo`.
- The sandbox no longer runs bootstrap during setup (the recording does); it only builds the messy existing setup.

### Real Claude Code clip

- `demo/claude.tape` plus `demo/record-claude.sh`, run by the maintainer on their own machine (needs `vhs` on the
  host). Agents never run it.
- It creates a throwaway folder, starts `claude`, shows the welcome screen, runs `/mcp` (servers connected), then
  `/exit`. No prompt goes to the model.
- Output: `demo/claude-clip.mp4`, committed after the maintainer reviewed it (it shows their paths and plugins;
  crop if it shows the account line).
- `demo/render.sh` records the sandbox part, then joins it with the clip using ffmpeg (already in the VHS image)
  into `docs/assets/demo.gif`, with the same size, theme and font. If the clip is missing, render.sh produces the
  sandbox part alone and says so.

### Look: modern, professional, minimal

Not VHS defaults:

- A custom theme defined in the tape (JSON): near-black background, soft off-white text, one accent colour
  (loadout's violet) used for prompts and marks, muted grey for secondary text; green/amber/red only for status.
- Font: JetBrains Mono (installed in `demo/Containerfile` via `fonts-jetbrains-mono`), FontSize 16, LineHeight 1.3.
- Window: `WindowBar Rings`, `BorderRadius 10`, `Margin 36` with a solid `MarginFill`
  slightly lighter than the terminal background, `Padding 28`.
- Size about 1200×800; Framerate 20; target GIF size under 5 MB (lower framerate before speeding up).
- Title cards: a cleared screen with the text centred, the title in the accent colour and a muted subtitle,
  printed by a hidden helper (`demo/card.sh "① …" "subtitle"`), shown ~2.5 s.
- A minimal prompt: `~ ❯` in the accent colour.
- The README embeds the GIF with a one-line caption under it.

### Tests

- Existing demo tests stay (tape uses only the sandbox, offline render, sandbox refuses an existing home,
  claude stub refuses outside the sandbox and edits the sandbox).
- New: curl and uv stubs refuse to run without the marker; curl stub refuses any URL but the one; the tape types the
  README one-liner verbatim (compared with README.md); `record-claude.sh` is never called by render.sh or tests.
- CLI: tests for the new bootstrap summary lines, `--verbose` on bootstrap/adopt/check, adopt headings and short
  reasons, no plan reprint in `--apply`, one answer per line, `check` summary and failures with `[FAIL]`,
  `✓` fallback when stdout cannot encode it, and the catalog `short` field (validation: one line, length limit).

## Documentation

- `docs/reference/cli.md`: `--verbose` flags and the new output shape.
- `docs/reference/catalog-format.md`: the `short` field.
- Tutorials and how-tos that quote output: updated.
- CONTRIBUTING "The README demo": recording the Claude Code clip, rendering, the look.
