# Add a tool to the catalog

Use this page to propose a tool to the kit: a plugin, MCP server, skill, hook or binary that `loadout adopt`, `check`, `configure` or `update` should know about. The catalog is where the "why" of every keep or drop decision lives, so every entry needs a `reason`.

1. **Pick the entry shape.** Read [catalog format](../reference/catalog-format.md). Choose `kind` and `status`, and decide how an installed item is recognised (`match.names` or `match.contains`). Copy a similar entry in `catalog.json` as a start.
2. **Write the entry.** Add it to the `entries` list in `catalog.json`.
   - `id` must be unique.
   - `reason` says why the tool has this status, in a sentence. For a `superseded` or `alternative` tool, name the replacement in `by`.
   - For `status: profile`, set `profile` to the name of a file in `profiles/`.
   - For a `binary`, `version.cmd` is required. Add `install`, `update` or `manual` so `loadout check` can name a fix.
   - To make it a global add-on in `loadout configure`, add `offer`. Pin MCP server versions: no `@latest`.
3. **Check it reads right.** Run `loadout configure show` (read-only) to see an add-on, or `loadout check` to see a binary.
4. **Run the static tests.** They enforce the format (unique ids, valid `kind` and `status`, a `reason`, a non-empty `match`, existing profiles, declared marketplaces, no `@latest`):

   ```bash
   uv run --python 3.12 --with pytest pytest -q tests/test_repo_static.py
   ```

   Then the whole suite:

   ```bash
   uv run --python 3.12 --with pytest pytest -q
   ```

5. **Open a pull request.** Use a Conventional Commit message such as `feat(catalog): add <tool>`. Say in the PR why the tool belongs, and which tool it replaces or complements.
