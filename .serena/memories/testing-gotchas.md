# Testing gotchas
Use `fake_home` / `fake_runner` (tests/conftest.py); tests that need bash stubs or POSIX hook paths are skipped on Windows. Timing tests use roomy limits. The hook-merge property test reads seeds from `LOADOUT_PROPERTY_SEEDS` / `LOADOUT_PROPERTY_FIRST_SEED`.
Details: CONTRIBUTING.md#test-rules, docs/adr/0017-hooks-merge-per-hook-with-tombstones.md.
