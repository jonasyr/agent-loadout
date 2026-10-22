# Testing gotchas
Use `fake_home` / `fake_runner` (tests/conftest.py). Rules, output mode, platform skips, `git config --global` with HOME unset and CI-only failures (bash 5.2 vs 5.3): CONTRIBUTING.md#test-rules. Property test seed variables: docs/reference/cli.md#environment-variables. Real installers run only in fresh-machine CI.
Demo, diagrams, issue forms: CONTRIBUTING.md#the-readme-demo, #diagrams, #issues (diagram SVGs jitter on each render; the sync test hashes the inputs, ADR 0021).
