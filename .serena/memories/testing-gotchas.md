# Testing gotchas
Use `fake_home` / `fake_runner` (tests/conftest.py); tests run in verbose output mode (autouse fixture), calm-mode tests set `out.VERBOSE = False`. Rules: CONTRIBUTING.md#test-rules.
Tests with bash stubs or POSIX hook paths skip on Windows; timing tests use roomy limits; the property test's seed variables: docs/reference/cli.md#environment-variables. Real installers run only in fresh-machine CI.
Never run `git config --global` with HOME unset (`env -i`): git falls back to the real home and writes `~/.gitconfig` (it happened once; demo/sandbox.sh uses `--file`).
CI-only failures: Ubuntu's bash 5.2 differs from Arch's 5.3 (piped `BASH_SOURCE`); reproduce with `podman run ubuntu:24.04`. Entry-script tests run bash in a new session, so the CI runner's terminal does not matter.
Demo, diagrams, issue forms: CONTRIBUTING.md#the-readme-demo, #diagrams, #issues (diagram SVGs jitter on each render; the sync test hashes the inputs, ADR 0021).
