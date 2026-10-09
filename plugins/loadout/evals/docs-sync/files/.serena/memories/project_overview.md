tasklog: small CLI task logger (SQLite, JSON/CSV export). Commands and limits: docs/reference/cli.md; modules: docs/architecture.md.

Gotcha: tests create their own database under pytest's tmp_path; never point them at ~/.local/share/tasklog.
