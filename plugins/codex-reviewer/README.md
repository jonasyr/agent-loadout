# codex-reviewer

A stand-in for Codex's GitHub code review ("@codex review") for when it is unavailable, for example when its quota is exhausted. One read-only Claude Code agent reviews the current branch's diff against the default branch with Codex's open-source rubric, applies the repo's `AGENTS.md` rules, and returns the same JSON findings (P0–P2).

Off by default. Turn it on with `loadout configure set plugin codex-reviewer@agent-loadout on`, then `/reload-plugins`, and ask Claude Code to "run the codex-reviewer agent on this branch". Claude Code only; loadout never adds it to Codex.

License of the rubric: [NOTICE](NOTICE).
