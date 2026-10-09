---
max_turns: 60
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write, Edit, TodoWrite]
---

/loadout:onboard

I already know the answers to your questions, so here they are in one go:

- Purpose: a small command-line tool that tracks what is in my kitchen pantry and warns me about items that expire within the next 7 days. Success = I run one command every morning and see what to use up.
- Users: just me, from the terminal (a CLI), on Linux and macOS.
- Stack: Python 3.12, managed with uv, Typer for the CLI, pytest for tests, data in a single local SQLite file.
- Constraints: offline only (no network calls, no accounts), MIT licence, keep dependencies minimal.

Your summary is approved in advance as long as it matches these answers, so go ahead and write the project definition now. No profiles for now, please. Don't commit anything; I'll review the diff first.
