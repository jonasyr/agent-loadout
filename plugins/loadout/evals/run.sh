#!/usr/bin/env bash
# The only supported way to run this suite. Never run `claude plugin eval` on this plugin
# directly: every scaffold sources lib/common.sh, which refuses to run without these rails.
#  - stubs first on PATH, in a directory named loadout-eval-stub.*:
#    `loadout` (bin/loadout): the plugin's SessionStart hook and the skills call it; the real
#    CLI would read/write the user's setup and its session hook can spawn
#    `loadout maintenance` (git pull on the kit and personal repos);
#    playwright-cli and the browser binaries (bin/playwright-cli, bin/browser-stub);
#  - a before/after checksum of the user's global state (global-state.sh), compared in an
#    EXIT trap so it also runs on errors and interrupts; exits 3 if anything changed.
# Usage: plugins/loadout/evals/run.sh [claude plugin eval options...]
#        e.g. run.sh --case 'onboard-*' --runs 2 -j 3
# The browser-routing case lives in ../evals-browser (opt-in: run.sh --eval-dir evals-browser).
# PATH stubs cannot stop an agent that calls a browser by absolute path, so only run it on a
# machine where a crashing headless browser is acceptable.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
plugin=$(dirname "$here")
before=$("$here/global-state.sh")
stub=""

finish() {
  local rc=$?
  [ -n "$stub" ] && rm -rf "$stub"
  local after
  after=$("$here/global-state.sh")
  if [ "$before" != "$after" ]; then
    echo "GLOBAL STATE CHANGED during the eval run:" >&2
    diff <(echo "$before") <(echo "$after") >&2 || true
    exit 3
  fi
  echo "global state unchanged"
  exit "$rc"
}
trap finish EXIT
trap 'exit 130' INT TERM

# The run's Bash sandbox can read only the workspace and the directories on PATH, and not
# /tmp, so the stub directory lives under $HOME/.cache and is put first on PATH.
mkdir -p "$HOME/.cache"
stub=$(mktemp -d "$HOME/.cache/loadout-eval-stub.XXXXXX")
install -m 755 "$here/bin/loadout" "$stub/loadout"
# Never start a real browser from an eval run: playwright-cli is a logging stub, and the
# browser binaries an agent might fall back to fail fast (they log to ./.browser-calls.log).
install -m 755 "$here/bin/playwright-cli" "$stub/playwright-cli"
for b in chromium chromium-browser google-chrome google-chrome-stable firefox playwright; do
  install -m 755 "$here/bin/browser-stub" "$stub/$b"
done

# When started from inside a Claude Code session, drop that session's bridge variables:
# eval children inherit CLAUDE_CODE_* and otherwise stall in API retries.
env -u CLAUDE_CODE_CHILD_SESSION -u CLAUDE_CODE_SESSION_ID -u CLAUDE_CODE_MESSAGING_SOCKET \
  -u CLAUDE_CODE_MESSAGING_TOKEN -u CLAUDE_CODE_BRIDGE_SESSION_ID -u CLAUDE_CODE_SESSION_ATTENDED \
  -u CLAUDE_CODE_ENTRYPOINT -u CLAUDE_CODE_EXECPATH \
  PATH="$stub:$PATH" claude plugin eval "$plugin" --trust-plugin --scaffold --no-publish "$@" \
  --allow-tools Bash Write Edit
