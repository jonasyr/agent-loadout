# The README demo: loadout takes over an existing Claude Code setup. Render with demo/render.sh
# (in a container, without network); it records the real CLI in a sandbox HOME with fake data.
Output demo.gif

Require bash
Set Shell bash
Set FontSize 14
Set Width 1280
Set Height 940
Set Padding 24
Set Theme "Catppuccin Mocha"
Set TypingSpeed 45ms
Set PlaybackSpeed 1.0
Set Framerate 20

Hide
Type "bash /kit/demo/sandbox.sh /home/demo && export HOME=/home/demo PATH=/home/demo/.local/bin:$PATH LOADOUT_NO_AUTO_PULL=1 && cd ~ && PS1='\[\e[1;35m\]~\[\e[0m\] $ ' && clear"
Enter
Sleep 8s
Show

Type "# An existing setup. What would loadout change, and why?"
Enter
Type "loadout adopt"
Sleep 300ms
Enter
Sleep 10s

Type "clear; loadout adopt --apply"
Enter
Sleep 4s
Type "a"
Enter
Sleep 900ms
Type "a"
Enter
Sleep 900ms
Type "a"
Enter
Sleep 1200ms
Type "c"
Enter
Sleep 900ms
Type "g"
Enter
Sleep 700ms
Type "g"
Enter
Sleep 900ms
Type "y"
Enter
Sleep 8s

Type "clear; loadout check"
Enter
Sleep 7s

Type "clear; loadout restore --list"
Enter
Sleep 6s
