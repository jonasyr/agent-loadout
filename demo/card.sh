#!/usr/bin/env bash
# A title card for the README demo: a cleared screen, the title in the accent colour and a muted subtitle, centred.
# The tape's card() waits for a key after it, then clears the screen.
title="$1" sub="${2:-}"
cols=$(tput cols) rows=$(tput lines)
pad() { printf '%*s' $(( (cols - ${#1}) / 2 )) ''; }
tput civis; clear
for _ in $(seq $(( rows / 2 - 2 ))); do echo; done
printf '%s\033[1;35m%s\033[0m\n\n' "$(pad "$title")" "$title"
[ -z "$sub" ] || printf '%s\033[2m%s\033[0m\n' "$(pad "$sub")" "$sub"
