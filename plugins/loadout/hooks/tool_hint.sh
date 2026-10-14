#!/usr/bin/env bash
# Fast gate for tool_hint.py (docs/reference/hooks.md): most tool calls are no search, a docs lookup or a Serena or
# graph call, so Python starts only when the payload can matter. A superset is fine; tool_hint.py decides.
here="$(cd "$(dirname "$0")" && pwd)"
payload="$(head -c 200001)"
case "$payload" in
  *grep*|*Grep*|*"rg "*|*'"rg"'*|*find*|*Glob*|*'"Web'*|*mcp__*) ;;
  *) exit 0 ;;
esac
if command -v python3 >/dev/null 2>&1; then  # tool_hint.py runs on any Python 3.8+: no version check needed
  printf '%s' "$payload" | python3 -I "$here/tool_hint.py" 2>/dev/null
else
  printf '%s' "$payload" | "$here/run.sh" --soft --python "$here/tool_hint.py"
fi
exit 0
