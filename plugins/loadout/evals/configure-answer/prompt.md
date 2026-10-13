---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write, Edit]
# the loadout row of rules/tooling.md (eval runs do not load ~/.claude/rules; the other rows have their own opt-in case)
append_system_prompt: |
  # Tool routing (loadout)

  Pick the tool by the question, not by habit:

  | Need | Use |
  |---|---|
  | Questions about loadout, or changes to the loadout setup (tools, preferences, agents, profiles, undo) | The `loadout:configure` skill, even when the user does not name it; never edit `~/.claude` or `~/.codex` settings by hand |
---

Something loadout changed yesterday broke my setup. How do I get back to how it was before?
