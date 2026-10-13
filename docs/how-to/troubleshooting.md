# Troubleshooting

Start with `loadout check`. It is read-only, names what is wrong and prints the fix. It prints `Health check: N of M OK` and then only the problems (`loadout check --verbose` lists every check as `ok`, `warn` or `FAIL`); see [loadout check](../reference/cli.md#loadout-check) for what it tests. On WSL, see also [WSL](wsl.md).

## Install and PATH

| Symptom | Fix |
|---|---|
| `loadout` or `claude` not found right after bootstrap | Open a new terminal. Bootstrap added `~/.local/bin` and the mise shims to your profile (block `# loadout PATH`); Windows: your user PATH, which also gets npm's global folder (wherever `npm prefix -g` points) and codebase-memory-mcp's folder. |
| `note: ~/.local/bin can be written by other users (mode 0775)` after a failed install | Some installers, codebase-memory-mcp's among them, refuse to put a program into a folder that other users can write to. Debian and Ubuntu create folders like that by default (umask 002). Run `chmod go-w ~/.local/bin`, then run bootstrap again. Bootstrap creates the folder without group write access itself, so this only happens when it already existed. |
| `missing node: not installed because mise failed to install` | mise failed to install; see the line above it. Fix that, then re-run bootstrap. |
| `npm error code EACCES` when installing pyright / typescript-language-server / playwright-cli | Your global npm prefix is root-owned (for example `/usr`). Either `npm config set prefix ~/.local` (then re-run `loadout bootstrap --install`), or install them with your version manager, for example `mise use -g npm:pyright npm:typescript-language-server`. |
| `loadout needs Python 3.11 or newer (found 3.X). Re-run bootstrap (it gets one through uv) or install it yourself.` | Re-run bootstrap (it installs uv, which provides Python), or install Python 3.11 or newer yourself (on Windows from python.org or `winget install Python.Python.3.12`). |
| `loadout needs Python 3.11 or newer, or uv, on PATH` | The launcher found neither. Re-run bootstrap (it installs uv). |
| `could not install uv (offline?). Install it from https://docs.astral.sh/uv/ and run this again.` | Bootstrap could not download uv. Check your network, or install uv from the linked page, then run bootstrap again. |
| `could not get Python 3.11 or newer through uv (offline?). Check your connection and run this again.` | uv could not find or download a Python for loadout. Check your network and run the command again; installing Python 3.11 or newer yourself also works. |
| `loadout needs curl to download uv. Install it, then run this again:` | Install curl (Linux: `sudo apt install curl`), then run bootstrap again. |
| A required tool is missing | Re-run `./bootstrap.sh --install` (Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap.ps1 --install`). `loadout check` shows manual install steps for what it cannot install, for example rtk on native Windows. |
| No session notices, or the daily sync never runs | `loadout` must be on the `PATH` that the agent's hooks see (Claude Code, or Codex after you approved the hooks). The plugin's hook runner exits 0 silently when the command is missing (`plugins/loadout/hooks/run.sh`). Add `~/.local/bin` to the `PATH` of the environment the agent starts from, then restart it. |
| A plugin or MCP server is missing in Claude Code | Restart Claude Code (for Codex, see [below](#codex)). Then `loadout check` lists what is missing and how to fix it. Enabled plugins install at the next Claude Code start. |
| loadout skills or hooks are missing in a session that started before an update | Run `/reload-plugins` (loadout reminds you once per session), or start a new session. |

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
| `adopt --apply` exits with code 2 | Either it was run without a terminal: add `--yes` (adopt's default groups remove, migrate and scope-down, plus moving plaintext secrets, without asking), `--groups remove,migrate,...` or `--own NAME=CHOICE,...`. Or the `--own` input was wrong: the message names the problem and nothing changed. |
| `loadout: no unmanaged item named 'X' (see: loadout configure own --all)` | Use the name exactly as `loadout configure own --all` prints it. A hook is `Event:matcher` (`Stop:` without matcher). |
| `hook 'X' matches N hooks; pick one: ...` or `'X' matches several kinds` | Add `#n` to the hook name as the message shows, or write `<kind>:<name>`. See [hook names](../reference/hooks.md#naming-hooks-of-your-own-tools). |
| `loadout configure set own` exits with code 1 and prints `skipped:` or `failed:` | Nothing was recorded for that item. The line says why. Typical causes: a secret or private file (see [Secret guard](your-own-tools.md#secret-guard)), a name that already exists in your personal layer with different content, or a file that could not be written. Fix it and run the command again. |
| I left a tool and want to be asked about it again | `loadout configure own --all` lists the left ones. Decide again with `loadout configure set own NAME CHOICE`, or delete its entry in `~/.claude/.loadout/own-decisions.json`. |
| `loadout check` warns "own tools" | Some tools are not managed by loadout. Decide with `loadout adopt --apply` or `loadout configure own`. See [Handle your own tools](your-own-tools.md). |
| A global skill or hook script is missing on another machine | Commit and push the personal layer on the first machine. The other machine links them after its daily pull (or `loadout bootstrap`). See [Sync to other machines](your-own-tools.md#sync-to-other-machines). |

## Codex

Only if Codex is on ([Use loadout with Codex](codex.md)). `loadout check` names each of these.

| Symptom | Fix |
|---|---|
| No loadout session notice, no type check after edits in Codex; `loadout check` shows `Codex hooks` | Codex runs plugin hooks only after you approve them. Start `codex`, run `/hooks` and approve loadout's hooks. You need to do it again after they change. loadout never approves them for you ([Hooks](../reference/hooks.md)). |
| The repo's `.codex/config.toml` servers or plugin switches have no effect | Codex reads that file only in a trusted project. Start `codex` in the repo once and accept the trust question. |
| Codex says "Serena is not available" | Codex loads MCP tools on demand. Ask for them by name ("use Serena's find_symbol"). See [what stays different](codex.md#what-stays-different). |
| Codex ignores the rules and your `me.md` (`loadout check` warns `Codex instructions`) | `AGENTS.override.md` in the Codex folder (`~/.codex`, or `$CODEX_HOME`) shadows `AGENTS.md`, where loadout's block is. Merge the block into the override file or remove the override. |
| `plugin NAME@MARKET: no Codex route (its marketplace is not on GitHub)` | Codex gets plugins only from GitHub marketplaces. The plugin keeps working in Claude Code; Codex does without it. |
| An MCP server waits for a login in Codex | Run `codex mcp login NAME`. For Context7 the login is optional ([details](codex.md#what-stays-different)). |
| `MCP server "x" only in Claude Code` (or `only in Codex`) in the check or the session notice | You added it in one agent only. Record it with `loadout adopt` so both get it ([Handle your own tools](your-own-tools.md#tools-only-codex-has)). |

## Windows

| Symptom | Fix |
|---|---|
| Links were copied instead of linked | Enable Developer Mode (Settings, For developers) and re-run bootstrap, which switches back to links. Copies still work and are refreshed after each daily sync. Edit the source in your personal layer, not the copy: an edited copy is moved into a backup on the next refresh (the session notice names it). See [Links and copies](../reference/personal-layer.md#links-and-copies). |
| "cannot take JSON arguments (Windows .cmd shim)" | The npm-installed `claude.cmd` cannot receive JSON safely, so loadout changes nothing for that server. Best fix: install the native `claude.exe` and re-run. Otherwise open the private `manual-commands.txt` (path printed): with Claude Code closed, add the JSON block it shows under `"mcpServers"` in `%USERPROFILE%\.claude.json` (the file also has the macOS/Linux shell form). |
| `.\bootstrap.ps1` is refused ("running scripts is disabled on this system"), or secrets in `secrets.env` are not seen | PowerShell's default execution policy on Windows clients is `Restricted`: no script runs, neither `bootstrap.ps1` nor your PowerShell profiles, where bootstrap writes the secrets loader. Run bootstrap with `powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap.ps1 --install`, which bypasses the policy for that one process. For the profiles, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. Bootstrap detects `Restricted` and prints that command, but does not change the policy itself (`bootstrap.POLICY_NOTE`). |
| `loadout check` shows a `WSL` warning | Follow the fix it prints. [Use loadout on Windows with WSL 2](wsl.md) explains each one. |
| A hook script is not found | Claude Code runs hook commands through Git Bash. Use forward slashes (`C:/Users/me/x.sh`) or quotes. |

## Secrets

| Symptom | Fix |
|---|---|
| An MCP server does not see a key from `secrets.env` | Bootstrap adds a line to your shell startup file that loads `~/.config/loadout/secrets.env`. It only reaches an agent (Claude Code or Codex) started from a shell that read that file: open a new terminal and start it from there. |

## Cost

| Symptom | Fix |
|---|---|
| Context or token use is high | Heavy tools are per-project, and rtk compresses command output. Check with `/context` in Claude Code. Turn off an add-on you do not use with `loadout configure set plugin ID off`. |
