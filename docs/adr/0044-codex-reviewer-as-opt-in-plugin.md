# 0044. codex-reviewer as an opt-in plugin

- Status: Accepted
- Date: 2026-10-27
- Source: [Design: codex-reviewer as an opt-in plugin](../superpowers/specs/2026-10-27-codex-reviewer-plugin-design.md)

## Context

Codex's GitHub review ("@codex review") runs out of quota now and then. This repo covered the gap with a Claude Code agent in `.claude/agents/`: it reviews the branch diff with Codex's open-source review rubric and returns the same JSON findings. Every loadout user who relies on Codex's review meets the same quota limit, so the agent should ship with the kit.

Three things made that more than a file copy. The marketplace had one plugin, and code assumed so. Codex adds the whole `agent-loadout` marketplace, and loadout routes every enabled plugin into Codex. And an agent description costs context in every session, also in sessions that never review.

## Decision

- **A second plugin in the marketplace.** `plugins/codex-reviewer/` carries one agent. The marketplace entry comes second and has no `version`, like the first. The marketplace is the existing GitHub one, so no new marketplace is needed.
- **Off by default.** The catalog entry `addon-codex-reviewer` has an `offer` key, so `loadout configure` offers it and `loadout configure set plugin codex-reviewer@agent-loadout on` turns it on. Sessions that do not use it pay nothing.
- **Claude Code only.** The entry has `target: claude` ([catalog format](../reference/catalog-format.md)). Codex's plugin setup and a profile's Codex side skip such a plugin and name it once as "Claude Code only, not added to Codex". Codex has its own `/review`.
- **A minimal Codex manifest.** Whether Codex's `marketplace add` and `upgrade` accept a plugin without `.codex-plugin/` could not be checked without running Codex. So the plugin ships a minimal `.codex-plugin/plugin.json` that keeps the shared marketplace readable; `target: claude` keeps the plugin uninstalled there.
- **This repo turns it on.** A project `.claude/settings.json` enables `codex-reviewer@agent-loadout` for everyone working here. Elsewhere it stays off. The repo-specific review rules moved into `AGENTS.md` "Code Review Rules", so Codex's review and the stand-in apply the same text. The old `.claude/agents/codex-reviewer.md` is removed: one source.
- **The agent is repo-neutral.** It reviews against the repo's default branch, reads `AGENTS.md` for rules, is read-only, and outputs the rubric's JSON (P0-P2). The rubric comes from openai/codex (Apache-2.0); the plugin's `NOTICE` names the source.

## Consequences

- A user who turns it on gets a review when Codex's quota is out. A user who does not sees no change.
- `target` on a plugin is a generic catalog field. Another Claude-Code-only plugin can use it.
- The rubric is copied at a known source and is not tracked upstream.
- No Codex-side agent exists, and nothing posts the findings to GitHub; the person or the session acts on them.
- If Codex is found to reject a plugin without `.codex-plugin/`, the minimal manifest is already in place.

## How to use it

[Use the codex-reviewer when Codex's review quota is out](../how-to/codex-review-stand-in.md)
