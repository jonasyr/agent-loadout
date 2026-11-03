# Release channels (stable and dev)

Status: design, 2026-11-03. Decisions marked **(Jonas)** were made by the maintainer; **(call)** marks a choice made while writing this, open to change.

## Why

Today every machine runs `git pull --ff-only` on the kit's `main` once a day and re-applies config without asking (docs/reference/state-and-sync.md, "The daily sync"), and Claude Code updates the kit's plugin marketplace on its own (`autoUpdate: true`, ADR 0024). One bad commit on `main`, from a bug, an agent commit that slipped through review, or a stolen GitHub login, reaches every machine within a day. With loadout going to other people (a friend's install is next), that is no longer acceptable as the default.

Success: a person on stable only ever runs code that (a) was released on purpose by the maintainer, (b) was out for 3 days first, and (c) they applied themselves. The maintainer keeps today's fast loop on dev.

## Goals

1. Two channels per machine. **dev** follows `main` exactly as today. **stable** follows release tags `vX.Y.Z`. **(Jonas)**
2. New installs default to stable; the maintainer's machine runs dev. **(Jonas)** A machine with no channel setting (every existing install) stays dev and gets one notice about `loadout channel stable`. **(Jonas)**
3. Stable is notify-then-apply: a notice says a release is available; nothing changes until the person runs `loadout update`. **(Jonas)**
4. A release is offered to stable only when it is at least 3 days old. **(Jonas)**
5. The maintainer cuts a release with `loadout release X.Y.Z`, which refuses unless CI is green. **(Jonas)**
6. `--urgent` skips the 3-day wait; a release can be withdrawn. **(Jonas)**
7. The kit's Claude Code and Codex plugins are pinned to the same release on stable and move only with `loadout update`. **(Jonas)**
8. The personal layer keeps its daily pull on both channels: it is the person's own repo. **(Jonas)**

## Non-goals

- Tag signatures (`git verify-tag`). Later; the design leaves room (a verify step before checkout). **(Jonas)**
- Separate mirror repos; GitHub Releases pages; automated release PRs (release-please).
- Auto-apply on stable. Notify only.
- Pinning third-party marketplaces (claude-plugins-official, impeccable, …): unchanged.

## Anti-goals (a failure even if it works)

- Stable silently runs unreleased code anywhere: the kit checkout, the plugin, or the first install.
- A channel switch or update loses local edits or local commits in the kit checkout.
- A kit move that `loadout restore` cannot undo.
- A notice that repeats every session, or an update path that marks a healthy stable checkout as failed.

## Threat model and its limits

- Protected: a bad or malicious commit on `main` (stable never runs it); a bad release noticed within 3 days (withdrawn before stable sees it); a tag backdated to skip the wait (the wait is counted from when *this machine* first saw the tag, see below).
- Not protected: someone with push access who cuts a release and waits 3 days unnoticed; a machine whose clock is set far ahead; `--urgent` set by an attacker (it only shortens the notice, the person still applies it). Signatures address these later. The security doc says so plainly.

## Design

### Channel setting

- Machine-local file `~/.local/state/loadout/channel.json`: `{"channel": "stable" | "dev"}`. Not in the personal layer: the channel belongs to this machine's checkout, and a synced value would move another machine's code without its yes. **(call)**
- No file = dev, plus a one-time notice (`loadout now has release channels; run loadout channel stable to get only tested releases`), stamped so it shows once.
- `loadout channel` prints the channel and the current release or branch. `loadout channel stable|dev` switches (see below).

### Learning about releases (both channels record, only stable acts)

- Once a day, in the existing detached `loadout maintenance` run, on both channels: `git ls-remote --tags origin`, so a later dev → stable switch already has first-seen times. **(call)** Accept only names matching `^v\d+\.\d+\.\d+$` and at or above the **release floor** (the first release that knows channels, e.g. `0.2.0`, a constant in the code and the scripts); ignore the rest, including today's `v0.1.0`. **(Jonas)** No GitHub API (rate limits, no account needed). Offline or any git error: say nothing, record nothing, try next day.
- `releases.json` in the state folder keeps, per tag: the commit sha and the time this machine first saw it (`first_seen`, own clock). If a known tag later points at a different sha: never offer it, queue one alarm notice (`release vX.Y.Z was changed after release; not offered — tell the maintainer`), and a check row warns.
- Release status (urgent and withdrawn) lives in `release-status.json` on `main`, read without touching the working tree: `git fetch origin main` then `git show FETCH_HEAD:release-status.json`. Shape:
  ```json
  {"urgent": ["1.5.1"], "withdrawn": [{"version": "1.5.0", "reason": "breaks Codex on Windows", "use": "1.5.1"}]}
  ```
  A missing or unparsable file counts as empty. Tags are never deleted or moved (a fetched tag stays on clients; Go `retract` / cargo yank model).
- **Eligible release**: newer than the current one (semantic version compare, `versions.parse_version`), not withdrawn, sha unchanged, and `now - first_seen >= 3 days` or urgent. If `now < first_seen` (clock went back) it is not eligible yet.
- One notice per eligible version, never repeated: `loadout 1.5.0 is available (since 1.4.2: <up to 3 changelog lines>); run loadout update`. Changelog lines come from that tag's `CHANGELOG.md` section (`git fetch origin tag vX.Y.Z --no-tags`, then `git show vX.Y.Z:CHANGELOG.md`; fetching touches no files).
- On a withdrawn current release: one notice with the reason and `run loadout update` (to the `use` version, if eligible; urgent is implied for a withdrawal's `use` target) or `loadout restore` when no target exists.
- `LOADOUT_NO_AUTO_PULL=1` keeps meaning "no automatic pull of code". The release check pulls no code, so it still runs, like the weekly tool check. **(call)**

### `loadout update` on stable

1. If an eligible release exists: the plan shows `kit: v1.4.2 → v1.5.0` with its changelog lines, under the same yes rules `update` uses today.
2. Refuse (as a paused sync does today, with the files named) when the kit checkout has local edits that the checkout would overwrite, or local commits not contained in any release tag. Never `checkout -f`, never stash or reset.
3. Record the undo first: the backup manifest gets `["git", "-C", <kit root>, "checkout", "--detach", <old 40-hex sha>]`; `backup._allowed_run` accepts exactly that shape, only for the kit root and a 40-hex sha.
4. `git fetch origin tag vX.Y.Z --no-tags`, `git checkout --detach vX.Y.Z`. Recognise git's `would be overwritten by checkout:` refusal like the merge one.
5. Re-run in the new code (today's `LOADOUT_UPDATE_PULLED` / `runner.continue_in` path) and re-apply exactly as after a pull that brought commits, with backups.
6. Move the plugin pins (below), only for agents that are on.

Without an eligible release, `update` does everything else as today; a detached kit on a release tag is not listed as a failed pull.

### Plugin pins

- **Claude Code**: the `agent-loadout` entry in `extraKnownMarketplaces` gets `"ref": "vX.Y.Z"` on stable and no `ref` on dev, written through loadout's existing settings merge (never by hand). `autoUpdate: true` stays: on a tag it has nothing to move to. After the change: `claude plugin marketplace update agent-loadout`, then the plugin update ADR 0024 already runs. Every `claude plugin marketplace add` loadout runs for this marketplace passes `jonasyr/agent-loadout#vX.Y.Z` on stable (a source without the ref would mismatch the settings entry).
- **Codex**: `codex plugin marketplace add jonasyr/agent-loadout@vX.Y.Z` (rewrites the table with `ref`), then loadout's plugin reinstall. Every `marketplace add` loadout runs for this marketplace (codex.py `_readd` and the add paths, update.py) passes the ref on stable. `unchanged_routes` / `remote_head` check the pinned ref, not HEAD, and the record stores the ref.
- Pinning uses the source the kit was cloned from (`LOADOUT_REPO_URL`/fork-aware), not a hard-coded repo.
- With Claude Code off, nothing touches `~/.claude`; with Codex off, nothing touches `~/.codex` (ADR 0030 rules).

### Bug fix that ships first (separate PR)

`codex._table_blockers` (`cli/loadout/codex.py:1596`) reads `ref_name`; Codex writes `ref`. A user's pinned marketplace is therefore re-added without its ref after a 30-second upgrade timeout, silently moving it to the default branch (P1 by the user-files rule; `loadout restore` can undo it). Fix: read `ref`, keep refusing the re-add (or pass `@ref`), fix `tests/test_codex_marketplace_readd.py:176-180`. Also correct ADR 0024's "Codex has no marketplace auto-update" (Codex 0.166 auto-upgrades marketplaces in the background).

### Switching channels

- **dev → stable**: refuse when the kit has local edits or commits not on `origin/main`, naming them. Otherwise pick the newest eligible release (when none has been seen for 3 days yet: the newest at or above the floor whose tagger date is 3 days old, the same one-time trust as a first install; when there is none at all, refuse with `no release is ready yet`), then steps 3–6 of update (undo recorded, checkout, re-run, re-apply, pins), after a plan and yes.
- **stable → dev**: `git switch main` (create it tracking `origin/main` if missing), `git pull --ff-only`, re-apply, remove the pins; undo recorded the same way. Refuse on local edits and on local commits not reachable from `origin/main`, naming them. **(call)**
- The setting is written only after the move succeeded.
- **Restore**: an update or a switch is one restore point: the kit checkout (the recorded `checkout --detach <old sha>`; restoring a stable → dev switch puts the old release back and leaves the created `main` branch in place, it is harmless), `channel.json` (saved copy), the Claude Code settings and the Codex `config.toml` (the existing backups, which hold the pins). **(call)**

### First install

- The install command points at the newest GitHub Release's attached scripts, not at `main`: `curl -fsSL https://github.com/jonasyr/agent-loadout/releases/latest/download/bootstrap.sh | bash` (and the `.ps1` twin). So the script itself is released code. **(Jonas)** It is not soaked: a fresh release's script is served at once; the code it then checks out is chosen by the rule below. Install docs (README, getting-started) change accordingly; `--channel dev` documents the main-branch way for the maintainer.
- `bootstrap.sh` / `bootstrap.ps1`: after the clone, unless `LOADOUT_REF` is set (tests and forks), check out the newest annotated `vX.Y.Z` tag at or above the floor whose tagger date is at least 3 days old. When none exists (before the first channels release has been out 3 days): say so and stop, suggesting to wait or to install dev (`--channel dev`). Never fall back to `main` on stable. This is the one step that trusts tag dates, done in shell before any loadout Python runs.
- `loadout bootstrap` (now running the release's code) seeds `releases.json` with every current tag as first seen now, writes `channel.json` = stable unless `--channel dev`, checks `release-status.json`, and if the checked-out release is withdrawn moves to its `use` target the same way update does.

### `loadout release` (maintainer only)

- `loadout release X.Y.Z [--urgent]`. Refuses unless: run from the kit checkout on `main`, clean, equal to `origin/main`; `X.Y.Z` is greater than the newest tag; `gh` is present and signed in; the newest CI run of `ci.yml` for HEAD concluded `success` (`gh run list --commit <sha> --workflow ci.yml --json conclusion` as an argument list).
- Then shows a plan and asks yes: set `pyproject.toml` `version`, prepend a `CHANGELOG.md` section built from Conventional Commit subjects since the last tag (feat, fix, and breaking changes; the maintainer can edit before confirming via `--edit`), with `--urgent` add the version to `release-status.json`, commit `chore(release): vX.Y.Z`, create an annotated tag, push the commit and the tag straight to `main`, then `gh release create vX.Y.Z` with the changelog section as notes and `bootstrap.sh` / `bootstrap.ps1` attached. **(Jonas)** The release commit may touch only `pyproject.toml`, `CHANGELOG.md` and `release-status.json`; the command refuses anything else, and the CI result of its parent stands for it.
- The first channels release must be the floor version; `loadout release` refuses a version below it.
- `loadout release withdraw X.Y.Z --reason TEXT [--use A.B.C]`: refuses if `--use` names no existing tag; edits `release-status.json`, commits `chore(release): withdraw vX.Y.Z`, pushes after a yes. Guidance in the docs: release the fix first, then withdraw (cargo's order).
- The plugins' `plugin.json` files get no `version` field: Claude Code then versions by commit sha, so every tag is a new version with nothing to bump. **(call)**

### Check, version, docs

- `loadout check`: a Channel row (`stable, v1.5.0` / `dev, main`); warns on an available release (fix: `loadout update`), on running a withdrawn release, and on a changed tag.
- `loadout --version`: `loadout 1.5.0 (stable, v1.5.0)` or `loadout 1.5.0+abc1234 (dev)`.
- Docs: new ADR 0046 (release channels); state-and-sync "The daily sync" (stable path); cli.md (`channel`, `release`, `--channel`, env vars); personal-layer machine-local state (`channel.json`, `releases.json`); security-and-trust trust boundary (what stable protects and what not); README and getting-started install text; CONTRIBUTING (how to release); ADR 0024 correction.

## Constraints

- Standard library only; every git/gh/claude/codex call through `runner.run` with argument lists; tag names validated against the regex before any use or print.
- Tests with `fake_home` and `fake_runner` only (git and gh answers faked).
- Windows (PowerShell bootstrap, Git Bash), WSL with a Windows-side Codex, Codex-only machines and the VS Code Codex extension without the CLI must all work; extension mode moves the Codex pin with the extension's codex.

## Left to the builder

- Exact notice and check wording (house style: short, plain, one action).
- File split (likely a new `cli/loadout/channels.py`, `release.py`), plan task order.
- The changelog generator's grouping details.
