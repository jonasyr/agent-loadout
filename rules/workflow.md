# Workflow (loadout)

- Use the superpowers process skills: brainstorming before building, writing-plans for multi-step work, systematic-debugging for bugs, verification-before-completion before claiming success.
- After writing an implementation plan, do not ask the planner's own execution question: run /loadout:execution-advisor in the same turn and ask only its question. If an execution question was already shown, state that the advisor's Recommended option supersedes it. (Codex: `$loadout:execution-advisor`.)
- One review pass per change: either `/code-review` (Codex: `/review`) or superpowers requesting-code-review, not both. Run `/security-review` (Codex has no such command: ask `/review` for a security-focused review) before merging security-relevant changes (auth, input handling, secrets, network exposure).
- UI loop: frontend-design for direction → build → playwright-cli (render at 320, 768 and 1280 px wide, exercise the main flows, read the console) → the `impeccable` skill's `audit`, then its `polish`. UI is not done until it was checked in a browser.
- At the end of a feature run the `loadout:docs-sync` skill.
- Domain tools (academic research, SonarQube, databases, Android) are enabled per project with `loadout profile <name>`; do not install them globally.
- New repo or repo without AGENTS.md: suggest `loadout init` and the `loadout:onboard` skill.
