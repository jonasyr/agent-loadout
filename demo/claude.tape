# The real Claude Code at the end of the README demo: a new project right after `loadout init`, then /loadout:onboard,
# which states the mode and asks its first question. Recorded by the maintainer with demo/record-claude.sh (it uses
# their Claude Code login and a little plan usage). record-claude.sh prepares /tmp/loadout-demo/my-app; the path never
# changes, so Claude Code asks to trust it only on the first run, and that happens while the recording is hidden.
# No Wait commands: VHS reads Wait from the top of the scrollback, so it cannot follow a full-screen app.
Output demo/claude-clip.mp4
Require claude
Source demo/style.tape

Hide
Type `cd /tmp/loadout-demo/my-app && PS1='\[\e[35m\]~/my-app ❯\[\e[0m\] ' && clear`
Enter
Sleep 1s
Show
Sleep 500ms
Type "claude"
Sleep 500ms
Enter
Hide
# first run only: the trust prompt preselects "No, exit"; Down picks "Yes, I trust this folder". Once trusted,
# these keys land in an empty prompt and do nothing.
Sleep 5s
Down
Sleep 300ms
Enter
Sleep 3s
Show
Sleep 3s
Type "/loadout:onboard"
Sleep 800ms
Enter
Sleep 40s
