#!/usr/bin/env bash
# Fast gate for tool_hint.py (docs/reference/hooks.md): only a web lookup can get the docs hint, so Python starts
# only for one. A superset is fine; tool_hint.py decides.
here="$(cd "$(dirname "$0")" && pwd)"
payload="$(head -c 200001)"
case "$payload" in
  *'"tool_name":"Web'*|*'"tool_name": "Web'*) ;;
  *) exit 0 ;;
esac
# tool_hint.py runs on any Python 3.8+: no version check needed. A python3 that fails to run (the Windows Store
# alias exists but only prints a notice) falls back to run.sh, which tries python3, then python, then uv.
if command -v python3 >/dev/null 2>&1 && out="$(printf '%s' "$payload" | python3 -I "$here/tool_hint.py" 2>/dev/null)"; then
  printf '%s' "$out"
else
  printf '%s' "$payload" | "$here/run.sh" --soft --python "$here/tool_hint.py"
fi
exit 0
