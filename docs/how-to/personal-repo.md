# Keep your personal layer in a private git repo

Use this page to sync your preferences, own tools and profiles across machines. Your personal layer is the folder that holds everything that is yours rather than the kit's: `rules/me.md`, your `settings.json` overrides, your MCP servers, skills, hooks and profiles. It lives in `~/.config/loadout/personal` (or wherever `LOADOUT_PERSONAL` points). Which file does what: [Personal layer](../reference/personal-layer.md).

Bootstrap creates a starter layer when you press Enter at its first question. A starter stays on that machine until you make it a git repo. Make it **private**: it describes how you work and which tools you use. Your secrets are not in it; they live in `~/.config/loadout/secrets.env`, next to the folder.

## On your first machine

Turn the starter into a private GitHub repo, with [gh](https://cli.github.com/) (bootstrap installs it):

```bash
cd ~/.config/loadout/personal
git init -b main
git add -A
git commit -m "chore: my loadout personal layer"
gh repo create loadout-personal --private --source . --push
```

Without gh: create an empty private repo on github.com (or any git host), then:

```bash
cd ~/.config/loadout/personal
git init -b main
git add -A
git commit -m "chore: my loadout personal layer"
git remote add origin git@github.com:YOU/loadout-personal.git
git push -u origin main
```

If git asks who you are, set your name and email once (`git config --global user.name "…"` and `git config --global user.email "…"`) and commit again.

## On every further machine

Bootstrap asks for your personal layer first. Paste your repo's URL there, and bootstrap clones it to `~/.config/loadout/personal` instead of creating a starter.

A private repo needs access:

- **With an SSH key on that machine:** paste the SSH URL (`git@github.com:YOU/loadout-personal.git`). It works on the first run.
- **Without one:** paste the HTTPS URL anyway. The clone fails without access, and bootstrap continues without a personal layer and says so. Then log in and run bootstrap again; it asks for the URL once more:

  ```bash
  gh auth login && gh auth setup-git
  loadout bootstrap
  ```

Or clone it yourself before you run bootstrap; bootstrap then uses that folder and asks nothing:

```bash
git clone git@github.com:YOU/loadout-personal.git ~/.config/loadout/personal
```

If bootstrap already created a starter on that machine, move it aside first (`mv ~/.config/loadout/personal ~/.config/loadout/personal.starter`), clone, and copy over anything you want to keep.

## Day to day

- **Changes:** after `loadout configure` or an interactive `loadout adopt`, loadout offers to commit and push your personal layer. It refuses while a `*.env` file or a key or credential file would be committed. You can also commit and push yourself, like any repo.
- **Other machines:** the daily sync pulls your personal layer in the background and re-applies settings, MCP servers and links when new commits arrive ([the daily sync](../explanation/architecture.md#the-daily-sync)). A checkout with uncommitted changes is skipped, so a local edit is never overwritten.
- **What stays on one machine:** your `leave` decisions for own tools and the state in `~/.claude/.loadout/` ([Machine-local state](../reference/personal-layer.md#machine-local-state)).
