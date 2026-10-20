# Ask your agent about loadout

Use this page when you have a question about loadout or want to change your setup, but do not want to look up the command or edit files by hand.

## Ask in plain words

In Claude Code or Codex, ask what you want to know or change, for example:

- "How do I undo what loadout changed yesterday?"
- "Is Context7 on for me?"
- "Turn off Codex on this machine."
- "Add the web tools to this repo."
- "Answer in German from now on."
- "Which entries in `.claude/settings.json` did loadout write?"
- "Do my agents actually use Serena?"

The loadout plugin's `configure` skill picks this up by itself; loadout's rules tell the agent to use it for any loadout question or change. To call it explicitly, run `/loadout:configure` in Claude Code, or `$loadout:configure` in Codex.

## What it does

- **Questions:** it reads the docs in your clone of the kit (`loadout kit-path`), starting from [the docs index](../README.md), answers from the page that covers your question and names that page. When your own state matters, it first runs read-only commands (`loadout configure show`, `loadout configure own`, `loadout check`).
- **Changes:** it maps the request to `loadout` commands, shows them, and runs them only after your yes. Preferences, add-ons and your own tools go through `loadout configure`, a new skill of yours through `loadout configure new skill`; agents through `loadout configure set target`; repos through `loadout profile` or `loadout init` (without a terminal: `--dry-run`, show the plan, then `--yes` after your yes; `init` also takes `--agents`); reviewing your existing setup through `loadout adopt`; tool updates through `loadout update`; VS Code through `loadout bootstrap --install`, which installs the recommended Codex CLI next to VS Code's Codex extension, and in WSL `loadout bootstrap --vscode-path` (`--vscode-wsl` for a Windows window you open anyway; `--without-codex-cli` only if you want the extension alone) ([Use loadout with VS Code](vscode.md), [Recommended setups](setups.md#recommended-setups)); undo through `loadout restore`. Commands that remove, replace or write files in a repo record undo steps first; what restore does not undo is in [Undo what loadout changed](undo-and-restore.md#what-restore-does-not-undo).
- **Read-only answers about your files:** `loadout explain <file>` says which entries in a repo file (or in `~/.codex/config.toml` and `~/.codex/hooks.json`) loadout wrote and whether they are unchanged; the `loadout:usage` skill counts how often your agents used each tool family.
- **Setting loadout up:** asked to set loadout up or repair it, it follows [Set loadout up from inside an agent](install-with-an-agent.md).
- **Never by hand:** it does not edit `~/.claude/settings.json`, `~/.claude.json`, `~/.codex/config.toml` or your personal layer's files. When no command covers a request, it names the doc page with the manual way and leaves the decision to you.

Changes to your personal layer reach your other machines once the layer is committed and pushed. When it is a git repo, the skill asks you to run `loadout configure prefs` in a terminal, which lists the changes and offers to commit and push ([personal repo](personal-repo.md)).
