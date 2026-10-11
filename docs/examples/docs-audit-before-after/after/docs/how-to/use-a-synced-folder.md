# Use a synced folder

Keep your tasks in Dropbox (or any synced folder) so another machine sees them.

1. Point tasklog at the folder in your shell startup file:

       export TASKLOG_HOME=~/Dropbox/tasklog

2. Open a new terminal and add a task: `tasklog add "test sync"`.
3. Check that `~/Dropbox/tasklog/tasks.db` exists.

All settings: [configuration reference](../reference/configuration.md).
