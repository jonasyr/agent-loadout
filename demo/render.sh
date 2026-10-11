#!/usr/bin/env bash
# Renders docs/assets/demo.gif: records demo/loadout.tape in a container without network access (so the recording
# can only show the sandbox), then appends demo/claude-clip.mp4 when it exists (the real Claude Code part, recorded
# by the maintainer; see CONTRIBUTING.md). Needs podman (or docker: DEMO_ENGINE=docker).
# DEMO_KEEP_DIR=DIR also copies the recording (demo.mp4) there, to check frames.
set -euo pipefail
kit="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
engine="${DEMO_ENGINE:-podman}"
"$engine" build -q -t loadout-demo -f "$kit/demo/Containerfile" "$kit/demo" >/dev/null 2>&1
mkdir -p "$kit/docs/assets"
keep=()
if [ -n "${DEMO_KEEP_DIR:-}" ]; then mkdir -p "$DEMO_KEEP_DIR"; keep=(-v "$DEMO_KEEP_DIR:/keep"); fi
# the kit is copied into a fresh, committed repo, so `loadout check` sees a clean kit
"$engine" run --rm --network=none -v "$kit:/src:ro" -v "$kit/docs/assets:/out" ${keep[@]+"${keep[@]}"} \
  --entrypoint bash loadout-demo -c '
  set -e
  git config --global user.name demo && git config --global user.email demo@example.com
  git config --global init.defaultBranch main
  mkdir /kit && cd /src && git ls-files -co --exclude-standard -z | xargs -0 cp --parents -t /kit
  cd /kit && git init -q && git add -A && git commit -qm demo
  vhs demo/loadout.tape
  W=1200 H=800 FILL=0x181a24
  if [ -f demo/claude-clip.mp4 ]; then
    ffmpeg -y -loglevel error -i demo.mp4 -i demo/claude-clip.mp4 -filter_complex \
      "[0:v]fps=20,setsar=1[a];[1:v]scale=$W:$H:force_original_aspect_ratio=decrease,pad=$W:$H:(ow-iw)/2:(oh-ih)/2:color=$FILL,fps=20,setsar=1[b];[a][b]concat=n=2:v=1[v]" \
      -map "[v]" joined.mp4
  else
    echo "no demo/claude-clip.mp4 yet: rendering the sandbox part alone (the maintainer records it; see CONTRIBUTING.md)" >&2
    cp demo.mp4 joined.mp4
  fi
  ffmpeg -y -loglevel error -i joined.mp4 \
    -vf "fps=15,split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" demo.gif
  cp demo.gif /out/demo.gif
  if [ -d /keep ]; then cp demo.mp4 /keep/demo.mp4; fi'
echo "wrote $kit/docs/assets/demo.gif"
