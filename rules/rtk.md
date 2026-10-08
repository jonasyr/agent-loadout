# rtk (loadout)

Applies only when the `rtk` command exists. rtk is a token-optimizing CLI proxy; a hook rewrites shell commands through it automatically.

- `rtk gain` shows token savings; `rtk gain --history` shows command history with savings.
- `rtk discover` analyses Claude Code history for missed opportunities.
- `rtk proxy <cmd>` runs a command without filtering (use it when you need raw, complete output).
- If `rtk gain` fails, the wrong `rtk` (Rust Type Kit) may be installed.
