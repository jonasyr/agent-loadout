# Troubleshooting

Start with `loadout check`. It is read-only, names what is wrong and prints the fix. It prints `Health check: N of M OK` and then only the problems, each as `[warn] NAME: message` or `[FAIL] NAME: message` with a `fix:` line under it (`loadout check --verbose` lists every check). What each row tests: [loadout check](../reference/cli.md#loadout-check).

This page has one row per problem row that `loadout check` can show, grouped by area, plus the messages that bootstrap, `adopt`, `configure` and `profile` print. In the tables, `NAME:` is the row name and the text after it is the start of the message; `…` stands for names and paths that the real message fills in. When the printed fix and this page differ, this page says why.

## Install and PATH

These are bootstrap and launcher messages.

| Symptom | Fix |
|---|---|
| `loadout` or `claude` not found right after bootstrap | Open a new terminal. Bootstrap added `~/.local/bin` and the mise shims to your profile (block `# loadout PATH`); Windows: your user PATH, which also gets npm's global folder (wherever `npm prefix -g` points) and codebase-memory-mcp's folder. |
| `note: /home/you/.local/bin can be written by other users (mode 0775)` after a failed install (with your path and mode) | Some installers, codebase-memory-mcp's among them, refuse to put a program into a folder that other users can write to. Debian and Ubuntu create folders like that by default (umask 002). Run `chmod go-w ~/.local/bin`, then run bootstrap again. Bootstrap creates the folder without group write access itself, so this only happens when it already existed. |
| `missing node: not installed because mise failed to install` | mise failed to install; see the line above it. Fix that, then re-run bootstrap. |
| `npm error code EACCES` when installing pyright / typescript-language-server / playwright-cli | Your global npm prefix is root-owned (for example `/usr`, a system npm). Recommended: `npm config set prefix ~/.local`, then re-run `loadout bootstrap --install`; the tools land in `~/.local/bin`, which is already on your PATH. If you manage Node with a version manager, install them there instead, for example `mise use -g npm:pyright npm:typescript-language-server`. |
| `loadout needs Python 3.11 or newer (found 3.X). Re-run bootstrap (it gets one through uv) or install it yourself.` | Re-run bootstrap (it installs uv, which provides Python), or install Python 3.11 or newer yourself (on Windows from python.org or `winget install Python.Python.3.12`). |
| `loadout needs Python 3.11 or newer, or uv, on PATH` | The launcher found neither. Re-run bootstrap (it installs uv). |
| `could not install uv (offline?). Install it from https://docs.astral.sh/uv/ and run this again.` | Bootstrap could not download uv. Check your network, or install uv from the linked page, then run bootstrap again. |
| `could not get Python 3.11 or newer through uv (offline?). Check your connection and run this again.` | uv could not find or download a Python for loadout. Check your network and run the command again; installing Python 3.11 or newer yourself also works. |
| `loadout needs curl to download uv. Install it, then run this again:` | Install curl (Linux: `sudo apt install curl`), then run bootstrap again. |
| A required tool is missing | Re-run `./bootstrap.sh --install` (Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap.ps1 --install`). `loadout check` shows manual install steps for what it cannot install, for example rtk on native Windows. |
| No session notices, or the daily sync never runs | The sync and the notices start from a plugin hook. `loadout` must be on the `PATH` that the agent's hooks see (Claude Code, or Codex after you approved the hooks). The plugin's hook runner exits 0 silently when the command is missing (`plugins/loadout/hooks/run.sh`). Add `~/.local/bin` to the `PATH` of the environment the agent starts from, then restart it. With only VS Code's Codex extension (no Codex CLI) no plugin hook runs at all: install the Codex CLI next to it (`loadout bootstrap --install`) and approve the hooks there once ([VS Code](vscode.md#the-codex-cli-alongside-vs-code), [the daily sync](../reference/state-and-sync.md#the-daily-sync)). |
| `Personal layer  clone failed` | Bootstrap could not clone your personal repo; the next line names git's error and how to get access (`gh auth login` and `gh auth setup-git`, or an SSH URL). Fix it and run bootstrap again with the same `--personal URL`: nothing was created in its place. |
| `--personal: give \`new\` or the git URL of your personal layer` | The value after `--personal` is empty or starts with `-` (a flag that lost its value). Pass `--personal new` or the URL. Nothing changed. |
| A line that starts with `--answers:` | The answers file has a problem; the line names the key. Fix it and run bootstrap again: it stops before it changes anything. The format is in [Set loadout up from inside an agent](install-with-an-agent.md#3-show-the-answers-file). For `looks like a secret`, remove the token or password from the file: secrets go in `secrets.env`, never in the personal layer. |
| `--personal and --answers: not used` (or one of them) | A personal layer already exists, or bootstrap cloned yours, so there was nothing new to create. Your layer keeps its own answers; change them with `loadout configure prefs`. |
| `--without-codex-cli: not used; it applies only with VS Code's Codex extension and no Codex CLI on PATH` | Nothing to do. The flag only skips the Codex CLI install when VS Code's Codex extension can run Codex and no Codex CLI is on PATH; here a Codex CLI is already there, or there is no usable extension. |
| `Codex CLI  not installed (you use VS Code's Codex extension): …` | You declined the Codex CLI (or passed `--without-codex-cli`). loadout sets Codex up for the extension; what only the CLI adds is listed under "Still to do". Recommended: install it next to the extension later with `loadout bootstrap --install` ([VS Code](vscode.md#codex-in-vs-code-without-the-cli)). |
| `Claude Code CLI  not on PATH: loadout runs VS Code's Claude Code extension's own (…) for claude plugin and claude mcp; --install puts a claude on PATH for the terminal` | Expected when you use only the Claude Code extension: loadout's `claude` commands run the extension's own binary. For `claude` in a terminal, run `loadout bootstrap --install` ([VS Code](vscode.md#claude-code-in-vs-code-without-the-cli)). |

## Claude Code

Only if Claude Code is on.

| Symptom | Fix |
|---|---|
| `settings.json` is `FAIL` with `invalid JSON in …/settings.json` | Fix the syntax error at the reported position, then run `loadout apply-settings`. |
| `settings drift: …` | Something changed a kit-managed value. Run `loadout apply-settings`. To keep your own value instead, put it in your personal `settings.json`, as the fix line says. See [settings merge](../reference/settings-merge.md). |
| `plugins installed: …` (a list of plugin ids) | Enabled plugins that Claude Code has not installed yet. They install at the next Claude Code start; or run `loadout bootstrap`. |
| `plugins installed: invalid JSON …` (or `'plugins' is not an object`) | `~/.claude/plugins/installed_plugins.json` is broken. Fix its JSON syntax, then restart Claude Code. |
| `loadout plugin (Claude Code): the installed copy differs from the kit, so its hooks and skills may be old` (or a loadout hook acts on old state, for example the execution advisor asks again for a plan you already marked) | The agent runs an old copy of the loadout plugin. Run `loadout update --yes`, then `/reload-plugins` in Claude Code. |
| `loadout plugin (Claude Code, project …)` or `(Claude Code, local …)` | A copy installed for one project. `loadout update` refreshes only the user scope: in that project run `claude plugin update loadout@agent-loadout --scope project` (or `--scope local`), then `/reload-plugins`. |
| `duplicate NAME: the plugin and the connector … provide the same tools` | A plugin and a claude.ai connector give you the same tools twice. Keep one: disconnect the connector on claude.ai if you prefer the plugin, or `loadout configure set plugin NAME off` if you prefer the connector. |
| `binary claude: not on PATH; loadout runs VS Code's Claude Code extension's own (…)` | Expected with the extension only. For `claude` in a terminal and the extension's terminal mode: `loadout bootstrap --install` ([VS Code](vscode.md#claude-code-in-vs-code-without-the-cli)). |
| A plugin or MCP server is missing in Claude Code | Restart Claude Code (for Codex, see [below](#codex)). Then `loadout check` lists what is missing and how to fix it. Enabled plugins install at the next Claude Code start. |
| loadout skills or hooks are missing in a session that started before an update | Run `/reload-plugins` (loadout reminds you once per session), or start a new session. |
| Agents still grep instead of using Serena or the code graph | Run `loadout usage` (or `/loadout:usage` for a short report) to see how often each tool was used, and `loadout check` to see that the MCP servers run. In Codex, ask for the tool by name ("use Serena's find_symbol"). |

## Codex

Only if Codex is on ([Use loadout with Codex](codex.md)). "Extension mode" means VS Code's Codex extension with no Codex CLI on PATH; some fixes differ there.

| Symptom | Fix |
|---|---|
| `Codex: codex not found on PATH` | Install the Codex CLI (`loadout bootstrap --install`, or `mise use -g codex`), or turn Codex off: `loadout configure set target codex off`. |
| `Codex: codex X is too old; loadout needs 0.161 or newer (update it: mise upgrade codex)` (or `could not read codex --version`) | Run `mise upgrade codex` (or update Codex the way you installed it), then `loadout bootstrap`. |
| `Codex: VS Code's Codex extension runs codex X; loadout needs 0.161 or newer …` (or `… own codex gives no version, so loadout does not use it …`) | Extension mode with an extension whose Codex loadout cannot use. Update the extension in VS Code's Extensions view. Recommended: also install the Codex CLI (`loadout bootstrap --install`). |
| `Codex: the codex on PATH is the Windows one (…)` or `Codex: CODEX_HOME points into Windows (…)` | WSL only; see [WSL](#wsl). |
| `Codex plugin: loadout plugin not installed in Codex` (FAIL) | Run `loadout bootstrap`. |
| `Codex plugin: not installed: VS Code's Codex extension loads none …` | Extension mode: plugins need the Codex CLI. Install it with `loadout bootstrap --install` ([VS Code](vscode.md#the-codex-cli-alongside-vs-code)). |
| `Codex instructions: ~/.codex/AGENTS.md lacks loadout's current block` (FAIL) | Run `loadout bootstrap`. If the markers are broken, bootstrap prints `skipped …: its loadout markers are unbalanced or duplicated; fix them by hand`: keep one `<!-- loadout:start -->` … `<!-- loadout:end -->` pair (or delete both), then run it again. |
| `Codex instructions: AGENTS.override.md shadows AGENTS.md, so Codex ignores loadout's block` (Codex ignores the rules and your `me.md`) | `AGENTS.override.md` in the Codex folder (`~/.codex`, or `$CODEX_HOME`) shadows `AGENTS.md`, where loadout's block is. Move what you need from `AGENTS.override.md` into `AGENTS.md`, then delete the override. |
| `Codex config: config.toml: changes pending` | loadout has entries to write. Run `loadout bootstrap`. |
| `Codex config: mcp NAME: left as is, config.toml already has a server of that name` | Your own `[mcp_servers.NAME]` table has the name loadout wants (for `serena`: your table does not start Serena; if it does, loadout uses it and says nothing). loadout never changes it. To get loadout's, rename or remove your table, then run `loadout bootstrap`; to keep yours, ignore the warning. |
| `Codex config: mcp NAME: left as is in config.toml (changed by you); loadout no longer manages it` (or `(it has sub-tables)`) | You edited a section loadout wrote, so it is yours now. Run `loadout bootstrap` once: it records that, and this warning goes. The section stays as you left it. While loadout still wants a server of that name, the row then reads `mcp NAME: left as is, config.toml already has a server of that name` (the row above). |
| `Codex config: KEY: left as is in config.toml (your value)` | Your value for a key loadout sets (for example `model_reasoning_effort`). Keep it (the warning stays), or delete your line and run `loadout bootstrap` to take loadout's value. |
| `Codex config: skipped …: it does not parse now (…)`, `… the result would not parse …` or `… the edit would change entries loadout does not own; nothing written` | loadout wrote nothing to `~/.codex/config.toml`. Fix the TOML syntax (or the entry the message names) by hand, then run `loadout bootstrap`. |
| `Codex Serena hooks: …/hooks.json: Serena hooks pending` | Run `loadout bootstrap`, then approve the hooks in `/hooks`. |
| `Codex Serena hooks: …/hooks.json: Serena hooks missing, add these yourself (loadout does not rewrite a file in another format): …` | Your `~/.codex/hooks.json` is not in loadout's own format (other indentation, or mixed line endings), so loadout does not rewrite it. Recommended: add the listed `serena-hooks … --client=codex` entries by hand, so the file keeps your format; `serena setup codex` is the other way ([Serena's hooks in Codex](../reference/hooks.md#serenas-hooks-in-codex)). |
| `Codex Serena hooks: …/config.toml: Serena hooks missing, add these yourself to its [hooks] (loadout creates no hooks.json next to inline hooks): …` | You keep hooks inline in `~/.codex/config.toml`. Add the listed entries to its `[hooks]`, not to a `hooks.json` (the printed fix line names `hooks.json`; the message is right). |
| `Codex Serena hooks: …: loadout's old Serena hooks are still in it; remove them yourself` | A `hooks.json` in another format still holds entries loadout wrote and no longer wants. Delete them by hand (the printed fix, `loadout bootstrap`, cannot rewrite that file). |
| `Codex Serena hooks: skipped …: it is not valid JSON …`, `… it has no hooks object …` or `… is not a list of hook groups …` | Fix `~/.codex/hooks.json` so it is a JSON object with a `hooks` object whose events hold lists, then run `loadout bootstrap`. |
| `Codex plugins: no Codex route for …`, or `plugin NAME@MARKET: no Codex route (its marketplace is not on GitHub)` | Codex gets plugins only from GitHub marketplaces. The plugin keeps working in Claude Code; Codex does without it. No fix needed. |
| `Codex hooks: loadout's hooks are not approved yet` (or `… changed since you approved them`): no loadout session notice, no type check after edits | Codex runs plugin hooks only after you approve them. Start `codex`, run `/hooks` and approve loadout's hooks; again after they change. loadout never approves them for you ([Hooks](../reference/hooks.md)). In extension mode the fix line says to install the Codex CLI: VS Code's Codex extension has no `/hooks`, so install it (`loadout bootstrap --install`), run `codex` once in VS Code's terminal and approve them there ([VS Code](vscode.md#the-codex-cli-alongside-vs-code)). |
| `Codex logins: waiting for a login: …` (an MCP server waits for a login) | Run `codex mcp login NAME` for each. In extension mode: in VS Code's Codex extension, gear, MCP servers, Authenticate. For Context7 the login is optional ([details](codex.md#what-stays-different)). |
| `Codex drift: MCP server "x" only in Claude Code` (or `only in Codex`, or `skill "x" only in …`), also in the session notice | You added it in one agent only. Record it with `loadout adopt` so both get it ([Handle your own tools](your-own-tools.md#tools-only-one-agent-has)). |
| `loadout plugin (Codex): the installed copy differs from the kit, …` | Run `loadout update --yes`, then approve the changed hooks in Codex's `/hooks`. |
| `binary codex: not on PATH; VS Code's Codex extension runs its own` | Expected in extension mode. Recommended: install the Codex CLI for `/hooks` and plugins, `loadout bootstrap --install` ([VS Code](vscode.md#codex-in-vs-code-without-the-cli)). |
| The repo's `.codex/config.toml` servers or plugin switches have no effect | Codex reads that file only in a trusted project. Start `codex` in the repo once and accept the trust question. |
| Codex says "Serena is not available" | Codex loads MCP tools on demand. Ask for them by name ("use Serena's find_symbol"). See [what stays different](codex.md#what-stays-different). |

## VS Code

Rows are named `VS Code (Codex)`, `VS Code (Claude Code)`, with `, Windows window` or `, Remote-WSL window` added when seen from WSL. Background: [Use loadout with VS Code](vscode.md).

| Symptom | Fix |
|---|---|
| `VS Code (Codex): plugins do not load in VS Code's Codex extension …, and it has no /hooks …` | No Codex CLI on this side. Recommended: install it next to the extension (`loadout bootstrap --install`), run `codex` once in VS Code's terminal and approve the hooks in `/hooks`; use it there when you need a plugin skill ([VS Code](vscode.md#the-codex-cli-alongside-vs-code)). |
| `VS Code (Codex): its bundled Codex is X; loadout's Codex setup needs 0.161 or newer` | Update the Codex extension in VS Code's Extensions view. |
| `VS Code (Codex): the extension has no bundled Codex for this platform` | Reinstall the Codex extension in VS Code. |
| `VS Code (Codex): chatgpt.cliExecutable names …, which is not a file it can run, …` | Your `chatgpt.cliExecutable` setting points at a missing program. Point it at an installed `codex`, or remove the setting from VS Code's user settings. |
| `VS Code (Codex): the Codex that chatgpt.cliExecutable names (…) is X; loadout's Codex setup needs 0.161 or newer` | Update that Codex, or remove `chatgpt.cliExecutable` so the extension runs its own. |
| `VS Code (Codex, Windows window): the Codex extension in a Windows window reads …, which loadout has not set up` | WSL with Codex on the Windows side of VS Code. Recommended: open repos with `code .` from WSL (a Remote-WSL window). Or switch the extension to WSL (`loadout bootstrap --codex-side wsl --vscode-wsl`), or run `bootstrap.ps1` on Windows ([Codex in WSL](wsl.md#codex)). |
| `VS Code (Codex, Remote-WSL window): the Codex extension in a Remote-WSL window reads the WSL ~/.codex, which loadout does not set up while your Codex runs on Windows` | You chose Codex on Windows. Open the repo in a Windows window, or set Codex up in WSL with `loadout bootstrap --codex-side wsl` ([Codex in WSL](wsl.md#codex)). |
| `VS Code (Claude Code, Windows window): the Claude Code extension in a Windows window reads …, which loadout in WSL does not set up` | That window reads `%USERPROFILE%\.claude`. Recommended: open repos with `code .` from WSL (a Remote-WSL window); if you use only Remote-WSL windows, uninstall the extension from VS Code on Windows (its Remote-WSL copy stays). Or set loadout up on Windows too with `bootstrap.ps1` ([Windows and WSL](vscode.md#windows-and-wsl)). |
| `VS Code (Claude Code): terminal mode (claudeCode.useTerminal) starts the claude on PATH, and no claude is on PATH` | Install Claude Code (`loadout bootstrap --install`; on native Windows `bootstrap.ps1 --install`), or turn `claudeCode.useTerminal` off. |
| `VS Code (Claude Code, Windows window): terminal mode (claudeCode.useTerminal) starts the claude on the Windows PATH, and it may not find one …` | Install Claude Code on Windows (`bootstrap.ps1 --install`), or turn `claudeCode.useTerminal` off. |
| `VS Code (Claude Code): claudeCode.claudeProcessWrapper names …, which is not a file it can run, …` | Point the setting at an installed `claude`, or remove it from VS Code's user settings (in a Remote-WSL window: VS Code's remote settings for WSL, Preferences: Open Remote Settings). |
| `VS Code (Claude Code): the extension has no bundled Claude Code for this platform, so it cannot start Claude` | Set `claudeCode.claudeProcessWrapper` in VS Code's user settings (in a Remote-WSL window: VS Code's remote settings for WSL, Preferences: Open Remote Settings) to an installed `claude` (`loadout bootstrap --install` installs one), or reinstall the extension. If the message adds that a VS Code profile sets the wrapper, check that profile. |
| `VS Code settings: … does not parse, so loadout cannot read the settings that matter there` | Fix the file's JSON in VS Code. The row names the file and how to open it: Preferences: Open User Settings (JSON) for your user settings (for a file under `profiles/`, switch to that profile first), Open Remote Settings (JSON) for a Remote-WSL server's settings, Open Workspace Settings (JSON) for the folder's `.vscode/settings.json`. loadout reads it, never changes it. |
| `VS Code PATH: in a Remote-WSL window the Codex extension may not find the command of the MCP servers …` | Recommended: `loadout bootstrap --vscode-path` (puts loadout's tool folders on PATH in `~/.vscode-server/server-env-setup`), then restart VS Code's WSL server: close every Remote-WSL window, run `wsl --shutdown` in Windows (it stops every WSL distro), reopen the folder. For a command outside those folders, give the server an absolute command ([VS Code](vscode.md#mcp-servers-in-a-remote-wsl-window)). |
| `VS Code PATH: the … extension may not find the command of the MCP servers …: it is not on your shell's PATH` | Install the command, or give the server entry an absolute command. `loadout check` reports with the PATH of the terminal it runs in; a plain terminal (no activated virtualenv) is the closest to what VS Code inherits. |
| `VS Code: the Codex extension runs Codex on Windows, not the Codex in WSL` | WSL with Codex in WSL. Recommended: open repos with `code .` from WSL (a Remote-WSL window). For a Windows window you open anyway: `loadout bootstrap --codex-side wsl --vscode-wsl`, or tick `chatgpt.runCodexInWindowsSubsystemForLinux` in VS Code's settings on Windows ([Windows and WSL](vscode.md#windows-and-wsl)). |
| `VS Code: … sets chatgpt.runCodexInWindowsSubsystemForLinux to false, …` (a folder's settings) or `VS Code: the VS Code profile settings … set chatgpt.runCodexInWindowsSubsystemForLinux to false: …` (a profile's) | That folder's or profile's settings win over your user settings. Set it to true there or remove it; loadout edits neither ([Windows and WSL](vscode.md#windows-and-wsl)). |
| Bootstrap prints `VS Code  Windows home not found; …`, `VS Code  VS Code settings not found …`, `… give chatgpt.runCodexInWindowsSubsystemForLinux a value other than true or false …`, `… are not an object …` or `could not change VS Code settings …` | `--vscode-wsl` could not set the switch and changed nothing. Do it by hand as the line says: in VS Code on Windows, Settings, search `chatgpt.runCodexInWindowsSubsystemForLinux`, tick it. |
| Bootstrap prints `VS Code  --vscode-wsl: the Codex step in WSL was skipped, so nothing changed` | The Codex side in WSL was not chosen (you picked Windows, or no side), so the switch was not set. To set it, choose the WSL side: `loadout bootstrap --codex-side wsl --vscode-wsl` ([Codex in WSL](wsl.md#codex)). |
| Bootstrap prints `VS Code  --vscode-wsl: Codex is not set up in WSL in this run; nothing changed` | `--vscode-wsl` acts only in WSL with Codex on. Run it in WSL, with Codex in your agent choice (`loadout configure set target codex on`, or `--agents codex` / `claude,codex`). |

## WSL

`loadout check` in WSL shows `WSL 2` (or `WSL 1`) and one `WSL` row per problem. Background: [Use loadout on Windows with WSL 2](wsl.md).

| Symptom | Fix |
|---|---|
| `WSL: WSL 1: Claude Code's sandbox needs WSL 2, …` | In PowerShell: `wsl --set-version <distro> 2` ([WSL 2](wsl.md#1-use-wsl-2-not-wsl-1)). |
| `WSL: the kit (…) is on the Windows filesystem …` (or `the personal layer (…)`) | Move it into the Linux home, for example `~/code/...`, then re-run `./bootstrap.sh` there (the installed links point into it). |
| `WSL: the current folder (…) is on the Windows filesystem …` | Move the repo into the Linux home, for example `~/code/...` ([Keep repos in the Linux filesystem](wsl.md#4-keep-repos-in-the-linux-filesystem)). |
| `WSL: TOOL resolves to the Windows program …` | Install the tool inside WSL and put its folder first in PATH, or set `appendWindowsPath = false` in `/etc/wsl.conf` ([Linux binaries](wsl.md#5-check-that-the-tools-are-linux-binaries)). |
| `WSL: sandbox packages missing: …` | `sudo apt-get install` the packages it names ([sandbox packages](wsl.md#6-install-the-sandbox-packages-optional)). |
| `Codex: the codex on PATH is the Windows one (…)` (also in bootstrap) | You chose Codex in WSL, but `codex` still resolves to the Windows program. Re-run bootstrap with `--install`; it installs Codex in WSL. |
| `Codex home: CODEX_HOME points into Windows: …` (or `Codex: CODEX_HOME points into Windows (…)`) | Both sides read one config. Unset `CODEX_HOME` in WSL ([Codex in WSL](wsl.md#a-codex_home-that-points-into-windows)). |
| `Codex (Windows side): you use Codex on Windows too, and loadout has not set it up there` | Run `bootstrap.ps1` in PowerShell on Windows with the same personal layer ([Codex on both sides](wsl.md#codex-on-both-sides)). |
| Bootstrap in WSL prints `Codex step skipped: …` | You chose Codex on Windows (`--codex-side windows` or answer 2), your only Codex is the Windows one, or `CODEX_HOME` points into Windows. Choose a side with `--codex-side wsl` (with `--install`, it installs Codex in WSL) or run `bootstrap.ps1` on Windows ([Codex in WSL](wsl.md#codex)). |

The VS Code rows for Windows and Remote-WSL windows are in [VS Code](#vs-code).

## Windows

Native Windows (`bootstrap.ps1`), and repos checked out by a Git without symlinks.

| Symptom | Fix |
|---|---|
| Links were copied instead of linked | Enable Developer Mode (Settings, For developers) and re-run bootstrap, which switches back to links. Copies still work and are refreshed by bootstrap and when the daily sync pulls new commits. Edit the source in your personal layer, not the copy: an edited copy is moved into a backup on the next refresh (the session notice names it). See [Links and copies](../reference/personal-layer.md#links-and-copies). |
| A line that mentions "Windows .cmd shim", for example `not changed, this claude (a Windows .cmd shim) cannot take JSON arguments` | The npm-installed `claude.cmd` cannot receive JSON safely, so loadout changes nothing for that server. Best fix: install the native `claude.exe` and re-run. Otherwise open the private `manual-commands.txt` (path printed): with Claude Code closed, add the JSON block it shows under `"mcpServers"` in `%USERPROFILE%\.claude.json` (the file also has the macOS/Linux shell form). |
| `.\bootstrap.ps1` is refused ("running scripts is disabled on this system"), or secrets in `secrets.env` are not seen | PowerShell's default execution policy on Windows clients is `Restricted`: no script runs, neither `bootstrap.ps1` nor your PowerShell profiles, where bootstrap writes the secrets loader. Run bootstrap with `powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap.ps1 --install`, which bypasses the policy for that one process. For the profiles, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. Bootstrap detects `Restricted` and prints that command, but does not change the policy itself. |
| A hook script is not found | Claude Code runs hook commands through Git Bash. Use forward slashes (`C:/Users/me/x.sh`) or quotes. |
| `repo skill links: …: N skill links in .agents/skills are plain files in this checkout (Git without symlinks), …` (also printed by `init` and `profile`) | Git checked the repo's skill links out as files (Windows without Developer Mode), so the agent does not see those skills. Best: use Codex in WSL with the repo in the Linux home ([WSL 2](wsl.md)). Otherwise turn on Windows Developer Mode, run `git config core.symlinks true` and the `git checkout -- "PATH" …` that loadout prints, which names only the broken links, so your other changes in the skill folders stay. loadout counts a file only when its content is exactly the link's target, and changes nothing. |

## MCP servers and tools

| Symptom | Fix |
|---|---|
| `binary NAME: not on PATH` (FAIL for a required tool, warn for an optional one) | Run `loadout bootstrap --install`. For a tool it cannot install (git, rtk on native Windows), the fix line gives the manual step. The VS Code variants of `binary claude` and `binary codex` are under [Claude Code](#claude-code) and [Codex](#codex). |
| `MCP servers on PATH: serena` (or `codebase-memory-mcp`) | They are installed, but a new terminal's PATH does not find them, so Claude Code cannot start them. Open a new terminal; if it stays, add the folder the fix line names to PATH. |
| `gh auth: not logged in` | Run `gh auth login`, then `gh auth setup-git`. Needed for a private personal repo over HTTPS. |
| An MCP server does not see a key from `secrets.env` | Bootstrap adds a line to your shell startup file that loads `~/.config/loadout/secrets.env`. It only reaches an agent (Claude Code or Codex) started from a shell that read that file: open a new terminal and start it from there. |

`VS Code PATH` is under [VS Code](#vs-code), `repo .mcp.json` under [Repos](#repos).

## Personal layer and state

| Symptom | Fix |
|---|---|
| `link rules/personal` is `FAIL` | `<personal layer>/rules` does not exist, so the link was not made. Create the personal layer (`loadout bootstrap`). |
| `link DIR/NAME: … does not point to …` (FAIL) | A link loadout made (rules, skills, hook scripts) is missing or points elsewhere. Run `loadout bootstrap`. |
| `skills.json: invalid JSON …` | Fix the JSON syntax in your personal `skills.json` (the path is printed). |
| `secrets.env: … missing` | Run `loadout bootstrap`; it creates the file. |
| `secrets.env: permissions too open` | Run `chmod 600` on the file (the fix line has the path). |
| `personal repo clean: uncommitted changes (daily sync paused)` (or `kit repo clean`) | The daily sync skips a checkout with uncommitted changes, so it pulls nothing there. Commit (and push) or discard the changes in the folder the fix line names. |
| `loadout state: kept in ~/.claude because both places have it: …` | The move out of `~/.claude` found a different copy in both places. Compare each named entry with the state folder (path in the fix line), keep what you need, and delete the old ones by hand ([The move out of ~/.claude](../reference/state-and-sync.md#the-move-out-of-claude)). |
| `loadout state: not everything was copied out of ~/.claude yet` | Run any loadout command. If the row stays, move the entry it names by hand. |
| `loadout state: cannot read the old folder in ~/.claude (…)` | Check that folder's permissions, then run loadout again. |
| `own tools: N tool(s) not managed by loadout (they stay on this machine only)` | Decide with `loadout adopt --apply` or `loadout configure own`. See [Handle your own tools](your-own-tools.md). If the row names `invalid JSON`, fix the file it names first. |
| A global skill or hook script is missing on another machine | Commit and push the personal layer on the first machine. The other machine links them after its daily pull (or `loadout bootstrap`). See [Sync to other machines](your-own-tools.md#sync-to-other-machines). |
| Something went wrong after adopt | `loadout restore` lists the recent backups by number, shows what one puts back and asks; pick the adopt one by its command and age. Adopt prints the path itself only with `--verbose`. See [Undo what loadout changed](undo-and-restore.md). |

### Your own tools

| Symptom | Fix |
|---|---|
| `adopt --apply` exits with code 2 | Either it was run without a terminal: add `--yes` (adopt's default groups remove, migrate and scope-down, plus moving plaintext secrets, without asking), `--groups remove,migrate,...` or `--own NAME=CHOICE,...`. Or the `--own` input was wrong: the message names the problem and nothing changed. |
| `loadout: no unmanaged item named 'X' (see: loadout configure own --all)` | Use the name exactly as `loadout configure own --all` prints it. A hook is `Event:matcher` (`Stop:` without matcher). |
| `hook 'X' matches N hooks; pick one: ...` or `'X' matches several kinds` | Add `#n` to the hook name as the message shows, or write `<kind>:<name>`. See [hook names](../reference/hooks.md#naming-hooks-of-your-own-tools). |
| `loadout configure set own` exits with code 1 and prints `skipped:` or `failed:` | Nothing was recorded for that item. The line says why. Typical causes: a secret or private file (see [Secret guard](your-own-tools.md#secret-guard)), a name that already exists in your personal layer with different content, or a file that could not be written. Fix it and run the command again. |
| I left a tool and want to be asked about it again | See [Be asked again about a left item](your-own-tools.md#be-asked-again-about-a-left-item). |

## Repos

| Symptom | Fix |
|---|---|
| `repo .mcp.json: …: the committed .mcp.json starts … from a path in one person's home (…), so teammates' agents cannot start it` | Move that server out of the committed file. Recommended: local scope (`claude mcp add --scope local …`) when only this repo needs it; your user-level server when you want it in every repo. loadout does not change the file ([VS Code](vscode.md#a-committed-mcpjson-with-your-own-path)). |
| `loadout profile` prints `skill NAME: … is not a link to …, left as is` | The repo has two different skills of that name, one in `.claude/skills` and one in `.agents/skills`; each agent uses its own. Keep one: delete or rename the other (use git, it is a repo file), then run `loadout profile` again to link it for the other agent. |
| `loadout profile` prints `skills not linked: … is a link`, `skills not linked: … points outside …` or `skill NAME: … leads outside …, not linked for …` | loadout links repo skills only between plain folders inside the repo, because a link that leads elsewhere is broken in every other clone. Replace the linked `.claude`, `.agents` or skills folder with a plain folder (or copy the skill into the repo), then run it again ([profile-format](../reference/profile-format.md#skills)). |
| `loadout profile` lists `.mcp.json` or `.claude/settings.json` as not written because the repo is for Codex only | Expected: a repo gets only the files of its agents. To add Claude Code, run `loadout init --agents claude,codex` and then `loadout profile NAME` again ([`.loadout.json`](../reference/cli.md#loadoutjson), [ADR 0030](../adr/0030-repo-files-follow-the-repos-agents.md)). |
| The same, because Claude Code is off for you (a repo without `.loadout.json`) | If you use Claude Code yourself, turn it on (`loadout configure set target claude on`). If you do not, but people who clone the repo do, name the repo's agents instead: `loadout init --agents claude,codex`. Then run `loadout profile NAME` again. |
| `kept the repo's values (run it again with --take-profile to use the profile's)` | Someone changed entries the profile set, and loadout kept their values. `loadout explain FILE` shows which entries came from which profile and which were changed. To use the profile's values, run `loadout profile NAME --take-profile` ([three-way merge](../reference/profile-format.md#what-applying-a-profile-does)). |
| `.loadout.json: …` and exit 1 | The repo's `.loadout.json` is invalid; nothing was changed. The message names the reason: fix the file, then run the command again. |
| `manage is false in .loadout.json: nothing written` | The repo switched loadout off. Set `"manage"` back to `true` in `.loadout.json` (or remove the key) to let loadout write there. |
| `no terminal: nothing written` | `init`, `profile` and `new skill --to repo` write without a terminal only with `--yes`. Read the plan above the message, then run the same command with `--yes`. |

`repo skill links` (plain files instead of links) is under [Windows](#windows).

## Cost

| Symptom | Fix |
|---|---|
| Context or token use is high | Heavy tools are per-project, and rtk compresses command output. Check with `/context` in Claude Code. Turn off an add-on you do not use with `loadout configure set plugin ID off`. |
