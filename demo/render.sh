#!/usr/bin/env bash
# Renders docs/assets/demo.gif from demo/loadout.tape in a container, without network access,
# so the recording can only show the sandbox. Needs podman (or docker: DEMO_ENGINE=docker).
set -euo pipefail
kit="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
engine="${DEMO_ENGINE:-podman}"
"$engine" build -q -t loadout-demo -f "$kit/demo/Containerfile" "$kit/demo" >/dev/null 2>&1
mkdir -p "$kit/docs/assets"
# the kit is copied into a fresh, committed repo, so `loadout check` sees a clean kit
"$engine" run --rm --network=none -v "$kit:/src:ro" -v "$kit/docs/assets:/out" --entrypoint bash loadout-demo -c '
  set -e
  git config --global user.name demo && git config --global user.email demo@example.com
  git config --global init.defaultBranch main
  mkdir /kit && cd /src && git ls-files -co --exclude-standard -z | xargs -0 cp --parents -t /kit
  cd /kit && git init -q && git add -A && git commit -qm demo
  vhs demo/loadout.tape && cp demo.gif /out/demo.gif'
echo "wrote $kit/docs/assets/demo.gif"
