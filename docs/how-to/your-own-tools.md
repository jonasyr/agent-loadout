# Handle your own tools

Use this page when `loadout adopt` or `loadout check` lists tools that loadout does not manage, and you want them to follow you to other machines, live in one project, stay put, or go away.

`loadout adopt` looks at every user-scope plugin, marketplace, MCP server (`~/.claude.json`, `~/.claude/.mcp.json`), skill (`~/.claude/skills`) and hook (`~/.claude/settings.json`). What the [catalog](../reference/catalog-format.md) does not know is listed under **YOUR OWN TOOLS**. Items already in your personal layer show as keep, and so does a plugin that a personal profile holds while it is disabled globally. Project-level config is not inspected.

`loadout configure own` lists the same items. Flags and exit codes of the commands are in the [CLI reference](../reference/cli.md#loadout-adopt).

## Choices

| Choice | Meaning |
|---|---|
| `global` | Record it in your personal layer, so it follows you to every machine. |
| `project:<profile>` | Disable or remove it on this machine and write it into a personal profile (`profiles/<profile>.json`). Apply that profile to a repo with `loadout profile <profile>`. |
| `leave` | Stay as is, on this machine only. Not asked again here. |
| `remove` | Remove it. It goes into a backup and `loadout restore` brings it back. |

Nothing changes without an answer. In a terminal, adopt asks once: `your own tools: [l]eave all / [c]hoose each`. Enter decides nothing. After `c` it asks per item, and Enter (or three invalid answers) skips that item. Only an explicit `leave` is remembered, in `~/.claude/.loadout/own-decisions.json`, which is local to this machine. `--yes` and runs without a terminal decide nothing and remember nothing. `--skip NAME,...` skips items for one run and remembers nothing.

Catalog plugins that adopt would disable globally accept `global` ("keep global"): pick the group (`p`), then `k` for that plugin. Not every choice fits every item: marketplaces and skills that are links to a shared source cannot go into a profile, and servers in `~/.claude/.mcp.json` can only be left or removed. The prompt and `loadout configure own` list only what applies.

A profile name that matches a kit profile (for example `db`) starts as a copy of that kit profile and replaces it for you. Later changes to the kit profile no longer reach you. Adopt prints a note when this happens. See [Personal and kit profiles](../reference/profile-format.md#personal-and-kit-profiles).

After `project` choices, interactive adopt offers to apply the profile to repos. The default is none. It suggests repos known to Claude Code (`~/.claude.json`) whose project config mentions the item, or you type paths. Applying a profile is the same as running `loadout profile` in that repo: it writes the repo's committed `.claude/settings.json` and `.mcp.json`, and `loadout restore` does not undo it. `--own` never applies profiles to repos.

When something was recorded or removed, adopt and `configure set own` end with "Restart Claude Code (or run /reload-plugins) to load the changes."

## Be asked again about a left item

Choose another answer with `loadout configure set own NAME CHOICE`, or delete its entry (or the whole file) in `~/.claude/.loadout/own-decisions.json`. `loadout configure own --all` lists the left items too.

## Without a terminal

```bash
loadout adopt --apply --own "foo@bar=global,my-db=project:mydb,notes=leave"
loadout configure set own foo@bar global
```

Items not named stay as they are. `--groups own` is refused (exit code 1); use `--own`. Names are as `loadout configure own` prints them:

- If a name matches several kinds, write `<kind>:<name>`.
- A hook is `<Event>:<matcher>`, and `Stop:` when it has no matcher. When several hooks share that name, add `#n` (`PreToolUse:Bash#2`), counted in the order `loadout configure own --all` lists them. Result lines show a hook without matcher as `hook Stop (no matcher)`.
- A name containing a comma (a hook matcher such as `Bash,Edit`) cannot be given here. Choose it in the interactive prompt.

The naming rules are in [hooks](../reference/hooks.md#naming-hooks-of-your-own-tools).

### Exit codes

| Command | Code | Meaning |
|---|---|---|
| `adopt --apply --own` | 2 | An unknown or duplicate name, a bad choice, or a name that needs `<kind>:` or `#n`. Nothing changed. |
| `adopt --apply` | 2 | No terminal and none of `--yes`, `--groups` or `--own`. Nothing changed. |
| `configure set own` | 2 | The same bad input as above. Nothing changed. |
| `configure set own`, `adopt --apply --own` | 1 | At least one named item was not recorded, or recorded but not active on this machine (see the `skipped:`/`failed:` line). A removal that did not happen says `skipped (...)` or `not removed`. The other items were applied. |

## What each choice changes

The files a `global` or `project` choice writes in the personal layer are in [personal-layer](../reference/personal-layer.md#what-gets-recorded-here). On this machine:

| Kind | With `global` |
|---|---|
| Plugin, marketplace | Unchanged. |
| MCP server | Secrets in `env` and `headers` become `${VAR}` and move to `secrets.env`. The server is re-added with the `${VAR}` config and managed by loadout. |
| Skill (folder) | Replaced by a link to the copy in the personal layer. The original goes into the backup. |
| Skill (link to a shared source) | Unchanged. |
| Hook | Exactly that hook is replaced in place, in its group, by the recorded hook and tracked as applied by loadout (also a hook you re-added by hand after deleting it, whose remembered deletion is cleared). It does not run twice, and removing it from the personal layer later removes it here too. A hook with the same identity already in the personal layer is replaced in its slot, not added a second time. |

With `project`, the item goes into a personal profile instead (`profiles/<name>.json`; skills into `profiles/skills/<name>/`) and is disabled (plugins) or removed (MCP servers, skills, hooks) from your global setup. A removed skill reads `skill <name>: removed from ~/.claude/skills (kept in profile <p>; original in the backup)`. `loadout profile` copies a profile's skills into a repo and never overwrites an existing one.

## Sync to other machines

`global` and `project` choices reach another machine only when your personal layer is a git repo and you commit and push. The other machine pulls it daily (see [Sync](../reference/personal-layer.md#sync)).

- Interactive adopt offers this at the end, when you chose anything other than `leave`. It shows the changes and asks `commit and push your personal layer? [y/N]`. It refuses, without asking, when a private file would be committed.
- After `--own` or `configure set own` nothing is committed. Run it yourself:

```bash
cd ~/.config/loadout/personal      # or $LOADOUT_PERSONAL
git status --short
git add -A && git commit -m "chore: record own tools" && git push
```

`leave` decisions stay on the machine where you made them.

On the second machine, after the daily pull, loadout links the pulled skills and hook scripts by itself (`~/.claude/skills/<name>`, `~/.claude/hooks/personal`) and merges the hooks. Plugins install at the next Claude Code start. Pulling is skipped while the personal layer has uncommitted changes, or when `LOADOUT_NO_AUTO_PULL=1` is set.

## Secret guard

Nothing that looks like a secret is written to the personal layer. Every printed line is redacted too.

- **MCP servers:** values in `env` and `headers` become `${VAR}` and move to `secrets.env`. A secret in `args`, in the URL (query string or a high-entropy path segment) or in a multi-line value is refused, because it cannot be moved safely.
- **Marketplaces:** a source URL with credentials or a token is refused.
- **Hooks and skills:** a hook command, args, script or any skill file that looks secret is refused. All skill files are scanned, binary ones by their text runs; a file with a UTF-16 byte-order mark or any NUL byte is scanned as UTF-8 and as UTF-16 (LE and BE). An unreadable file refuses too.
- **Private files:** a skill that contains one of these, and a hook that names one anywhere in its command, is refused: `.ssh`, `.gnupg`, `.aws`, `.azure`, `.kube`, `.docker` and `.password-store` folders, `~/.config/gh`, `~/.claude.json`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `id_rsa*`, `id_dsa*`, `id_ecdsa*`, `id_ed25519*`, `.env`, `.env.*` (except `.env.example`, `.env.sample` and `.env.template`), `.netrc`, `.npmrc`, `.pypirc`, `credentials`, `credentials.json`, `credentials.csv`, `.git-credentials`, `.vault-token` and `*.kdbx`. The commit offer refuses the same files.
- **Git checkouts:** a skill that contains a `.git` folder or file is refused. Copy it without `.git`.

A refusal prints `skipped: ...` and changes nothing for that item. Move the secret to `secrets.env`, use `${VAR}`, then run it again. Secrets belong in `~/.config/loadout/secrets.env`.

## Hooks

- Only a simple command of the form `<interpreter> <script> args` gets its script copied. That is one file, copied to `<personal>/hooks/<file>`, and the command points to `$HOME/.claude/hooks/personal/<file>`. Files the script reads next to it must be copied by hand.
- A complex shell command (`;`, `&&`, pipes, redirects, `$(...)`, globs and similar), a hook in exec form (`args`), and a path outside your home folder are recorded as they are, with a note. They work only where their paths exist. Files under `/usr`, `/bin`, `/sbin`, `/opt/homebrew` and `/usr/local` (an interpreter, for example) do not trigger the "outside your home folder" note.
- A hook that refers to a private file is refused.
- Values of interpreter flags (`node --require X`, `python -X opt`, `bash -o opt`, `env -u VAR`) are not taken for the script; such a file under your home folder gets a note. Inline code (`-c`, `-e`, `-m`, `env -S`) is recorded as is with the complex-command note.

How recorded hooks are merged into `settings.json` (identity, deleted hooks, hooks you edited) is in [settings merge](../reference/settings-merge.md#hook-merge).

## Known limits

- Windows: Claude Code runs hook commands through Git Bash, so a hook's script path must use forward slashes (`C:/Users/me/x.sh`) or quotes for loadout to recognise and copy the script. An unquoted backslash path is recorded as is (Git Bash would misread it too). Script detection is tested on Linux and macOS.
- An MCP server is managed by loadout only if it is in `managed-mcp.json` or its config in `~/.claude.json` is identical to the personal one; otherwise loadout leaves your server alone. Recording through adopt seeds `managed-mcp.json`.
- A profile is copied into a repo when applied. Later changes to the personal profile do not reach repos until you apply it again, and skill copies in a repo can drift from your personal layer.
- A skill recorded as a pointer to a shared source is linked only on machines where that source exists.
- If removing an item from this machine fails (a `failed:` line), it shows up under your own tools again next time. Fix the cause and choose again.
- An older loadout stored a leave decision for a `~/.claude/.mcp.json` server under the plain server name, so it also hides a user-scope server of the same name. Deciding the `.mcp.json` server again replaces it, and the user-scope one is then asked about again.
- Every file of a skill is scanned, so very large skill files slow the run down.
- Hooks in project settings files and `leave` decisions on other machines are out of scope.
- Backups made before the snapshot was part of them, and the snapshot rewrites without a backup: see [Limits](../reference/settings-merge.md#limits).
