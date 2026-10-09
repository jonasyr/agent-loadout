#!/usr/bin/env bash
# Fixture for the configure cases: an ordinary project directory, the kit rules in the
# run's temporary ~/.claude, and a fake merged ~/.claude/settings.json in the run's
# temporary HOME (never the real one). `loadout` itself is the stub from evals/bin, put
# on PATH by run.sh; it logs every call to ./.loadout-calls.log.
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
install_rules
# Belt and braces on top of eval_guard: only ever write a settings.json inside the eval home.
case "$HOME" in
  */claude-eval-*/home) ;;
  *) echo "refusing to write $HOME/.claude/settings.json outside an eval temp home" >&2; exit 70 ;;
esac
mkdir -p "$HOME/.claude"
cat > "$HOME/.claude/settings.json" <<'EOF'
{
  "enabledPlugins": {
    "loadout@agent-loadout": true,
    "superpowers@claude-plugins-official": true,
    "frontend-design@claude-plugins-official": true
  },
  "effortLevel": "high"
}
EOF
printf '# webshop\n\nA small storefront.\n' > README.md
git_commit_all "chore: init"
