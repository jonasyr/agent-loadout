# 0046. Release channels: stable follows tested releases, dev follows main

- Status: Accepted
- Date: 2026-11-03
- Source: [Design: release channels](../superpowers/specs/2026-11-03-release-channels-design.md)
- Amends:
  - [ADR 0024](0024-codex-parity-update-model.md): on stable the kit's plugin marketplaces are pinned to the release and move only with `loadout update`;
  - [ADR 0035](0035-loadout-update-brings-a-machine-current.md): on stable `loadout update` moves the kit to a release instead of pulling `main`.

## Context

Every machine pulled the kit's `main` once a day and re-applied the setup without asking, and Claude Code updated the kit's marketplace by itself. One bad commit on `main` (a bug, an agent commit that slipped through review, a stolen GitHub login) reached every machine within a day. With a friend's install next, that stops being acceptable as the default.

## Decision

- **Two channels per machine.** `dev` follows `main` as before. `stable` follows release tags `vX.Y.Z`. A new install is stable; a machine with no channel setting stays dev and is told once about `loadout channel stable`. The setting is `channel.json` in the machine-local state folder, not in the personal layer: a synced value would move another machine's code without its yes.
- **A release is offered after 3 days.** The daily maintenance run lists the tags on `origin` (`git ls-remote --tags`, no GitHub API) on both channels and records, per tag, its commit and the time this machine first saw it (`releases.json`). A tag is offered when it is newer than the current one, not withdrawn, unchanged and first seen 3 days ago or listed as urgent. Only names `vX.Y.Z` at or above the floor (`0.2.0`, the first release that knows channels) count.
- **Notify, then apply.** Stable prints one notice per available version and changes nothing until the person runs `loadout update`. The kit is never pulled on stable. The personal layer is the person's own repo and keeps its daily pull on both channels.
- **Plugins follow the release.** On stable the `agent-loadout` marketplace entry in Claude Code gets `ref: vX.Y.Z` and `autoUpdate: false`, and the Codex marketplace is added as `owner/repo@<sha>`, the release's 40-hex commit (the one the kit checkout is on). Both are written by loadout's own merge and move only with `update`. dev has no ref and keeps `autoUpdate: true`. Why the commit and the switched-off auto-update: the plugin's hooks run every session, and a tag name follows the remote. Codex takes a 40-hex ref as the commit and never asks the remote for it; Claude Code has no commit pin for a marketplace source and with `autoUpdate` would install the latest commit of the ref, so a force-moved tag would bring an unverified plugin while the kit stays on the verified commit. `loadout update` refreshes the kit's Claude Code marketplace only while the release's tag is unchanged; once the daily check saw it moved, it holds the marketplace and its plugins and says so.
- **Release status lives on `main`.** `release-status.json` lists urgent versions and withdrawn ones (with a reason and an optional `use` target). Tags are never deleted or moved; a withdrawal is a line in that file.
- **A moved tag is never offered.** If a known tag later points at another commit, loadout queues one alarm and `check` warns.
- **`loadout release X.Y.Z`** (maintainer only) refuses unless it runs on a clean `main` equal to `origin/main`, the version is newer than every tag and at least the floor, `gh` is signed in and CI for `HEAD` succeeded. It touches only `pyproject.toml`, `CHANGELOG.md` and `release-status.json`, then pushes the commit and the tag in one atomic push and creates the GitHub Release with `bootstrap.sh` and `bootstrap.ps1` attached. `loadout release withdraw` edits `release-status.json` only.
- **Moves are undoable.** `update` and `channel` refuse on local edits or local commits in the kit checkout, record `git checkout --detach <old sha>` in the backup before moving, and never use `checkout -f`, stash or reset. One move is one restore point.
- **First install runs released code.** The install command fetches the scripts of the newest GitHub Release. The script checks out the newest annotated tag that is at least 3 days old by its tagger date, and stops (never falls back to `main`) when there is none. `--channel dev` installs `main`.

## Threat model and its limits

- **Protected:** a bad or malicious commit on `main` (stable never runs it); a bad release noticed within 3 days (withdrawn before stable sees it); a tag backdated to skip the wait (the wait counts from when this machine first saw the tag).
- **Not protected:** someone with push access who cuts a release and waits 3 days unnoticed; a machine whose clock is far ahead; a fresh release's install script, which is served at once; the first-install check, which trusts the tag's own date. `--urgent` only shortens the wait for the notice; the person still applies the release.

## Alternatives considered

- **Keep daily pulls and add a pause switch:** the default stays unsafe.
- **Auto-apply releases on stable:** a stolen login then still reaches machines, only later.
- **GitHub Releases API for discovery:** rate limits and an account; `ls-remote` needs neither.
- **Pin by commit sha in a file on `main`:** the file is the thing an attacker would change.
- **Tag signatures:** wanted, left out for now; a verify step before the checkout fits the design.
- **A separate mirror repo:** more to run, no gain here.

## Consequences

- Fixes reach stable machines at the earliest 3 days after the release, or at once with `--urgent`, and only after `loadout update`.
- Until the first channels release (0.2.0) has been out 3 days, a stable install stops and says so.
- Releasing becomes a deliberate step with a changelog.
- Third-party marketplaces (claude-plugins-official and others) are not pinned.

## In the code

- `cli/loadout/channels.py` (the setting, tags, eligibility, moves), `cli/loadout/release.py` (`loadout release`), `cli/loadout/update.py` (`update` and `channel` on stable), `cli/loadout/maintenance.py` (the daily check), `cli/loadout/check.py` (the Channel row), `bootstrap.sh` and `bootstrap.ps1` (the first install)
