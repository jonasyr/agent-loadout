# 0037. Marketplaces only when a plugin uses them

- Status: Accepted
- Date: 2026-10-21
- Source: [Design: live tour fixes](../superpowers/specs/2026-10-21-live-tour-fixes-design.md), fixes 1 and 6 (live tour findings 17, 18 and 34)
- Amends: [ADR 0007](0007-tiered-scoping-with-profiles.md) (a profile can bring the marketplace of its plugins)

## Context

`settings.base.json` declared every marketplace a kit plugin or a profile plugin might come from in `extraKnownMarketplaces`, and `loadout bootstrap` and `loadout update` cloned each one Claude Code lacked. On the live tour (2026-10-21) a fresh bootstrap cloned `academic-research-skills` and `life-sciences` on every machine, although only the `thesis` profile uses the first and no enabled plugin uses the second (finding 18). Each clone costs time and disk on a first install, and `academic-research-skills` is declared for every session although it matters only in research repos. The forces:

- A profile plugin installs with `claude plugin install ID --scope project`, which fails when its marketplace is not added.
- `life-sciences` stays useful: someone without a claude.ai login enables `wiley-scholar-gateway@life-sciences` themselves, as the `thesis` profile's notes say.
- Existing machines already have the clones; removing them is not loadout's to do (they are Claude Code's, and a person may use them).
- Adopt (`loadout adopt`) declares the marketplace of a plugin it records in the personal layer, unless the kit declares it; that must keep working for a marketplace the kit no longer declares globally.

## Decision

We will clone a marketplace only when a plugin uses it, and let a profile bring the marketplace of its own plugins.

- **Bootstrap and update** add a declared marketplace only when it is `agent-loadout` (loadout's own) or an enabled plugin comes from it (`plugins_plan`, fix 1). Names are matched exactly against `claude plugin marketplace list --json` (`bootstrap.listed_marketplaces`). `life-sciences` stays declared in `settings.base.json` and is cloned once a plugin from it is enabled.
- **`academic-research-skills`** moves from `settings.base.json` to `profiles/thesis.json` (`settings.extraKnownMarketplaces`), so the repo's `.claude/settings.json` declares it for everyone who clones the repo.
- **Applying a profile** (`loadout profile`, `loadout init`, adopt's profile step) adds, before the installs, each marketplace the profile declares that a plugin in its `install` comes from and that Claude Code has not added: `claude plugin marketplace add <repo or url>`. In the plan it is a `run` step that restore cannot undo, as a profile's commands are: the clone is Claude Code's. Only marketplaces of plugins in `install` are added; a source with no repo or url (or one that starts with `-`) is named as a problem and not run. When Claude Code is off for the person, or the repo is not for Claude Code (`.loadout.json`), neither the add nor the install runs.
- When `claude plugin marketplace list` fails, the add is planned anyway: the install needs the marketplace, and adding a known one at worst fails with its own message.
- **Existing machines:** the unchanged base entry leaves `~/.claude/settings.json` through the settings merge; the clone in `known_marketplaces.json` stays.
- **Inventory** counts a kit profile's marketplace as the kit's (`profiles.kit_marketplaces`), so adopt does not offer a clone the `thesis` profile made as the person's own. Adopt's own check (`own._kit_markets`) still looks at `settings.base.json` only, so recording a plugin from such a marketplace keeps declaring the marketplace in the personal layer.

## Consequences

- A fresh machine clones only the marketplaces it uses; `thesis` repos bring theirs.
- A `loadout profile thesis` run can need network for a clone, and that clone is not undone by `loadout restore`; the plan says so.
- A person who used `academic-research-skills` outside a `thesis` repo keeps the clone, but the global declaration is gone; adopt records it in the personal layer when they keep its plugin.
