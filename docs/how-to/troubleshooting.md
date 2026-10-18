# Troubleshooting

Start with `loadout check`. It is read-only, names what is wrong and prints the fix. It prints `Health check: N of M OK` and then only the problems (`loadout check --verbose` lists every check as `ok`, `warn` or `FAIL`); see [loadout check](../reference/cli.md#loadout-check) for what it tests. On WSL, see also [WSL](wsl.md).

## Install and PATH

| Symptom | Fix |
|---|---|
| `loadout` or `claude` not found right after bootstrap | Open a new terminal. Bootstrap added `~/.local/bin` and the mise shims to your profile (block `# loadout PATH`); Windows: your user PATH, which also gets npm's global folder (wherever `npm prefix -g` points) and codebase-memory-mcp's folder. |
| `note: /home/you/.local/bin can be written by other users (mode 0775)` after a failed install (with your path and mode) | Some installers, codebase-memory-mcp's among them, refuse to put a program into a folder that other users can write to. Debian and Ubuntu create folders like that by default (umask 002). Run `chmod go-w ~/.local/bin`, then run bootstrap again. Bootstrap creates the folder without group write access itself, so this only happens when it already existed. |
| `missing node: not installed because mise failed to install` | mise failed to install; see the line above it. Fix that, then re-run bootstrap. |
| `npm error code EACCES` when installing pyright / typescript-language-server / playwright-cli | Your global npm prefix is root-owned (for example `/usr`). Either `npm config set prefix ~/.local` (then re-run `loadout bootstrap --install`), or install them with your version manager, for example `mise use -g npm:pyright npm:typescript-language-server`. |
| `loadout needs Python 3.11 or newer (found 3.X). Re-run bootstrap (it gets one through uv) or install it yourself.` | Re-run bootstrap (it installs uv, which provides Python), or install Python 3.11 or newer yourself (on Windows from python.org or `winget install Python.Python.3.12`). |
| `loadout needs Python 3.11 or newer, or uv, on PATH` | The launcher found neither. Re-run bootstrap (it installs uv). |
| A loadout hook acts on old state (for example the execution advisor asks again for a plan you already marked), or `loadout check` warns `loadout plugin (...)` | The agent runs an old copy of the loadout plugin. Run `loadout update --yes`, then `/reload-plugins` in Claude Code; in Codex, approve the changed hooks in `/hooks`. |
| Agents still grep instead of using Serena or the code graph | Run `loadout usage` (or `/loadout:usage` for a short report) to see how often each tool was used, and `loadout check` to see that the MCP servers run. In Codex, ask for the tool by name ("use Serena's find_symbol"). |
| `could not install uv (offline?). Install it from https://docs.astral.sh/uv/ and run this again.` | Bootstrap could not download uv. Check your network, or install uv from the linked page, then run bootstrap again. |
| `could not get Python 3.11 or newer through uv (offline?). Check your connection and run this again.` | uv could not find or download a Python for loadout. Check your network and run the command again; installing Python 3.11 or newer yourself also works. |
| `loadout needs curl to download uv. Install it, then run this again:` | Install curl (Linux: `sudo apt install curl`), then run bootstrap again. |
| A required tool is missing | Re-run `./bootstrap.sh --install` (Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap.ps1 --install`). `loadout check` shows manual install steps for what it cannot install, for example rtk on native Windows. |
| No session notices, or the daily sync never runs | `loadout` must be on the `PATH` that the agent's hooks see (Claude Code, or Codex after you approved the hooks). The plugin's hook runner exits 0 silently when the command is missing (`plugins/loadout/hooks/run.sh`). Add `~/.local/bin` to the `PATH` of the environment the agent starts from, then restart it. |
| A plugin or MCP server is missing in Claude Code | Restart Claude Code (for Codex, see [below](#codex)). Then `loadout check` lists what is missing and how to fix it. Enabled plugins install at the next Claude Code start. |
| loadout skills or hooks are missing in a session that started before an update | Run `/reload-plugins` (loadout reminds you once per session), or start a new session. |
| `Personal layer  clone failed` | Bootstrap could not clone your personal repo; the next line names git's error and how to get access (`gh auth login` and `gh auth setup-git`, or an SSH URL). Fix it and run bootstrap again with the same `--personal URL`: nothing was created in its place. |
| `--personal: give \`new\` or the git URL of your personal layer` | The value after `--personal` is empty or starts with `-` (a flag that lost its value). Pass `--personal new` or the URL. Nothing changed. |
| A line that starts with `--answers:` | The answers file has a problem; the line names the key. Fix it and run bootstrap again: it stops before it changes anything. The format is in [Set loadout up from inside an agent](install-with-an-agent.md#3-show-the-answers-file). For `looks like a secret`, remove the token or password from the file: secrets go in `secrets.env`, never in the personal layer. |
| `--personal and --answers: not used` (or one of them) | A personal layer already exists, or bootstrap cloned yours, so there was nothing new to create. Your layer keeps its own answers; change them with `loadout configure prefs`. |

## Settings

| Symptom | Fix |
|---|---|
| `invalid JSON in .../settings.json` | Fix the syntax error at the reported position, then run `loadout apply-settings`. |
| "settings drift" warning | Something changed a kit-managed value. Run `loadout apply-settings`, or put your preferred value in your personal `settings.json`. See [settings merge](../reference/settings-merge.md). |
| `link rules/personal` is `FAIL` | `<personal layer>/rules` does not exist, so the link was not made. Create the personal layer (`loadout bootstrap`). |

## Undo

| Symptom | Fix |
|---|---|
| Something went wrong after adopt | `loadout restore` lists the recent backups by number, shows what one puts back and asks; pick the adopt one by its command and age. Adopt prints the path itself only with `--verbose`. See [Undo what loadout changed](undo-and-restore.md). |

## Your own tools

| Symptom | Fix |
|---|---|
| `adopt --apply` exits with code 2 | Either it was run without a terminal: add `--yes` (adopt's default groups remove, migrate and scope-down, plus moving plaintext secrets, without asking), `--groups remove,migrate,...` or `--own NAME=CHOICE,...`. Or the `--own` input was wrong: the message names the problem and nothing changed. |
| `loadout: no unmanaged item named 'X' (see: loadout configure own --all)` | Use the name exactly as `loadout configure own --all` prints it. A hook is `Event:matcher` (`Stop:` without matcher). |
| `hook 'X' matches N hooks; pick one: ...` or `'X' matches several kinds` | Add `#n` to the hook name as the message shows, or write `<kind>:<name>`. See [hook names](../reference/hooks.md#naming-hooks-of-your-own-tools). |
| `loadout configure set own` exits with code 1 and prints `skipped:` or `failed:` | Nothing was recorded for that item. The line says why. Typical causes: a secret or private file (see [Secret guard](your-own-tools.md#secret-guard)), a name that already exists in your personal layer with different content, or a file that could not be written. Fix it and run the command again. |
| I left a tool and want to be asked about it again | See [Be asked again about a left item](your-own-tools.md#be-asked-again-about-a-left-item). |
| `loadout check` warns "own tools" | Some tools are not managed by loadout. Decide with `loadout adopt --apply` or `loadout configure own`. See [Handle your own tools](your-own-tools.md). |
| `loadout profile` prints `skill NAME: … is not a link to …, left as is` | The repo has two different skills of that name, one in `.claude/skills` and one in `.agents/skills`; each agent uses its own. Keep one: delete or rename the other (use git, it is a repo file), then run `loadout profile` again to link it for the other agent. |
| `loadout profile` prints `skills not linked: … is a link` or `… leads outside …, not linked` | loadout links repo skills only between plain folders inside the repo, because a link that leads elsewhere is broken in every other clone. Replace the linked `.claude`, `.agents` or skills folder with a plain folder (or copy the skill into the repo), then run it again ([profile-format](../reference/profile-format.md#skills)). |
| `loadout profile` lists `.mcp.json` or `.claude/settings.json` as not written because the repo is for Codex only | Expected: a repo gets only the files of its agents. To add Claude Code, run `loadout init --agents claude,codex` and then `loadout profile NAME` again ([`.loadout.json`](../reference/cli.md#loadoutjson), [ADR 0030](../adr/0030-repo-files-follow-the-repos-agents.md)). |
| The same, because Claude Code is off for you (a repo without `.loadout.json`) | Turn it on (`loadout configure set target claude on`), or name the repo's agents with `loadout init --agents claude,codex`; then run `loadout profile NAME` again. |
| `kept the repo's values (run it again with --take-profile to use the profile's)` | Someone changed entries the profile set, and loadout kept their values. `loadout explain FILE` shows which entries came from which profile and which were changed. To use the profile's values, run `loadout profile NAME --take-profile` ([three-way merge](../reference/profile-format.md#what-applying-a-profile-does)). |
| `.loadout.json: …` and exit 1 | The repo's `.loadout.json` is invalid; nothing was changed. The message names the reason: fix the file, then run the command again. |
| `manage is false in .loadout.json: nothing written` | The repo switched loadout off. Set `"manage"` back to `true` in `.loadout.json` (or remove the key) to let loadout write there. |
| `no terminal: nothing written` | `init`, `profile` and `new skill --to repo` write without a terminal only with `--yes`. Read the plan above the message, then run the same command with `--yes`. |
| A global skill or hook script is missing on another machine | Commit and push the personal layer on the first machine. The other machine links them after its daily pull (or `loadout bootstrap`). See [Sync to other machines](your-own-tools.md#sync-to-other-machines). |

## Codex

Only if Codex is on ([Use loadout with Codex](codex.md)). `loadout check` names each of these.

| Symptom | Fix |
|---|---|
| No loadout session notice, no type check after edits in Codex; `loadout check` shows `Codex hooks` | Codex runs plugin hooks only after you approve them. Start `codex`, run `/hooks` and approve loadout's hooks. You need to do it again after they change. loadout never approves them for you ([Hooks](../reference/hooks.md)). |
| The repo's `.codex/config.toml` servers or plugin switches have no effect | Codex reads that file only in a trusted project. Start `codex` in the repo once and accept the trust question. |
| Codex says "Serena is not available" | Codex loads MCP tools on demand. Ask for them by name ("use Serena's find_symbol"). See [what stays different](codex.md#what-stays-different). |
| Codex ignores the rules and your `me.md` (`loadout check` warns `Codex instructions`) | `AGENTS.override.md` in the Codex folder (`~/.codex`, or `$CODEX_HOME`) shadows `AGENTS.md`, where loadout's block is. Move what you need from `AGENTS.override.md` into `AGENTS.md`, then delete the override. |
| `plugin NAME@MARKET: no Codex route (its marketplace is not on GitHub)` | Codex gets plugins only from GitHub marketplaces. The plugin keeps working in Claude Code; Codex does without it. |
| An MCP server waits for a login in Codex | Run `codex mcp login NAME`. For Context7 the login is optional ([details](codex.md#what-stays-different)). |
| `MCP server "x" only in Claude Code` (or `only in Codex`) in the check or the session notice | You added it in one agent only. Record it with `loadout adopt` so both get it ([Handle your own tools](your-own-tools.md#tools-only-one-agent-has)). |
| `loadout check` warns `Codex Serena hooks: … add these yourself` | Your `~/.codex/hooks.json` is not in loadout's own format (other indentation, or mixed line endings), so loadout does not rewrite it. Add the listed `serena-hooks … --client=codex` entries by hand, or run `serena setup codex` ([Serena's hooks in Codex](../reference/hooks.md#serenas-hooks-in-codex)). |
| `mcp serena: left as is, config.toml already has a server of that name` | Your `[mcp_servers.serena]` does not start Serena (if it does, loadout uses it and says nothing). Rename that table if you want loadout's Serena; loadout never changes it. |

## VS Code

| Symptom | Fix |
|---|---|
| `VS Code (Codex)`: plugins do not load in VS Code's Codex extension | The extension loads no plugins and has no `/hooks`. Use the Codex CLI alongside VS Code ([VS Code](vscode.md#the-codex-cli-alongside-vs-code)). |
| `VS Code (Codex)`: its bundled Codex is older than 0.161 | Update the Codex extension in VS Code's Extensions view. |
| `VS Code (Claude Code, Windows window)` | That window reads `%USERPROFILE%\.claude`. Open repos with `code .` from WSL, or set loadout up on Windows too ([Windows and WSL](vscode.md#windows-and-wsl)). |
| `VS Code settings`: … does not parse | Fix the file's JSON in VS Code (Preferences: Open User Settings (JSON)); loadout reads it, never changes it. |
| `VS Code PATH` | An absolute command in the server entry, or the folder on PATH in `~/.vscode-server/server-env-setup` ([VS Code](vscode.md#mcp-servers-in-a-remote-wsl-window)). |
| `repo .mcp.json` | Register that server in local scope or as your user-level server ([VS Code](vscode.md#a-committed-mcpjson-with-your-own-path)). |

## Windows

| Symptom | Fix |
|---|---|
| Links were copied instead of linked | Enable Developer Mode (Settings, For developers) and re-run bootstrap, which switches back to links. Copies still work and are refreshed by bootstrap and when the daily sync pulls new commits. Edit the source in your personal layer, not the copy: an edited copy is moved into a backup on the next refresh (the session notice names it). See [Links and copies](../reference/personal-layer.md#links-and-copies). |
| A line that mentions "Windows .cmd shim", for example `not changed, this claude (a Windows .cmd shim) cannot take JSON arguments` | The npm-installed `claude.cmd` cannot receive JSON safely, so loadout changes nothing for that server. Best fix: install the native `claude.exe` and re-run. Otherwise open the private `manual-commands.txt` (path printed): with Claude Code closed, add the JSON block it shows under `"mcpServers"` in `%USERPROFILE%\.claude.json` (the file also has the macOS/Linux shell form). |
| `.\bootstrap.ps1` is refused ("running scripts is disabled on this system"), or secrets in `secrets.env` are not seen | PowerShell's default execution policy on Windows clients is `Restricted`: no script runs, neither `bootstrap.ps1` nor your PowerShell profiles, where bootstrap writes the secrets loader. Run bootstrap with `powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap.ps1 --install`, which bypasses the policy for that one process. For the profiles, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. Bootstrap detects `Restricted` and prints that command, but does not change the policy itself. |
| `loadout check` shows a `WSL` warning | Follow the fix it prints. [Use loadout on Windows with WSL 2](wsl.md) explains each one. |
| Bootstrap in WSL prints `Codex step skipped: …` | You chose Codex on Windows (`--codex-side windows` or answer 2), your only Codex is the Windows one, or `CODEX_HOME` points into Windows. Choose a side with `--codex-side wsl` (with `--install`, it installs Codex in WSL) or run `bootstrap.ps1` on Windows ([Codex in WSL](wsl.md#codex)). |
| `the codex on PATH is the Windows one` | You chose Codex in WSL, but `codex` still resolves to the Windows program. Re-run bootstrap with `--install`; it installs Codex in WSL. |
| `loadout check` in WSL warns `Codex (Windows side)` | You also use Codex on Windows, and loadout has not set it up there. Run `bootstrap.ps1` in PowerShell on Windows with the same personal layer. |
| `loadout check` in WSL warns `Codex home` | `CODEX_HOME` points into Windows, so both sides read one config. Unset it in WSL ([Codex in WSL](wsl.md#a-codex_home-that-points-into-windows)). |
| A hook script is not found | Claude Code runs hook commands through Git Bash. Use forward slashes (`C:/Users/me/x.sh`) or quotes. |
| `N skill links in .agents/skills are plain files in this checkout (Git without symlinks)` | Git checked the repo's skill links out as files (Windows without Developer Mode), so the agent does not see those skills. Best: use Codex in WSL with the repo in the Linux home ([WSL 2](wsl.md)). Otherwise turn on Windows Developer Mode, run `git config core.symlinks true` and the `git checkout -- "PATH" …` that loadout prints, which names only the broken links, so your other changes in the skill folders stay. loadout counts a file only when its content is exactly the link's target, and reports this in `loadout check`, `init` and `profile` and changes nothing. |

## Secrets

| Symptom | Fix |
|---|---|
| An MCP server does not see a key from `secrets.env` | Bootstrap adds a line to your shell startup file that loads `~/.config/loadout/secrets.env`. It only reaches an agent (Claude Code or Codex) started from a shell that read that file: open a new terminal and start it from there. |

## Cost

| Symptom | Fix |
|---|---|
| Context or token use is high | Heavy tools are per-project, and rtk compresses command output. Check with `/context` in Claude Code. Turn off an add-on you do not use with `loadout configure set plugin ID off`. |
