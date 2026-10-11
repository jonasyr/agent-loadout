# Testing gotchas
Use `fake_home` / `fake_runner` (tests/conftest.py); tests that need bash stubs or POSIX hook paths are skipped on Windows. Timing tests use roomy limits. The hook-merge property test reads seeds from `LOADOUT_PROPERTY_SEEDS` / `LOADOUT_PROPERTY_FIRST_SEED`.
Real installers run only in `.github/workflows/fresh-machine.yml` (fresh Ubuntu container, Windows experimental); entry-script tests (`tests/test_entry_scripts.py`) use stub binaries on PATH, never the network.
Details: CONTRIBUTING.md#test-rules, docs/adr/0017-hooks-merge-per-hook-with-tombstones.md.
