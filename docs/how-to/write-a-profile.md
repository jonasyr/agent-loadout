# Write a personal profile

Use this page to make a preset of plugins, MCP servers, settings and commands that you can add to any repo, for example for a kind of project the kit's profiles do not cover.

The kit ships `thesis`, `web`, `db`, `sonar` and `android`. Yours live in `<personal layer>/profiles/`, by default `~/.config/loadout/personal/profiles/`. The format is in [profile format](../reference/profile-format.md).

1. **Create the file.** `<personal layer>/profiles/NAME.json`, where NAME starts with a lowercase letter or digit, followed by lowercase letters, digits, `-` and `_`. All fields are optional; give it a `description`:

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

   To ship skills with it, add `skills`: names of folders in `<personal layer>/profiles/skills/` (or the kit's `profiles/skills/`), copied into the repo; see [Skills](../reference/profile-format.md#skills). Pin MCP server versions. A profile name that matches a kit profile replaces it for you; nothing is merged.
2. **Preview it in a repo.** In the repo, run `loadout profile NAME --dry-run`. It prints the plan: each file with its diff (also the `.claude/settings.json` and `.mcp.json` changes), the skills it would copy, and the plugins and commands it would run. It changes nothing.
3. **Apply it.** In the repo, run:

   ```bash
   loadout profile NAME
   ```

   It shows the plan and asks `Apply these changes? [y/N]` (without a terminal, add `--yes`). Then, in a Claude Code repo, it merges `settings` into `.claude/settings.json` and `mcp` into `.mcp.json`; in a Codex repo it writes the `mcp` servers into `.codex/config.toml` ([In Codex](../reference/profile-format.md#in-codex)); a repo for both agents gets both. The merges are three-way against what it wrote last time, so a teammate's changes stay: when a teammate changed an entry the profile sets, the run keeps the repo's value and asks `Use the profile's values for these? [y/N]` (`--take-profile` takes the profile's values without asking; [Applying a profile](../reference/profile-format.md#what-applying-a-profile-does)). It also copies `skills`, installs `install` plugins at project scope (in Claude Code; when the repo is for Codex, also in Codex, see [In Codex](../reference/profile-format.md#in-codex)) and runs `commands`. Add `--no-install` to skip the plugins and commands. Commit what it wrote: `.loadout.json` (if it was new), then for a Claude Code repo `.claude/settings.json`, `.mcp.json` and any `.claude/skills/`, and for a Codex repo `.codex/config.toml` and `.agents/skills` (in a Codex-only repo the skills live there). They are normal project files. The run ends with `undo: loadout restore <dir>`, which puts the files back; it cannot undo the profile's `commands` ([Repo writes](../reference/cli.md#repo-writes)).
4. **Sync it.** To use the profile on other machines, commit and push your personal layer. See [Sync](../reference/personal-layer.md#sync).

## Changes later

A profile is copied into a repo when you apply it. Later edits to the profile do not reach repos until you apply it again, and the skill copies in a repo can drift from your personal layer ([Skills](../reference/profile-format.md#skills)).

`loadout adopt` and `loadout configure set own NAME project:NAME` can create or extend a personal profile from a tool you already use. See [Handle your own tools](your-own-tools.md).
