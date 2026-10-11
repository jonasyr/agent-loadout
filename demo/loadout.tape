# The README demo follows the README Quick start: an existing Claude Code setup, the one-liner, the health
# check and `loadout init`. demo/render.sh records it in a container without network, in a sandbox HOME with
# fake data, then joins the real Claude Code clip (demo/claude-clip.mp4) recorded by the maintainer.
Output demo.mp4
Require bash
Source demo/style.tape

Hide
Type `bash /kit/demo/sandbox.sh /home/demo && export HOME=/home/demo PATH=/home/demo/.local/bin:$PATH LOADOUT_NO_AUTO_PULL=1 LOADOUT_REPO_URL=/kit LOADOUT_DEMO_KIT=/kit && cd ~ && PS1='\[\e[35m\]~ ❯\[\e[0m\] ' && card() { bash /kit/demo/card.sh "$@"; read -rsn1; tput cnorm; clear; } && clear`
Enter
Sleep 8s
Type `card loadout 'A reviewed Claude Code setup in one command'`
Enter
Sleep 500ms
Show
Sleep 3500ms
Hide
Type " "
Sleep 300ms
Show

# ① the starting point
Hide
Type `card '① An existing Claude Code setup' 'MCP servers, plugins and a skill, added by hand over time'`
Enter
Sleep 300ms
Show
Sleep 2800ms
Hide
Type " "
Sleep 300ms
Show
Type "claude mcp list"
Sleep 300ms
Enter
Sleep 2500ms
Type "claude plugin list"
Sleep 300ms
Enter
Sleep 3500ms

# ② the Quick start one-liner (typed exactly as in README.md)
Hide
Type `card '② One command' 'installs what is missing, then reviews what you already have'`
Enter
Sleep 300ms
Show
Sleep 2800ms
Hide
Type " "
Sleep 300ms
Show
Type "cd ~"
Sleep 300ms
Enter
Sleep 500ms
Type "curl -fsSL https://raw.githubusercontent.com/jonasyr/agent-loadout/main/bootstrap.sh | bash -s -- --install"
Sleep 700ms
Enter
# answers in the order bootstrap asks (VHS's Wait reads the top of the scrollback, so it cannot follow a
# scrolling screen; typed answers queue in the terminal, the pauses only set the pace)
Sleep 5s
Sleep 1500ms
Enter
Sleep 700ms
Type "Alex"
Sleep 250ms
Enter
Sleep 500ms
Type "web developer"
Sleep 250ms
Enter
Sleep 500ms
Type "TypeScript, React"
Sleep 250ms
Enter
Sleep 500ms
Enter
Sleep 450ms
Enter
Sleep 450ms
Enter
Sleep 450ms
Enter
Sleep 450ms
Enter
Sleep 450ms
Enter
Sleep 450ms
Enter
Sleep 450ms
Enter
Sleep 450ms
Enter
Sleep 450ms
Type "2"
Sleep 250ms
Enter
Sleep 450ms
Enter
Sleep 900ms
Enter
Sleep 2500ms
Type "a"
Sleep 250ms
Enter
Sleep 1800ms
Type "a"
Sleep 250ms
Enter
Sleep 1800ms
Type "a"
Sleep 250ms
Enter
Sleep 1800ms
Type "c"
Sleep 250ms
Enter
Sleep 1200ms
Type "g"
Sleep 250ms
Enter
Sleep 1000ms
Type "g"
Sleep 250ms
Enter
Sleep 1500ms
Type "y"
Sleep 250ms
Enter
Sleep 9s

# ③ the Quick start's last terminal steps: the health check, then a project
Hide
Type `card '③ Check, then start a project' 'loadout check · loadout init'`
Enter
Sleep 300ms
Show
Sleep 2800ms
Hide
Type " "
Sleep 300ms
Show
Type "loadout check"
Sleep 300ms
Enter
Sleep 3500ms
Type "cd ~/my-app && loadout init"
Sleep 300ms
Enter
Sleep 2000ms
Enter
Sleep 6s

# ④ the real Claude Code clip follows (demo/claude-clip.mp4)
Hide
Type `card '④ Claude Code starts with the kit' 'then /loadout:onboard sets up the project'`
Enter
Sleep 300ms
Show
Sleep 2800ms
