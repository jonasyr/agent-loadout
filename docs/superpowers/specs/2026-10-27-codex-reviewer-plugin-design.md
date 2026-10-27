# codex-reviewer as an opt-in plugin — design

## Intent

Codex's GitHub review ("@codex review") runs out of quota now and then. When it does, this repo uses a stand-in: the Claude Code agent `.claude/agents/codex-reviewer.md`. It reviews the branch diff with Codex's open-source review rubric and returns the same JSON findings (P0–P2). It has finished several PRs (#43, #68). Today only this repo has it. Every loadout user who uses Codex's GitHub review hits the same quota wall. So the agent ships with the kit, opt-in.

## Goals

- A second plugin, `codex-reviewer`, in the `agent-loadout` marketplace (`.claude-plugin/marketplace.json`, source `./plugins/codex-reviewer`). It carries one agent, `agents/codex-reviewer.md`. (User's choice.)
- Off by default: a catalog add-on entry with an `offer` key, so `loadout configure` offers it and `loadout configure set plugin codex-reviewer@agent-loadout on` turns it on. (User's choice.)
- Claude Code only. Codex has its own `/review`. (User's choice.)
- The agent is repo-neutral:
  - It reviews the current branch against the repo's default branch: `origin/HEAD` if set, else `main`, else `master`. It does not assume `main`.
  - It reads the repo's review guidance from `AGENTS.md` (the "Code Review Rules" section if present, otherwise the whole file). This is the file Codex's review reads. When it finds such a rule, it cites it, as now.
  - It stays read-only. It never edits files and never runs installers, deploys or mutating commands. It may run the repo's documented test command on the files it reviews, and only when `AGENTS.md` names one.
  - It outputs exactly the rubric's JSON, P0–P2 only.
- It uses Serena and codebase-memory when they are available, and grep/Read when they are not. With loadout's plugin on, the tool names are `mcp__plugin_loadout_serena__…` and `mcp__plugin_loadout_codebase-memory-mcp__…`.
- This repo:
  - The repo-specific lines of today's "This repository" section move into the "Code Review Rules" of this repo's `AGENTS.md`, so Codex and the stand-in apply the same rules. These are the edge-case machines, the test-command limit and the never-run-real-`claude`/`codex`/`loadout` rule.
  - Then `.claude/agents/codex-reviewer.md` is removed (user's choice: one source), and this repo uses the plugin.
- Attribution: the rubric is adapted from openai/codex (Apache-2.0). The plugin carries a `NOTICE` (or LICENSE excerpt) naming the source and license. The agent keeps its source line.
- Docs:
  - the add-on in `docs/reference/included-tools.md` (add-ons section);
  - a short how-to, "Use the codex-reviewer when Codex's review quota is out": turn it on, then run it ("run the codex-reviewer agent on this branch"), then read the JSON. It is linked from `docs/README.md`;
  - an ADR for shipping a second plugin from the marketplace;
  - the `AGENTS.md` map, if a new ADR number appears.

## Non-goals

- No Codex-side agent or skill.
- No automation that posts the findings to GitHub. The user (or the session) acts on them.
- No tracking of upstream rubric changes. The rubric is copied at a known source, as today.
- No new catalog kind "agent". The existing plugin kind covers it.

## Anti-goals

- The plugin costs context in sessions that never use it. Off by default prevents that.
- The agent edits code or runs anything that changes the machine.
- The agent invents findings to cite `AGENTS.md`, or drops ordinary findings because a rules file exists. Today's rubric text already forbids both. Keep it.
- loadout's own repo keeps two agents with the same purpose.

## Constraints

- Kit conventions apply (AGENTS.md): standard-library Python in `cli/loadout/`, tests with `fake_home`/`fake_runner`, Conventional Commits, no AI attribution, one home per fact.
- `claude plugin validate .` and `claude plugin validate plugins/codex-reviewer` must pass. CI's validate job runs the first.
- Existing tests that enumerate the marketplace's plugins or assume a single plugin must keep passing or be updated deliberately. Examples are update/plugin refresh, Codex marketplace handling, check rows and `duplicates.PLUGIN_ID` users.
- Codex adds the whole `agent-loadout` marketplace. A second plugin in it must not be installed into Codex by loadout (Claude Code only). Today it would be: `codex.plugin_routes` (cli/loadout/codex.py:1281-1298) routes every `enabledPlugins` entry, `apply_plugins` (codex.py:1849-1864) adds each, and profile installs are mirrored too (cli/loadout/codex_project.py:25-30).

## Decided after the builder check

- **Keeping it out of Codex (my call):** a generic catalog field on the entry, `"agents": ["claude"]` (documented in `docs/reference/catalog-format.md`). `plugin_routes` and the profile mirror (`codex_project`) skip a plugin whose catalog entry excludes Codex; the Codex plan/update output names it once as skipped ("Claude Code only"), following the existing "no Codex route" line.
- **Codex and the marketplace (my call):** whether Codex's `marketplace add`/`upgrade` tolerates a plugin without `.codex-plugin/` cannot be verified without running codex. So the plugin ships a minimal `.codex-plugin/plugin.json` anyway; the catalog field keeps it uninstalled in Codex.
- **Tools (my call):** the agent's `tools:` lists Read, Grep, Glob, Bash and the read-only Serena and codebase-memory tools in both name variants: loadout's (`mcp__plugin_loadout_serena__…`, `mcp__plugin_loadout_codebase-memory-mcp__…`) and own servers' (`mcp__serena__…`, `mcp__codebase-memory-mcp__…`). No Edit, Write or MultiEdit. The test that pins this (tests/test_hooks.py:72-83) moves to the plugin's agent.
- **This repo (user):** the plugin is on for everyone working here via a new project `.claude/settings.json` with `"enabledPlugins": {"codex-reviewer@agent-loadout": true}`; elsewhere it stays off. CONTRIBUTING.md:106 and docs/reference/modules.md:132 point to the plugin instead of the removed file.
- **Rules (user):** this repo's edge cases go into AGENTS.md's "Code Review Rules" for both Codex's review and the stand-in; the run limits (only the documented test command, never real `claude`/`codex`/`loadout`, no installers or evals, no edits) stand there as limits for any reviewer that runs commands.
- **Repo facts:** the ADR is 0044 (AGENTS.md map then says 0001-0044). The marketplace is GitHub `jonasyr/agent-loadout` (settings.base.json:4-7), so the add-on needs no new marketplace. The new marketplace entry comes second, without `version`, like the first (tests/test_hooks.py:86-91 pins `plugins[0]`). `loadout update` refreshes every enabled user-scope plugin; only `loadout@agent-loadout` triggers the core-reload fact (update.py:523-537), so the new plugin needs no special case there.

## Left to the builder

- The exact wording of the repo-neutral agent prompt, within the goals above.
- How the catalog entry is phrased (`reason`, `short`, `category`: workflow), following the other add-ons.
- Whether the plugin gets its own `README.md`.
