# Uninstall loadout

Use this page to remove loadout from a machine. To undo a single change instead, see [Undo what loadout changed](undo-and-restore.md).

If you recorded own tools as global, do the last section first. If Codex is on, do the [Codex section](#codex) before you delete `~/.claude/.loadout`: it needs a file from there. Steps that use the `claude` command or `~/.claude/settings.json` do not apply if you only use Codex.

## Remove the kit

1. Remove `loadout@agent-loadout` from `enabledPlugins` and `agent-loadout` from `extraKnownMarketplaces` in `~/.claude/settings.json` (and in your personal `settings.json` if you keep it). Otherwise Claude Code clones the marketplace and installs the plugin again at its next start.
2. Uninstall the plugin and remove the links and state.

On Linux, macOS and WSL:

```bash
claude plugin uninstall loadout@agent-loadout
claude plugin marketplace remove agent-loadout
rm ~/.claude/rules/loadout ~/.claude/rules/personal ~/.local/bin/loadout   # the launcher
rm -r ~/.claude/.loadout          # loadout's state (snapshots, timestamps)
```

Remove the block between `# loadout PATH` and `# loadout PATH end` from `~/.bashrc`, `~/.zshrc` and `~/.profile` (or `~/.bash_profile`).

On Windows, delete `loadout` and `loadout.cmd` in `%USERPROFILE%\.local\bin`, remove the folders bootstrap added from your user PATH (Settings, Environment Variables), and delete the folders `%USERPROFILE%\.claude\rules\loadout`, `%USERPROFILE%\.claude\rules\personal` and `%USERPROFILE%\.claude\.loadout`. If loadout copied instead of linking (see [Links and copies](../reference/personal-layer.md#links-and-copies)), these are folders, not links.

You can then delete the clone (`agent-loadout` in the folder you ran bootstrap from, usually your home).

## Codex

Only if Codex was on. `$CODEX_HOME` replaces `~/.codex` below if you set it. Turning Codex off (`loadout configure set target codex off`) removes nothing.

1. In `~/.codex/AGENTS.md`, delete the block from `<!-- loadout:start -->` to `<!-- loadout:end -->`. If loadout created the file, it holds only that block. Your own text stays.
2. In `~/.codex/config.toml`, remove the `[mcp_servers.NAME]` sections loadout wrote: `serena`, `context7` and one per MCP server of your personal `mcp.json`. The list of names is the `tables` entry in `~/.claude/.loadout/codex-config.json`; the same file's `keys` entry lists the lines loadout added (`model_reasoning_effort`, `tui.notifications`). A section you changed yourself is not in the list. Also remove the `[plugins."NAME@MARKET"]` sections of plugins that loadout installed for a single repo (`enabled = false` there), if you have any.
3. Remove the links in `~/.agents/skills` that point into your personal layer's `skills/` or at `~/.claude/skills`. Skills you put there yourself stay.
4. Remove the plugins and marketplaces loadout added. `codex plugin list` shows their ids:

   ```bash
   codex plugin remove loadout@agent-loadout
   codex plugin marketplace remove agent-loadout
   ```

   Plugins you enabled for Claude Code were installed in Codex from their marketplaces too. Remove each the same way if you want: `codex plugin remove NAME@MARKET`, then `codex plugin marketplace remove MARKET`.
5. In each repo where you ran `loadout init` or `loadout profile`: remove the sections loadout added to `.codex/config.toml` and the links in `.agents/skills` that point to `../../.claude/skills/NAME`. Use git there.

Then delete `~/.claude/.loadout` as in [Remove the kit](#remove-the-kit). If you restore from a backup instead, `loadout restore` removes the plugins and marketplaces it recorded and puts back the saved `AGENTS.md` and `config.toml` ([Undo](undo-and-restore.md#codex)).

## What stays

- **MCP servers** from your personal `mcp.json` were added with `claude mcp add-json -s user`. Remove them with `claude mcp remove -s user NAME` if you no longer want them.
- **Plugins** that bootstrap installed stay installed. Uninstall each with `claude plugin uninstall ID` if you want (Codex: see above).
- **`~/.claude/settings.json`** keeps the other merged values (the other plugins, `env`, `permissions`). Remove them if you want, or restore an older backup from `~/.claude/backups/`.
- **Git's credential helper for GitHub**, if bootstrap ran `gh auth setup-git`. Remove it with `git config --global --unset-all credential.https://github.com.helper`.
- **Tools bootstrap installed** (uv, Claude Code, Codex, mise and what mise installed, codebase-memory-mcp, rtk, npm tools) stay. Remove them with their own uninstall steps: see the docs of [uv](https://docs.astral.sh/uv/), [Claude Code](https://code.claude.com/docs/en/setup) and [mise](https://mise.jdx.dev/).
- **The shell startup file** keeps the "# loadout secrets" block that bootstrap added. Delete it if you want.
- **Your personal layer and `secrets.env`** under `~/.config/loadout/` are never touched. Delete them yourself if you want them gone.
- **Backups** in `~/.claude/backups/` stay. They can hold old configs with secrets, so delete them when you no longer need them.
- **Profiles applied to repos** stay: they are normal files in the repo's `.claude/settings.json` and `.mcp.json`, and with Codex on also `.codex/config.toml` and `.agents/skills`.

## If you recorded own tools as global

- Global skills live in `<personal layer>/skills/`, and `~/.claude/skills/<name>` links to them. Replace each link with a copy before you delete the personal layer, for example:

  ```bash
  cp -rL ~/.claude/skills/<name> ~/.claude/skills/<name>.copy && rm ~/.claude/skills/<name> && mv ~/.claude/skills/<name>.copy ~/.claude/skills/<name>
  ```

- Remove `~/.claude/hooks/personal` (a link to `<personal layer>/hooks/`) and the hooks in `~/.claude/settings.json` whose command uses it.

How these were recorded: [Handle your own tools](your-own-tools.md).
