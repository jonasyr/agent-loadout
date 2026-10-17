# Set loadout up from inside an agent

This page is written for a coding agent (Codex or Claude Code) that a user asked to set loadout up. If you are the user: paste this into your agent and let it guide you:

```text
Set up loadout for me by following https://raw.githubusercontent.com/jonasyr/agent-loadout/main/docs/how-to/install-with-an-agent.md
```

## Rules for you, the agent

- Ask one question at a time, and wait for the answer.
- Change nothing before the user said yes to the exact command you showed. Looking (the commands in step 1) is fine without asking.
- Never edit `~/.claude`, `~/.claude.json`, `~/.codex` or the personal layer (`~/.config/loadout/personal`) by hand. loadout writes them and records undo steps.
- Put no secret (API key, token, password) into the answers file, a command line or the chat. loadout asks for secrets later, and they go into `secrets.env`.
- Your shell has no terminal, so bootstrap cannot ask anything. Every answer goes in as a flag, and you run bootstrap with `</dev/null` so it never waits for input.
- Logins are the user's to type: `claude`, `codex login`, `gh auth login`. In Claude Code the user can type `! <command>` to run one in this session.

## 1. Look first

Run these read-only commands and tell the user in two or three lines what you found:

```bash
uname -s
grep -qi microsoft /proc/sys/kernel/osrelease 2>/dev/null && echo WSL
command -v loadout claude codex serena serena-hooks uv python3 git gh
ls ~/.config/loadout/personal 2>/dev/null && echo "a personal layer exists"
```

In WSL, also check which Codex the user runs: `command -v codex.exe`, and whether `command -v codex` prints a path under `/mnt/`. A Codex under `/mnt/` is the Windows one ([Codex in WSL](wsl.md#codex)).

If `loadout` is already installed, also run `loadout check` and keep its output for step 6.

On native Windows (not WSL), loadout is experimental: show the user the commands from [Getting started](../tutorials/getting-started.md#experimental-native-windows) and let them run them in PowerShell themselves.

## 2. Ask

Ask these, one at a time:

1. **Which agents** should loadout set up: Claude Code, Codex, or both? This becomes `--agents claude`, `--agents codex` or `--agents claude,codex`.
2. **In WSL, only when the user's Codex is the Windows one:** set up Codex in WSL (installs Codex here) or on Windows (they run `bootstrap.ps1` there)? This becomes `--codex-side wsl` or `--codex-side windows`. See [Codex in WSL](wsl.md#codex).
3. **The personal layer:** the URL of their private git repo for it, or a new one? This becomes `--personal <URL>` or `--personal new`. If a personal layer exists already (step 1), skip this question and the next two; loadout keeps it.
4. **About them** (only with `--personal new`; a cloned layer has its own): their name, their role, their main languages, and anything else about how they like to work. Every answer is optional.
5. **Working preferences** (only with `--personal new`): show the recommended answers from the table in [Preferences format](../reference/preferences-format.md) and ask whether to keep them or change some. `automode_trust` is not set here; the user can run `loadout configure prefs` later.

## 3. Show the answers file

Only with `--personal new`. Show the user the JSON you will write; write nothing yet:

```json
{
  "about": {"name": "Ada", "role": "backend developer", "languages": "Python, Go", "preferences": "short answers"},
  "preferences": {"answer_language": "match", "commit_style": "conventional"}
}
```

`about` takes `name`, `role`, `languages` and `preferences`. `preferences` takes the ids and values from the table in [Preferences format](../reference/preferences-format.md); a free-text option is written as `other:<text>`, for example `"answer_language": "other:French"`. Leave out what the user did not answer: loadout uses the default. Bootstrap refuses an unknown key or value, and a value that looks like a secret, before it changes anything.

After the yes in step 4, run `mktemp`, write the JSON to the new, empty file whose path it prints (an absolute path, outside the kit), and pass that path as `--answers`. A fresh file overwrites nothing.

## 4. Show the command, then run it after a yes

A machine without loadout, with a new personal layer:

```bash
git clone https://github.com/jonasyr/agent-loadout ~/agent-loadout
~/agent-loadout/bootstrap.sh --install --agents <list> --personal new --answers <the mktemp path> </dev/null
```

With the user's own personal layer, write `--personal <URL>` and leave out `--answers`.

A machine with loadout but no personal layer yet (for example after a failed clone): the same flags, with `loadout bootstrap` instead of the script:

```bash
loadout bootstrap --install --agents <list> --personal <new|URL> [--answers <the mktemp path>] </dev/null
```

A machine with loadout and a personal layer (repair):

```bash
loadout bootstrap --install --agents <list> </dev/null
```

Add `--codex-side wsl|windows` when step 2 asked it. In WSL with Codex only, use the steps in [Codex only on Windows with VS Code](#codex-only-on-windows-with-vs-code).

Before the user answers, say two things:

- `--install` runs the installers for missing tools without a further prompt ([What runs when you ask](../explanation/security-and-trust.md#what-runs-when-you-ask)).
- You do not add `--yes`: it would also apply the review of their existing setup without showing it. You review it in step 5 instead.

Run the command after the yes (with `--answers`, write the file first, as in step 3). It takes a few minutes. Show the user its summary lines.

## 5. Review the existing setup

Without a terminal, bootstrap skips the review of what was installed before loadout. Run `loadout adopt </dev/null` (a dry run, it changes nothing), explain each group it lists in one line, and ask which groups to apply. Then run `loadout adopt --apply --groups <the agreed groups> </dev/null`. Add `,secrets` only when the user agreed to move the plaintext secrets the dry run listed. The groups `update` and `install` run only with `--yes` added; with `--groups`, `--yes` applies exactly the groups named.

## 6. Finish

- **Codex:** Codex runs loadout's hooks only after the user approves them once: they start `codex` and run `/hooks`. In a repo with a `.codex/config.toml`, they accept Codex's trust question once ([Use loadout with Codex](codex.md#switch-it-on)).
- **Claude Code:** they restart it, or run `/reload-plugins`.
- **Logins:** bootstrap's "Still to do" list names the logins that are missing.
- Run `loadout check`. For each `warn` or `FAIL` line, give the user the fix from [Troubleshooting](troubleshooting.md), in one line each.
- For a new repo, they can run `loadout init` there. Without a terminal that is two steps: you run `loadout init --dry-run --agents claude`, `codex` or `claude,codex` (the repo's agents; ask which) and show the plan, then run `loadout init --yes --agents …` after their yes. For later changes, they ask you, and you use the `loadout:configure` skill.

## Codex only on Windows with VS Code

When the commands in section 1 printed `WSL` and the user chose Codex only, take these steps in this order instead of sections 4 to 6; they are the same as in [Find the path for your setup](setups.md#codex-only-on-windows-with-vs-code). Show each command and run it only after a yes, as above.

1. **WSL 2:** if the user is not sure their distribution is WSL 2, they run `wsl -l -v` in PowerShell ([WSL 2](wsl.md#1-use-wsl-2-not-wsl-1)).
2. **bootstrap:** the command from section 4 with `--agents codex --codex-side wsl --vscode-wsl`, for example `loadout bootstrap --install --agents codex --codex-side wsl --vscode-wsl </dev/null` when loadout is installed. Ask first whether they use VS Code with the Codex extension; only then add `--vscode-wsl`, which sets one VS Code setting so the extension runs the Codex in WSL, with a backup. Without VS Code, leave it out and skip `code .` in step 5. Then review their existing setup as in section 5.
3. **`codex login`:** the user types it in the WSL terminal.
4. **`/hooks`:** the user starts `codex` in the WSL terminal and approves loadout's hooks once.
5. **The first repo** (`loadout init --agents codex`), in a repo in the Linux home: run `loadout init --dry-run --agents codex </dev/null`, show the plan, and after a yes run `loadout init --yes --agents codex </dev/null`. The user opens the repo with `code .` from WSL, starts `codex` there once and accepts the trust question.
6. **`loadout check`:** give the fix for each `warn` or `FAIL` line in one line.
