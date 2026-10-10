# Troubleshooting

Start with `loadout check`. It is read-only, names what is wrong and prints the fix. Each line is `ok`, `warn` or `FAIL`; see [loadout check](../reference/cli.md#loadout-check) for what it tests. On WSL, see also [WSL](wsl.md).

## Install and PATH

| Symptom | Fix |
|---|---|
| `loadout: command not found` | Add `~/.local/bin` to your `PATH` (Windows: `%USERPROFILE%\.local\bin`) and open a new terminal. |
| `npm error code EACCES` when installing pyright / typescript-language-server / playwright-cli | Your global npm prefix is root-owned (for example `/usr`). Either `npm config set prefix ~/.local` (then re-run `loadout bootstrap --install`), or install them with your version manager, for example `mise use -g npm:pyright npm:typescript-language-server`. |
| A required tool is missing | Re-run `./bootstrap.sh --install`. `loadout check` shows manual install steps for what it cannot install. |
| A plugin or MCP server is missing in Claude Code | Restart Claude Code. Then `loadout check` lists what is missing and how to fix it. Enabled plugins install at the next Claude Code start. |

## Settings

| Symptom | Fix |
|---|---|
| `invalid JSON in .../settings.json` | Fix the syntax error at the reported position, then run `loadout apply-settings`. |
| "settings drift" warning | Something changed a kit-managed value. Run `loadout apply-settings`, or put your preferred value in your personal `settings.json`. See [settings merge](../reference/settings-merge.md). |
| `link rules/personal` is `FAIL` | `<personal layer>/rules` does not exist, so the link was not made. Create the personal layer (`loadout bootstrap`). |

## Undo

| Symptom | Fix |
|---|---|
| Something went wrong after adopt | `loadout restore <backup path printed by adopt>`. `loadout restore --list` shows all backups. See [Undo what loadout changed](undo-and-restore.md). |

## Your own tools

| Symptom | Fix |
|---|---|
| `adopt --apply` exits with code 2 | Either it was run without a terminal: add `--yes` (safe defaults), `--groups remove,migrate,...` or `--own NAME=CHOICE,...`. Or the `--own` input was wrong: the message names the problem and nothing changed. |
| `loadout: no unmanaged item named 'X' (see: loadout configure own --all)` | Use the name exactly as `loadout configure own --all` prints it. A hook is `Event:matcher` (`Stop:` without matcher). |
| `hook 'X' matches N hooks; pick one: ...` or `'X' matches several kinds` | Add `#n` to the hook name as the message shows, or write `<kind>:<name>`. See [hook names](../reference/hooks.md#naming-hooks-of-your-own-tools). |
| `loadout configure set own` exits with code 1 and prints `skipped:` or `failed:` | Nothing was recorded for that item. The line says why. Typical causes: a secret or private file (see [Secret guard](your-own-tools.md#secret-guard)), a name that already exists in your personal layer with different content, or a file that could not be written. Fix it and run the command again. |
| I left a tool and want to be asked about it again | `loadout configure own --all` lists the left ones. Decide again with `loadout configure set own NAME CHOICE`, or delete its entry in `~/.claude/.loadout/own-decisions.json`. |
| `loadout check` warns "own tools" | Some tools are not managed by loadout. Decide with `loadout adopt --apply` or `loadout configure own`. See [Handle your own tools](your-own-tools.md). |
| A global skill or hook script is missing on another machine | Commit and push the personal layer on the first machine. The other machine links them after its daily pull (or `loadout bootstrap`). See [Sync to other machines](your-own-tools.md#sync-to-other-machines). |

## Windows

| Symptom | Fix |
|---|---|
| Links were copied instead of linked | Enable Developer Mode (Settings, For developers) and re-run bootstrap, which switches back to links. Copies still work and are refreshed after each daily sync. Edit the source in your personal layer, not the copy: an edited copy is moved into a backup on the next refresh (the session notice names it). See [Links and copies](../reference/personal-layer.md#links-and-copies). |
| "cannot take JSON arguments (Windows .cmd shim)" | The npm-installed `claude.cmd` cannot receive JSON safely, so loadout changes nothing for that server. Best fix: install the native `claude.exe` and re-run. Otherwise open the private `manual-commands.txt` (path printed): with Claude Code closed, add the JSON block it shows under `"mcpServers"` in `%USERPROFILE%\.claude.json` (the file also has the macOS/Linux shell form). |
| Secrets in `secrets.env` are not seen | PowerShell's execution policy is `Restricted`, so profiles do not run. Bootstrap prints the command to allow them (`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`) but does not change it. |
| A hook script is not found | Claude Code runs hook commands through Git Bash. Use forward slashes (`C:/Users/me/x.sh`) or quotes. |

## Secrets

| Symptom | Fix |
|---|---|
| An MCP server does not see a key from `secrets.env` | Bootstrap adds a line to your shell startup file that loads `~/.config/loadout/secrets.env`. It only reaches Claude Code started from a shell that read that file: open a new terminal and start Claude Code from there. |

## Cost

| Symptom | Fix |
|---|---|
| Context or token use is high | Heavy tools are per-project, and rtk compresses command output. Check with `/context` in Claude Code. Turn off an add-on you do not use with `loadout configure set plugin ID off`. |
