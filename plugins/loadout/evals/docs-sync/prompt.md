---
max_turns: 40
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write, Edit, TodoWrite]
---

I just finished a small feature on this branch: task titles can now be up to 200 characters instead of 120 (the constant in src/tasklog/store.py, not committed yet). Before I merge, bring the documentation in line with this change.
