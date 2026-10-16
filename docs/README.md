# Documentation

Which page answers which question. The pages follow [Diátaxis](https://diataxis.fr/): a tutorial teaches one path, how-to pages solve one task, reference pages list the facts, explanation pages say why. Each fact has one home, and other pages link to it. How this is organised, and why: [Documentation strategy](explanation/documentation-strategy.md).

Questions about loadout, or a change to your setup? Ask your agent in plain words; see [Ask your agent about loadout](how-to/ask-about-loadout.md).

## Tutorials

- [Getting started](tutorials/getting-started.md). Read this when you install loadout for the first time, on Linux, macOS, WSL 2 or native Windows (experimental).

## How-to guides

- [Ask your agent about loadout](how-to/ask-about-loadout.md). Read this when you have a question about loadout or want to change your setup without looking up the command.
- [Handle your own tools](how-to/your-own-tools.md). Read this when you installed a skill, MCP server or plugin yourself (`npx`, `claude mcp add`, ...), when `adopt` or `check` lists tools loadout does not manage, or when you want to create a skill of your own.
- [Keep your personal layer in a private git repo](how-to/personal-repo.md). Read this when you want your preferences and own tools on more than one machine.
- [Find the path for your setup](how-to/setups.md). Read this before installing when you use Windows, WSL, Codex, or a machine or repo that already has parts set up: it names the path for each platform, agent and starting point.
- [Use loadout with Codex](how-to/codex.md). Read this for the Codex-only details: switching Codex on, hook approval, project trust and where it stays different.
- [Undo what loadout changed](how-to/undo-and-restore.md). Read this when something went wrong, or you want a removed tool back.
- [Set your working preferences](how-to/set-preferences.md). Read this when you want to change answer language, commit style, effort or another preference everywhere.
- [Write a personal profile](how-to/write-a-profile.md). Read this when you want your own preset of tools for a kind of project.
- [Add a tool to the catalog](how-to/add-to-catalog.md). Read this when you want to propose a tool to the kit.
- [Use loadout on Windows with WSL 2](how-to/wsl.md). Read this when you run loadout inside WSL.
- [Set loadout up from inside an agent](how-to/install-with-an-agent.md). Read this (or give it to Codex or Claude Code) when you want your agent to install loadout for you.
- [Troubleshooting](how-to/troubleshooting.md). Read this when a command fails or `loadout check` reports a problem.
- [Run the skill evals](how-to/run-evals.md). Read this when you changed one of the plugin's skills.
- [Uninstall loadout](how-to/uninstall.md). Read this when you want to remove loadout from a machine.

## Reference

- [CLI reference](reference/cli.md). Read this when you need a command, flag or exit code.
- [Included tools](reference/included-tools.md). Read this when you want to know which plugins, tools, profiles and add-ons the kit sets up.
- [Personal layer](reference/personal-layer.md). Read this when you want to know which file in your personal layer does what, and what stays on one machine.
- [Settings merge](reference/settings-merge.md). Read this when you want to know exactly how your `settings.json` and the kit's settings are combined, including hooks.
- [Hooks](reference/hooks.md). Read this when you want to know which hooks the loadout plugin runs, or how to name one of your own hooks.
- [Catalog format](reference/catalog-format.md). Read this when you edit `catalog.json`.
- [Profile format](reference/profile-format.md). Read this when you write or read a profile file.
- [Preferences format](reference/preferences-format.md). Read this when you want the list of working preferences, their options and where each answer is stored.

## Explanation

- [The toolset](explanation/the-toolset.md). Read this when you want to know which plugins, MCP servers, skills and tools the kit sets up, what each is for, and how they form one workflow.
- [Architecture](explanation/architecture.md). Read this when you want to understand how the kit, your personal layer and your agents' folders (`~/.claude`, `~/.codex`) fit together, and how the daily sync works.
- [Security and trust](explanation/security-and-trust.md). Read this when you want to know what runs without asking, what loadout touches, where secrets go and how to opt out.
- [Documentation strategy](explanation/documentation-strategy.md). Read this when you want to know how loadout organises a repo's documentation and what the docs skills do. A worked example is in [examples/docs-audit-before-after](examples/docs-audit-before-after/README.md).
- [The execution advisor](explanation/execution-advisor.md). Read this when you want to know how loadout decides how a finished plan is run.

## Decisions

- [Architecture decision records](adr/README.md). Read this when you want to know why something was decided, and what else was considered.

## Working documents

[`superpowers/`](superpowers/README.md) holds design specs and implementation plans written while the kit was built. They are working documents, not user documentation, and may be out of date; the pages above win.
