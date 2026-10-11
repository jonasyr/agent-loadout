# Architecture

loadout has three parts: the kit repo (shared), your personal layer (yours) and `~/.claude` (where Claude Code reads its configuration). The CLI merges the first two into the third and keeps it current.

```mermaid
---
config:
  look: neo
  flowchart:
    curve: basis
    nodeSpacing: 24
    rankSpacing: 80
    wrappingWidth: 320
---
flowchart LR
  subgraph KIT["Kit repo · shared by everyone"]
    direction TB
    kPlugin["`**plugins/loadout/**
    hooks · skills · MCP servers`"]
    kRules["`**rules/**
    how Claude uses the tools`"]
    kBase["`**settings.base.json**
    the keys loadout manages`"]
  end

  subgraph PER["Personal layer · your git repo"]
    direction TB
    pRules["`**rules/**
    me.md, your preferences`"]
    pSkills["`**skills/ · hooks/**`"]
    pSet["`**settings.json**
    your overrides`"]
    pMcp["`**mcp.json**
    your MCP servers`"]
  end

  merge{{"`**three-way merge**`"}}
  snap[("`**~/.claude/.loadout/**
  snapshot of the last merge`")]

  subgraph CC["Claude Code configuration"]
    direction TB
    cPlugin["`**~/.claude/plugins/**
    the loadout plugin`"]
    cRulesK["`**~/.claude/rules/loadout**`"]
    cRulesP["`**~/.claude/rules/personal**`"]
    cSkills["`**~/.claude/skills/**
    **~/.claude/hooks/personal/**`"]
    cSet["`**~/.claude/settings.json**`"]
    cMcp["`**~/.claude.json**
    user-scope MCP servers`"]
  end

  kPlugin -. "Claude Code installs and auto-updates" .-> cPlugin
  kRules -- link --> cRulesK
  pRules -- link --> cRulesP
  pSkills -- link --> cSkills
  kBase ==> merge
  pSet ==> merge
  snap <-. "read, then rewrite" .-> merge
  merge ==> cSet
  pMcp -- "claude mcp add-json" --> cMcp

  classDef kit fill:#dbeafe,stroke:#2563eb,stroke-width:1.5px,color:#0f172a
  classDef personal fill:#dcfce7,stroke:#16a34a,stroke-width:1.5px,color:#0f172a
  classDef claude fill:#ffedd5,stroke:#ea580c,stroke-width:1.5px,color:#0f172a
  classDef engine fill:#fef3c7,stroke:#d97706,stroke-width:2px,color:#0f172a
  classDef state fill:#f1f5f9,stroke:#64748b,stroke-width:1.5px,stroke-dasharray:4 3,color:#0f172a
  class kPlugin,kRules,kBase kit
  class pRules,pSkills,pSet,pMcp personal
  class cPlugin,cRulesK,cRulesP,cSkills,cSet,cMcp claude
  class merge engine
  class snap state
  style KIT fill:#2563eb0f,stroke:#2563eb,stroke-width:1.5px
  style PER fill:#16a34a0f,stroke:#16a34a,stroke-width:1.5px
  style CC fill:#ea580c0f,stroke:#ea580c,stroke-width:1.5px
  linkStyle 4,5,7 stroke:#d97706,stroke-width:2.5px
```

## The parts

**The kit repo** (this repository) holds what is the same for everybody:

- `plugins/loadout/`: the plugin with hooks, two MCP servers (Serena and codebase-memory) and the skills. The repo is also a plugin marketplace, so Claude Code installs and updates the plugin itself.
- `rules/`: how Claude should use the tools. `~/.claude/rules/loadout` is a link to this folder.
- `catalog.json`: what is good, superseded or optional, and how to install and update each tool. See [Catalog format](../reference/catalog-format.md).
- `profiles/`: per-project add-ons. See [Profile format](../reference/profile-format.md).
- `settings.base.json` and `preferences.json`: the settings loadout manages and the working preferences it asks about.
- `cli/loadout/`: the CLI, Python standard library only. See the [CLI reference](../reference/cli.md).

**The personal layer** (`~/.config/loadout/personal`, ideally a private git repo) holds what is yours: `rules/me.md`, `settings.json` overrides, `mcp.json`, your skills, hooks and profiles. It is linked into `~/.claude/rules/personal`, `~/.claude/skills` and `~/.claude/hooks/personal`. See [Personal layer](../reference/personal-layer.md).

**`~/.claude`** is owned by Claude Code and by you. loadout adds links and merges its own keys into `settings.json`. It does not edit `~/.claude/CLAUDE.md`, unless you ask adopt to move its content into your personal layer. Your other settings stay.

**Machine-local state** (`~/.claude/.loadout/`) records what the merge last applied, your `leave` decisions and the maintenance timestamps. It is not synced.

## The settings merge

The merge combines the kit's `settings.base.json`, your personal `settings.json` and the snapshot of what was applied last time. Because it has the snapshot, it can tell a value you changed from a value the kit changed, and it can tell a hook you deleted from a hook it never added. The kit manages only the keys it declares, so everything else in your `settings.json` survives. The exact rules, including the per-hook merge, are in [Settings merge](../reference/settings-merge.md).

## The daily sync

At each session start the plugin runs `loadout hook-session-start`. It prints queued notices and, when the daily pull or the weekly check is due, starts `loadout maintenance` as a detached process. The session never waits for it.

```mermaid
sequenceDiagram
  autonumber
  box rgba(234, 88, 12, 0.10) Claude Code
    participant S as Session
  end
  box rgba(37, 99, 235, 0.10) loadout
    participant H as hook-session-start
    participant M as maintenance
  end
  box rgba(22, 163, 74, 0.10) Your machine
    participant G as Kit and personal repos
    participant C as ~/.claude
  end

  S->>H: session starts
  H-->>S: queued notices
  opt daily pull or weekly check due
    H-)M: start detached
    Note over S,H: the session does not wait
    activate M
    Note over M: one run at a time
    opt daily, unless LOADOUT_NO_AUTO_PULL=1
      M->>G: git pull --ff-only
      Note over G: skips a checkout with<br/>uncommitted changes
      G-->>M: new commits, or none
      opt new commits arrived
        M->>C: merge settings, add personal MCP
        M->>C: relink skills and hook scripts
      end
    end
    opt weekly
      M->>M: check tool versions
      Note right of M: notice only,<br/>never installs
    end
    M--)H: queue notices for the next session
    deactivate M
  end
```

Details, from `maintenance._maintain`:

- One maintenance run at a time: a lock file in the state folder, taken over only after an hour.
- The pull is `git pull --ff-only` on the kit and on the personal layer (when each is a git checkout), at most once a day, with git's terminal and credential prompts turned off (`maintenance.pull_if_clean`). It is skipped for a checkout with uncommitted changes.
- With `LOADOUT_NO_AUTO_PULL=1` the pull and the re-apply are skipped; the weekly version check still runs.
- Settings, personal MCP servers and links (skills, hook scripts, and copies in copy mode) are re-applied only when a pull brought new commits. Errors become a notice for the next session instead of a crash.
- The next session runs the pulled `loadout` code and the plugin's hooks. Whoever can push to the kit or your personal layer reaches every machine that follows it; see [the trust boundary](security-and-trust.md#the-trust-boundary).
- Plugins newly enabled through the personal layer are installed by Claude Code at its next start, not by this job ([0015](../adr/0015-claude-code-installs-synced-plugins.md)).
- The weekly check compares installed and latest versions (through mise when it manages the tool, so its pins and release-age rules count). It queues "updates available, run `loadout update`". It never installs.

Plugins are not part of this loop: Claude Code updates them through the marketplace.

## Why it is built this way

The main decisions, in short. Each has a decision record in [`docs/adr/`](../adr/README.md) with the alternatives that were considered.

- **A kit and a personal repo** ([0001](../adr/0001-kit-repo-plus-personal-repo.md)). The shared part can be updated for everybody while your own part stays yours and syncs through your own git. Without the split, either every user forks the kit or personal settings leak into it.
- **The kit is a plugin marketplace** ([0002](../adr/0002-kit-is-a-plugin-marketplace.md)). Claude Code already knows how to install, enable and update plugins. loadout reuses that instead of copying files into `~/.claude` itself.
- **Three-way settings merge** ([0003](../adr/0003-three-way-settings-merge.md)). A plain overwrite would destroy your own settings. A plain merge cannot tell whether you or the kit changed a value. The snapshot makes both safe and lets you delete a kit hook without it coming back.
- **Rules are linked as folders** ([0004](../adr/0004-rules-linked-as-directories.md)). Linking `rules/` leaves `~/.claude/CLAUDE.md` yours, and a pull updates the rules without touching a file you own.

See the [decision records](../adr/README.md) for these and for the others: catalog ([0005](../adr/0005-catalog-as-source-of-tool-knowledge.md)), secrets ([0006](../adr/0006-secrets-in-secrets-env.md)), scoping ([0007](../adr/0007-tiered-scoping-with-profiles.md)), code intelligence ([0008](../adr/0008-code-intelligence-routed-by-rule.md)), design tooling ([0009](../adr/0009-design-tooling-frontend-design-and-impeccable.md)), documentation ([0010](../adr/0010-docs-as-single-source-of-truth.md)), binary updates ([0011](../adr/0011-tool-binaries-notice-and-deliberate-update.md)) and backups ([0012](../adr/0012-destructive-actions-dry-run-confirm-backup.md)).

## Other agents (planned)

This is planned and not implemented: loadout today configures Claude Code only. The catalog, the rules (plain Markdown), `AGENTS.md` and `docs/`, Serena and codebase-memory (MCP servers) and the skills are already agent-neutral. The Claude-specific parts are settings, plugins and the marketplace, hooks and MCP registration. A later version is meant to add targets, for example Codex (MCP servers in `~/.codex/config.toml`, global rules in `AGENTS.md`, a skills directory) and possibly Gemini CLI or Cursor. Each target would map the same personal layer and catalog to that agent's configuration. To keep this cheap, the Claude-specific code sits in `settings_merge`, `bootstrap.setup_plugins`, `adopt._apply_*` and `link`, so it can later move behind a target interface. The source is section 14 of the [original design](../superpowers/specs/2026-10-08-agent-loadout-design.md).
