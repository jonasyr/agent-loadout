#!/usr/bin/env bash
# Fixture: a static checkout page whose button styles were just changed.
# playwright-cli and the browser binaries are logging stubs from evals/bin (see evals/run.sh).
case_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
. "$case_dir/../../evals/lib/common.sh"
install_rules
copy_overlay "$case_dir"
printf '# shop\n\nStatic storefront: open src/index.html.\n' > README.md
git_commit_all "feat: checkout page"
