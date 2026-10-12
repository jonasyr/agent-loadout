#!/usr/bin/env bash
# Renders docs/diagrams/<name>.mmd to <name>.light.svg and <name>.dark.svg with a pinned mermaid-cli, in a container
# without network access. Each SVG records the hash of what it was made from; tests/test_diagrams.py compares it.
# Usage: docs/diagrams/render.sh [NAME...]  (no NAME: every diagram). Needs podman (or docker: DIAGRAMS_ENGINE=docker).
set -euo pipefail
IMAGE="ghcr.io/mermaid-js/mermaid-cli/mermaid-cli:11.16.0"
dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
engine="${DIAGRAMS_ENGINE:-podman}"
cd "$dir"

sha256() { if command -v sha256sum >/dev/null; then sha256sum; else shasum -a 256; fi | cut -d' ' -f1; }

names=("$@")
if [ ${#names[@]} -eq 0 ]; then
  for f in *.mmd; do case "$f" in palette.*) ;; *) names+=("${f%.mmd}") ;; esac; done
fi
for n in "${names[@]}"; do
  case "$n" in palette.* | */* | "") echo "not a diagram: $n" >&2; exit 2 ;; esac
  [ -f "$n.mmd" ] || { echo "no such diagram: $n (expected docs/diagrams/$n.mmd)" >&2; exit 2; }
done

# write the SVGs as the calling user (podman maps it into the container with keep-id)
user=(--user "$(id -u):$(id -g)")
[ "$(basename "$engine")" = podman ] && user=(--userns=keep-id "${user[@]}")
work="$(mktemp -d "$dir/.render.XXXXXX")"
trap 'rm -rf "$work"' EXIT
w="$(basename "$work")"

for n in "${names[@]}"; do
  for v in light dark; do
    # the "%% palette" line becomes this variant's classDef lines
    awk -v pal="palette.$v.mmd" '
      /^[[:space:]]*%% palette[[:space:]]*$/ { while ((getline l < pal) > 0) print l; close(pal); next }
      { print }' "$n.mmd" >"$work/$n.$v.mmd"
    "$engine" run --rm --network=none "${user[@]}" -e HOME=/tmp -v "$dir:/data" "$IMAGE" \
      -i "$w/$n.$v.mmd" -o "$w/$n.$v.svg" -c "theme.$v.json" -b transparent --quiet
    hash="$({ cat "$n.mmd" "palette.$v.mmd" "theme.$v.json" | tr -d '\r'; printf '%s' "$IMAGE"; } | sha256)"
    awk -v c="<!-- diagram-source sha256:$hash -->" '
      !done && match($0, /<svg[^>]*>/) { $0 = substr($0, 1, RSTART + RLENGTH - 1) c substr($0, RSTART + RLENGTH); done = 1 }
      { print }' "$work/$n.$v.svg" >"$work/$n.$v.stamped"
    grep -q "diagram-source sha256:$hash" "$work/$n.$v.stamped" || { echo "no <svg> tag in the output for $n ($v)" >&2; exit 1; }
    mv "$work/$n.$v.stamped" "$n.$v.svg"
    echo "wrote docs/diagrams/$n.$v.svg"
  done
done
