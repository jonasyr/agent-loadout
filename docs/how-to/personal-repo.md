# Keep your personal layer in a private git repo

Use this page to sync your preferences, own tools and profiles across machines. Your personal layer is the folder that holds everything that is yours rather than the kit's: `rules/me.md`, your `settings.json` overrides, your MCP servers, skills, hooks, profiles and the agent choice (`targets.json`). It lives in `~/.config/loadout/personal`; if you set `LOADOUT_PERSONAL`, use that folder in the commands below. Which file does what: [Personal layer](../reference/personal-layer.md).

Bootstrap creates a starter layer when you press Enter at its personal-layer question (an empty URL). A starter stays on that machine until you make it a git repo. Make it **private**: it describes how you work and which tools you use. Your secrets are not in it; they live in `~/.config/loadout/secrets.env`.

## On your first machine

If git has never committed on this machine, tell it who you are once:

```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

Then turn the starter into a repo and look at what will be committed. Nothing in the list should be a key or an `.env` file:

```bash
cd ~/.config/loadout/personal
git init
git add -A
git status
```

Commit it and create a private GitHub repo for it with [gh](https://cli.github.com/) (bootstrap's `--install` installs gh):

```bash
git commit -m "chore: my loadout personal layer"
git branch -M main
gh repo create loadout-personal --private --source . --push
```

Without gh: create an empty private repo on github.com (or any git host), then:

```bash
git commit -m "chore: my loadout personal layer"
git branch -M main
git remote add origin git@github.com:YOU/loadout-personal.git
git push -u origin main
```

## On every further machine

Bootstrap first asks for your personal layer. Paste your repo's URL there, and bootstrap clones it to `~/.config/loadout/personal` instead of creating a starter. If the cloned layer already holds an agent choice (`targets.json`), bootstrap uses it without asking which agents to set up, and says so ("using your personal layer's agents: …").

A private repo needs access. Recommended: log in with gh and use the HTTPS URL (bootstrap's `--install` installs gh); use the SSH URL on a machine that already has an SSH key for GitHub.

- **With an SSH key on that machine:** confirm GitHub's host key once with `ssh -T git@github.com` (it also tells you whether GitHub accepts your key), then paste the SSH URL (`git@github.com:YOU/loadout-personal.git`).
- **With gh already logged in** (`gh auth status`): the HTTPS URL just works; bootstrap set git up to use your gh login.
- **Neither:** paste the HTTPS URL anyway. The clone fails without access; bootstrap then skips the steps that write into the personal layer and says so. Log in, then run bootstrap again; it asks for the URL once more:

  ```bash
  gh auth login
  gh auth setup-git
  loadout bootstrap
  ```

Or clone it yourself before you run bootstrap; bootstrap then uses that folder and does not ask for a URL:

```bash
git clone git@github.com:YOU/loadout-personal.git ~/.config/loadout/personal
```

If bootstrap already created a starter on that machine, move it aside first (`mv ~/.config/loadout/personal ~/.config/loadout/personal.starter`), clone, and copy over anything you want to keep.

## Day to day

- **Changes:** after `loadout configure` or an interactive `loadout adopt`, loadout offers to commit and push your personal layer. It refuses while a `*.env` file or a key or credential file would be committed. You can also commit and push yourself, like any repo.
- **Other machines:** the daily sync pulls your personal layer in the background and re-applies settings, MCP servers and links when new commits arrive, for each agent that is on ([the daily sync](../reference/state-and-sync.md#the-daily-sync)). Git refuses the pull when it would overwrite a local edit, so an edit is never overwritten; the notice and `loadout check` then name the files (`personal repo clean: daily sync paused: …`). With only VS Code's Codex extension (no Codex CLI) the sync never starts ([At each session start](../reference/state-and-sync.md#at-each-session-start)); pull yourself (`git -C ~/.config/loadout/personal pull`) and run `loadout bootstrap`.
- **What stays on one machine:** your `leave` decisions for own tools and the state in `~/.local/state/loadout/`, which also holds Codex's records ([Machine-local state](../reference/personal-layer.md#machine-local-state), [State folders](../reference/state-and-sync.md#state-folders)).
- **Which agents:** the choice of Claude Code, Codex or both is `targets.json` in your personal layer, so it follows you and every machine gets the same choice. `bootstrap --agents` and `loadout configure set target` change that stored choice, for all your machines once you commit it ([Use loadout with Codex](codex.md#switch-it-on)).
