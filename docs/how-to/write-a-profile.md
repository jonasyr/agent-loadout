# Write a personal profile

Use this page to make a preset of plugins, MCP servers, settings and commands that you can add to any repo, for example for a kind of project the kit's profiles do not cover.

The kit ships `thesis`, `web`, `db`, `sonar` and `android`. Yours live in `<personal layer>/profiles/`, by default `~/.config/loadout/personal/profiles/`. The format is in [profile format](../reference/profile-format.md).

1. **Create the file.** `<personal layer>/profiles/NAME.json`, where NAME uses lowercase letters, digits, `-` and `_`. All fields are optional; give it a `description`:

   ```json
   {
     "description": "Rust CLI work: a guard-rail plugin and a docs MCP server",
     "install": ["hookify@claude-plugins-official"],
     "mcp": { "mcpServers": { "docs": { "type": "stdio", "command": "npx", "args": ["-y", "some-docs-mcp@1.2.3"] } } },
     "settings": { "permissions": { "allow": ["Bash(cargo check:*)"] } },
     "commands": [["cargo", "fetch"]],
     "notes": "Run cargo fetch once before going offline."
   }
   ```

   Pin MCP server versions. A profile name that matches a kit profile replaces it for you; nothing is merged.
2. **Preview it in a repo.** In the repo, run `loadout init --dry-run NAME`. It prints the profile's description, the skills it would copy, the plugins and commands it would run and the files `init` would create, and changes nothing. It does not show the settings diff.
3. **Apply it.** In the repo, run:

   ```bash
   loadout profile NAME
   ```

   This merges `settings` into the repo's `.claude/settings.json` and `mcp` into `.mcp.json`, copies `skills`, installs `install` plugins at project scope (in Claude Code; with Codex on, also in Codex, see [In Codex](../reference/profile-format.md#in-codex)) and runs `commands`. Add `--no-install` to skip the plugins and commands. Commit what it wrote: `.claude/settings.json`, `.mcp.json`, any `.claude/skills/`, and with Codex on `.codex/config.toml` and `.agents/skills`. They are normal project files and `loadout restore` does not undo them.
4. **Sync it.** To use the profile on other machines, commit and push your personal layer. See [Sync](../reference/personal-layer.md#sync).

## Changes later

A profile is copied into a repo when you apply it. Later edits to the profile do not reach repos until you apply it again, and the skill copies in a repo can drift from your personal layer ([Skills](../reference/profile-format.md#skills)).

`loadout adopt` and `loadout configure set own NAME project:NAME` can create or extend a personal profile from a tool you already use. See [Handle your own tools](your-own-tools.md).
