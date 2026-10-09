# Shared helpers for the cases' scaffold scripts. Source it with:
#   . "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
# A scaffold runs in the run's empty workspace with HOME set to the run's temporary home.
# Note: inside a run the agent cannot execute git (the eval sandbox denies /usr/bin/git);
# the scaffold itself can, so fixtures are still real repositories.
set -euo pipefail
EVALS_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
KIT_ROOT=$(cd "$EVALS_DIR/../../.." && pwd)

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
