# Shared helpers for the cases' scaffold scripts. Source it with:
#   . "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
# A scaffold runs in the run's empty workspace with HOME set to the run's temporary home.
# Note: inside a run the agent cannot execute git (the eval sandbox denies /usr/bin/git);
# the scaffold itself can, so fixtures are still real repositories.
set -euo pipefail
EVALS_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
KIT_ROOT=$(cd "$EVALS_DIR/../../.." && pwd)

# Safety guard: scaffolds write into $HOME (rules, a fake settings.json) and the cases rely on
# stubbed `loadout`/`playwright-cli`. Refuse to run unless this is an eval run started by
# evals/run.sh: HOME is the eval's temporary home (<tmp>/claude-eval-*/home, never the real
# one), the workspace lies inside it, and run.sh's stub directory is first on PATH.
eval_guard() {
  local real_home first
  real_home=$(getent passwd "$(id -u)" 2>/dev/null | cut -d: -f6)
  [ -n "$real_home" ] || real_home=$(python3 -c 'import os, pwd; print(pwd.getpwuid(os.getuid()).pw_dir)')
  case "$HOME" in
    */claude-eval-*/home) ;;
    *) echo "refusing to scaffold: HOME=$HOME is not an eval temp home (*/claude-eval-*/home); run the suite only via plugins/loadout/evals/run.sh" >&2; return 1 ;;
  esac
  if [ "$(cd "$HOME" && pwd -P)" = "$(cd "$real_home" && pwd -P)" ]; then
    echo "refusing to scaffold: HOME is the real home directory" >&2; return 1
  fi
  case "$(pwd -P)/" in
    "$(cd "$HOME" && pwd -P)"/*) ;;
    *) echo "refusing to scaffold: workspace $(pwd) is outside the eval home $HOME" >&2; return 1 ;;
  esac
  first=${PATH%%:*}
  case "$(basename "$first")" in
    loadout-eval-stub.*) ;;
    *) echo "refusing to scaffold: the loadout-eval-stub directory is not first on PATH; run the suite only via plugins/loadout/evals/run.sh" >&2; return 1 ;;
  esac
  local tool
  for tool in loadout playwright-cli chromium; do
    if [ "$(command -v "$tool")" != "$first/$tool" ]; then
      echo "refusing to scaffold: $tool does not resolve to the eval stub in $first" >&2; return 1
    fi
  done
}
eval_guard || exit 70

# What bootstrap links into ~/.claude/rules/loadout/ (the skills tell the agent to read them).
install_rules() {
  mkdir -p "$HOME/.claude/rules/loadout"
  cp "$KIT_ROOT"/rules/*.md "$HOME/.claude/rules/loadout/"
}

# What `loadout init` scaffolds into a project (templates/project, name filled in).
loadout_init_skeleton() {
  local name=$1
  cp -R "$KIT_ROOT/templates/project/." .
  find . -path ./.git -prune -o -type f -name '*.md' -print0 |
    xargs -0 sed -i "s/{{PROJECT_NAME}}/$name/g"
}

# Copy a shared fixture project (evals/fixtures/<name>) into the workspace.
copy_fixture() {
  cp -R "$EVALS_DIR/fixtures/$1/." .
}

# Copy the calling case's own files/ overlay (if any) on top.
copy_overlay() {
  local case_dir=$1
  if [ -d "$case_dir/files" ]; then cp -R "$case_dir/files/." .; fi
}

git_commit_all() {
  git init -q -b main
  git config user.name "Eval User"
  git config user.email "eval@example.com"
  git add -A
  git commit -q -m "${1:-initial commit}"
}
