# Uninstall loadout

Use this page to remove loadout from a machine. To undo a single change instead, see [Undo what loadout changed](undo-and-restore.md).

If you recorded own tools as global, do the last section first.

## Remove the kit

On Linux, macOS and WSL:

```bash
claude plugin uninstall loadout@agent-loadout
claude plugin marketplace remove agent-loadout
rm ~/.claude/rules/loadout ~/.claude/rules/personal ~/.local/bin/loadout
rm -r ~/.claude/.loadout          # loadout's state (snapshots, timestamps)
```

On Windows, delete `loadout` and `loadout.cmd` in `%USERPROFILE%\.local\bin`, and delete the folders `%USERPROFILE%\.claude\rules\loadout`, `%USERPROFILE%\.claude\rules\personal` and `%USERPROFILE%\.claude\.loadout`. If loadout copied instead of linking (see [Links and copies](../reference/personal-layer.md#links-and-copies)), these are folders, not links.

You can then delete the clone (`~/agent-loadout`).

## What stays

- **MCP servers** from your personal `mcp.json` were added with `claude mcp add-json -s user`. Remove them with `claude mcp remove -s user NAME` if you no longer want them.
- **Plugins** that bootstrap installed stay installed. Uninstall each with `claude plugin uninstall ID` if you want.
- **`~/.claude/settings.json`** keeps the merged values. Remove the kit's `enabledPlugins` and `extraKnownMarketplaces` entries if you want, or restore an older backup from `~/.claude/backups/`.
- **The shell startup file** keeps the "# loadout secrets" block that bootstrap added. Delete it if you want.
- **Your personal layer and `secrets.env`** under `~/.config/loadout/` are never touched. Delete them yourself if you want them gone.
- **Backups** in `~/.claude/backups/` stay. They can hold old configs with secrets, so delete them when you no longer need them.
- **Profiles applied to repos** stay: they are normal files in the repo's `.claude/settings.json` and `.mcp.json`.

## If you recorded own tools as global

- Global skills live in `<personal layer>/skills/`, and `~/.claude/skills/<name>` links to them. Replace each link with a copy before you delete the personal layer, for example:

  ```bash
  cp -rL ~/.claude/skills/<name> ~/.claude/skills/<name>.copy && rm ~/.claude/skills/<name> && mv ~/.claude/skills/<name>.copy ~/.claude/skills/<name>
  ```

- Remove `~/.claude/hooks/personal` (a link to `<personal layer>/hooks/`) and the hooks in `~/.claude/settings.json` whose command uses it.

How these were recorded: [Handle your own tools](your-own-tools.md).
