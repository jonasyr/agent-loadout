# Diagrams as Code Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The five Mermaid diagrams in the docs become sources in `docs/diagrams/`, rendered to a light and a dark SVG each by a pinned mermaid-cli, embedded with `<picture>`, and a stdlib test fails whenever an SVG no longer matches its source.

**Architecture:** `docs/diagrams/render.sh` splices a per-variant palette into each flowchart source, runs mermaid-cli 11.16.0 in a container without network, and writes `<name>.<variant>.svg` with a `diagram-source sha256:` comment. `tests/diagrams_support.py` computes the same hash in Python; `tests/test_diagrams_render.py` pins render.sh's behaviour with a stub container engine, and `tests/test_diagrams.py` is the repo gate (sources, palettes, SVGs, embeds).

**Tech Stack:** Bash, awk, mermaid-cli 11.16.0 container (podman or docker), Python 3.10+ stdlib, pytest, playwright-cli for visual checks.

**Spec:** `docs/superpowers/specs/2026-10-12-diagrams-as-code-design.md`

## Global Constraints

- Image pinned exactly: `ghcr.io/mermaid-js/mermaid-cli/mermaid-cli:11.16.0` (already pulled locally; verified with `mmdc -V`).
- Container runs with `--network=none`; engine is podman by default, docker via `DIAGRAMS_ENGINE=docker`.
- Hash = SHA-256 of `<name>.mmd` + `palette.<variant>.mmd` + `theme.<variant>.json` (in that order, CR bytes dropped) + the image reference string. Comment format, right after the opening `<svg …>` tag: `<!-- diagram-source sha256:<hex> -->`.
- `htmlLabels: false` (top level and `flowchart`); font stack `ui-sans-serif, system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif`; `-b transparent`.
- Dark variant matches the README demo: `#0f1117` background family, `#e6e6eb` text, violet accent `#a78bfa`.
- Flowchart sources carry no colours: no `classDef`, `style`, `linkStyle` or hex values; they end with a `%% palette` line. Sequence diagrams keep their `box rgba(…)` tints.
- Diagram content (nodes, labels, edges, frontmatter such as `look: neo`, `curve`, spacing) does not change.
- Tests: standard library plus pytest only; run on Linux and Windows CI (bash-based tests skip on Windows with a reason). Never touch the real `~/.claude`, `~/.claude.json`, `~/.config/loadout`.
- Conventional Commits; no `Co-Authored-By` or any AI attribution. Author must be `Jonas Weirauch <jonas.weirauch@gmx.de>`.
- Pushing and opening the PR need the user's OK.

## Review Focus

1. **A Windows checkout converts `.mmd` line endings to CRLF.** The gate must not report a stale diagram that is not stale: both hashes drop CR bytes, `.gitattributes` keeps `.mmd` at LF. Pinned by `test_crlf_source_hashes_like_lf` (Task 1).
2. **A class defined in only one palette** leaves a node unstyled in one colour scheme, invisible to whoever only checks light mode. Pinned by `test_palettes_define_every_class_used` (Task 2).
3. **mermaid-cli silently ignores `htmlLabels: false`** and emits `<foreignObject>`: labels go blank in image viewers. Pinned by `test_svgs_have_no_html_labels_or_external_resources` (Task 2).
4. **The `[Source]` link sits in the same HTML block as `</picture>`**, so GitHub prints it as literal text. Pinned by `test_each_embed_links_its_source` requiring a blank line (Task 3).
5. **render.sh fails half-way or gets a wrong name** and leaves a partial SVG, a temp folder, or renders the palette as a diagram. Pinned by `test_engine_failure_writes_nothing`, `test_unknown_name_fails`, `test_palette_is_not_a_diagram` (Task 1).

---

### Task 1: render.sh, themes and palettes

**Files:**
- Create: `docs/diagrams/render.sh` (executable), `docs/diagrams/theme.light.json`, `docs/diagrams/theme.dark.json`, `docs/diagrams/palette.light.mmd`, `docs/diagrams/palette.dark.mmd`
- Create: `tests/diagrams_support.py`, `tests/test_diagrams_render.py`
- Modify: `.gitattributes` (add `*.mmd text eol=lf`)

**Interfaces:**
- Produces: `diagrams_support.DIAGRAMS: Path`, `VARIANTS = ("light", "dark")`, `HASH_COMMENT: re.Pattern` (group 1 = hex), `image_ref(render_sh: Path) -> str`, `source_hash(folder: Path, name: str, variant: str, image: str) -> str`, `sources(folder: Path = DIAGRAMS) -> list[str]`.
- Produces: `render.sh [NAME…]`; exit 2 for an unknown name or a palette name; writes `<name>.light.svg` and `<name>.dark.svg` next to the source; prints `wrote docs/diagrams/<name>.<variant>.svg`.
- Produces palette classes: nodes `kit personal claude engine state truth entry notes local`; subgraphs `kitGroup personalGroup claudeGroup engineGroup notesGroup`; edges `emph truthLink muted`.

- [ ] **Step 1: Write the shared helper**

`tests/diagrams_support.py`:

```python
"""Shared by the diagram tests: where the diagrams live and how render.sh fingerprints an SVG."""
import hashlib
import re
from pathlib import Path

from loadout import paths

DIAGRAMS = paths.kit_root() / "docs" / "diagrams"
VARIANTS = ("light", "dark")
HASH_COMMENT = re.compile(r"<!-- diagram-source sha256:([0-9a-f]{64}) -->")


def image_ref(render_sh: Path) -> str:
    """The pinned mermaid-cli image, read from render.sh so there is one home for it."""
    m = re.search(r'^IMAGE="([^"]+)"$', render_sh.read_text(encoding="utf-8"), re.M)
    assert m, f"{render_sh} sets no IMAGE"
    return m.group(1)


def source_hash(folder: Path, name: str, variant: str, image: str) -> str:
    """SHA-256 of the source, its palette and theme (CRs dropped, like render.sh's tr -d) and the image reference."""
    h = hashlib.sha256()
    for part in (f"{name}.mmd", f"palette.{variant}.mmd", f"theme.{variant}.json"):
        h.update((folder / part).read_bytes().replace(b"\r", b""))
    h.update(image.encode("utf-8"))
    return h.hexdigest()


def sources(folder: Path = DIAGRAMS) -> list[str]:
    """Diagram names: every .mmd except the palettes."""
    return sorted(p.stem for p in folder.glob("*.mmd") if not p.name.startswith("palette."))
```

- [ ] **Step 2: Write the failing render tests**

`tests/test_diagrams_render.py`:

```python
"""docs/diagrams/render.sh, run against a copy of the folder with a stub container engine (no real mermaid-cli)."""
import os
import shutil
import subprocess

import pytest

from diagrams_support import DIAGRAMS, HASH_COMMENT, image_ref, source_hash

pytestmark = pytest.mark.skipif(os.name == "nt", reason="render.sh is a bash tool for maintainers on Linux and macOS")

# Stands in for podman/docker: finds the mount, the -i input and the -o output, and writes a minimal SVG that
# carries the composed input, so tests can see what render.sh handed to mermaid-cli.
STUB = r"""#!/usr/bin/env bash
[ -n "${STUB_FAIL:-}" ] && { echo "engine failed" >&2; exit 1; }
while [ $# -gt 0 ]; do
  case "$1" in
    -v) host="${2%%:*}"; shift 2;;
    -i) in="$2"; shift 2;;
    -o) out="$2"; shift 2;;
    *) shift;;
  esac
done
{ printf '<svg id="my-svg" xmlns="http://www.w3.org/2000/svg"><desc>'; cat "$host/$in"; printf '</desc></svg>'; } > "$host/$out"
"""

FLOW = "flowchart LR\n  a --> b\n  class a kit\n%% palette\n"
SEQ = "sequenceDiagram\n  A->>B: hi\n"


@pytest.fixture
def folder(tmp_path):
    d = tmp_path / "diagrams"
    d.mkdir()
    for f in ("render.sh", "palette.light.mmd", "palette.dark.mmd", "theme.light.json", "theme.dark.json"):
        shutil.copy2(DIAGRAMS / f, d / f)
    (d / "flow.mmd").write_text(FLOW, encoding="utf-8", newline="\n")
    (d / "seq.mmd").write_text(SEQ, encoding="utf-8", newline="\n")
    stub = tmp_path / "engine"
    stub.write_text(STUB, encoding="utf-8", newline="\n")
    stub.chmod(0o755)
    return d


def render(folder, *names, **env):
    e = {**os.environ, "DIAGRAMS_ENGINE": str(folder.parent / "engine"), **env}
    return subprocess.run(["bash", str(folder / "render.sh"), *names], capture_output=True, text=True, env=e, timeout=60)


def svgs(folder):
    return sorted(p.name for p in folder.glob("*.svg"))


def test_image_is_pinned():
    assert image_ref(DIAGRAMS / "render.sh") == "ghcr.io/mermaid-js/mermaid-cli/mermaid-cli:11.16.0"


def test_renders_every_diagram_in_both_variants_offline(folder):
    p = render(folder)
    assert p.returncode == 0, p.stderr
    assert svgs(folder) == ["flow.dark.svg", "flow.light.svg", "seq.dark.svg", "seq.light.svg"]
    assert "--network=none" in (folder / "render.sh").read_text(encoding="utf-8")


def test_svg_records_the_hash_python_computes(folder):
    assert render(folder).returncode == 0
    image = image_ref(folder / "render.sh")
    for name in ("flow", "seq"):
        for variant in ("light", "dark"):
            text = (folder / f"{name}.{variant}.svg").read_text(encoding="utf-8")
            assert text.startswith('<svg id="my-svg" xmlns="http://www.w3.org/2000/svg"><!-- diagram-source sha256:')
            assert HASH_COMMENT.findall(text) == [source_hash(folder, name, variant, image)]


def test_palette_line_is_replaced_by_the_variant_palette(folder):
    assert render(folder).returncode == 0
    light = (folder / "flow.light.svg").read_text(encoding="utf-8")
    dark = (folder / "flow.dark.svg").read_text(encoding="utf-8")
    assert "%% palette\n" not in light and "%% palette\n" not in dark
    assert (folder / "palette.light.mmd").read_text(encoding="utf-8").strip() in light
    assert (folder / "palette.dark.mmd").read_text(encoding="utf-8").strip() in dark


def test_named_render_touches_only_that_diagram(folder):
    p = render(folder, "seq")
    assert p.returncode == 0, p.stderr
    assert svgs(folder) == ["seq.dark.svg", "seq.light.svg"]


def test_unknown_name_fails(folder):
    p = render(folder, "nope")
    assert p.returncode == 2 and "no such diagram: nope" in p.stderr
    assert svgs(folder) == []


def test_palette_is_not_a_diagram(folder):
    p = render(folder, "palette.light")
    assert p.returncode == 2 and "not a diagram" in p.stderr


def test_engine_failure_writes_nothing(folder):
    p = render(folder, STUB_FAIL="1")
    assert p.returncode != 0
    assert svgs(folder) == []
    assert not list(folder.glob(".render.*")), "the temporary folder must be removed"


def test_crlf_source_hashes_like_lf(folder):
    (folder / "flow.mmd").write_bytes(FLOW.replace("\n", "\r\n").encode())
    assert render(folder, "flow").returncode == 0
    crlf = HASH_COMMENT.findall((folder / "flow.light.svg").read_text(encoding="utf-8"))
    (folder / "flow.mmd").write_bytes(FLOW.encode())
    assert render(folder, "flow").returncode == 0
    lf = HASH_COMMENT.findall((folder / "flow.light.svg").read_text(encoding="utf-8"))
    assert crlf == lf == [source_hash(folder, "flow", "light", image_ref(folder / "render.sh"))]
```

- [ ] **Step 3: Run them to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_diagrams_render.py`
Expected: FAIL/ERROR: `FileNotFoundError` for `docs/diagrams/render.sh` (and `palette.light.mmd`) in the fixture and in `test_image_is_pinned`.

- [ ] **Step 4: Write the themes**

`docs/diagrams/theme.light.json`:

```json
{
  "theme": "base",
  "htmlLabels": false,
  "flowchart": { "htmlLabels": false },
  "fontFamily": "ui-sans-serif, system-ui, -apple-system, \"Segoe UI\", Helvetica, Arial, sans-serif",
  "themeVariables": {
    "fontFamily": "ui-sans-serif, system-ui, -apple-system, \"Segoe UI\", Helvetica, Arial, sans-serif",
    "background": "#ffffff",
    "primaryColor": "#f8fafc",
    "primaryTextColor": "#0f172a",
    "primaryBorderColor": "#94a3b8",
    "secondaryColor": "#f8fafc",
    "tertiaryColor": "#f8fafc",
    "lineColor": "#64748b",
    "textColor": "#0f172a",
    "titleColor": "#0f172a",
    "edgeLabelBackground": "#ffffff",
    "clusterBkg": "#f8fafc",
    "clusterBorder": "#cbd5e1",
    "actorBkg": "#f8fafc",
    "actorBorder": "#94a3b8",
    "actorTextColor": "#0f172a",
    "actorLineColor": "#94a3b8",
    "signalColor": "#475569",
    "signalTextColor": "#0f172a",
    "labelBoxBkgColor": "#f1f5f9",
    "labelBoxBorderColor": "#94a3b8",
    "labelTextColor": "#0f172a",
    "loopTextColor": "#0f172a",
    "noteBkgColor": "#fef3c7",
    "noteBorderColor": "#d97706",
    "noteTextColor": "#0f172a",
    "activationBkgColor": "#e2e8f0",
    "activationBorderColor": "#64748b",
    "sequenceNumberColor": "#ffffff"
  }
}
```

`docs/diagrams/theme.dark.json`:

```json
{
  "theme": "base",
  "htmlLabels": false,
  "flowchart": { "htmlLabels": false },
  "fontFamily": "ui-sans-serif, system-ui, -apple-system, \"Segoe UI\", Helvetica, Arial, sans-serif",
  "themeVariables": {
    "darkMode": true,
    "fontFamily": "ui-sans-serif, system-ui, -apple-system, \"Segoe UI\", Helvetica, Arial, sans-serif",
    "background": "#0f1117",
    "primaryColor": "#1a1d27",
    "primaryTextColor": "#e6e6eb",
    "primaryBorderColor": "#4b5163",
    "secondaryColor": "#1a1d27",
    "tertiaryColor": "#1a1d27",
    "lineColor": "#9ca3af",
    "textColor": "#e6e6eb",
    "titleColor": "#e6e6eb",
    "edgeLabelBackground": "#0f1117",
    "clusterBkg": "#151821",
    "clusterBorder": "#4b5163",
    "actorBkg": "#1a1d27",
    "actorBorder": "#6b7280",
    "actorTextColor": "#e6e6eb",
    "actorLineColor": "#6b7280",
    "signalColor": "#9ca3af",
    "signalTextColor": "#e6e6eb",
    "labelBoxBkgColor": "#1a1d27",
    "labelBoxBorderColor": "#6b7280",
    "labelTextColor": "#e6e6eb",
    "loopTextColor": "#e6e6eb",
    "noteBkgColor": "#2e1065",
    "noteBorderColor": "#a78bfa",
    "noteTextColor": "#e6e6eb",
    "activationBkgColor": "#262a36",
    "activationBorderColor": "#9ca3af",
    "sequenceNumberColor": "#0f1117"
  }
}
```

- [ ] **Step 5: Write the palettes**

Light keeps today's colours exactly. Edge classes work through Mermaid 11 edge IDs (`a e1@--> b`, `class e1 emph`), verified with 11.16.0 while planning; subgraph classes (`class KIT kitGroup`) too.

`docs/diagrams/palette.light.mmd`:

```
%% Light palette: replaces the "%% palette" line of every flowchart (see render.sh). Same class names as palette.dark.mmd.
  classDef kit fill:#dbeafe,stroke:#2563eb,stroke-width:1.5px,color:#0f172a
  classDef personal fill:#dcfce7,stroke:#16a34a,stroke-width:1.5px,color:#0f172a
  classDef claude fill:#ffedd5,stroke:#ea580c,stroke-width:1.5px,color:#0f172a
  classDef engine fill:#fef3c7,stroke:#d97706,stroke-width:2px,color:#0f172a
  classDef state fill:#f1f5f9,stroke:#64748b,stroke-width:1.5px,stroke-dasharray:4 3,color:#0f172a
  classDef truth fill:#d1fae5,stroke:#059669,stroke-width:2.5px,color:#0f172a
  classDef entry fill:#dbeafe,stroke:#2563eb,stroke-width:1.5px,color:#0f172a
  classDef notes fill:#ede9fe,stroke:#7c3aed,stroke-width:1.5px,color:#0f172a
  classDef local fill:#f1f5f9,stroke:#64748b,stroke-width:1.5px,stroke-dasharray:4 3,color:#0f172a
  classDef kitGroup fill:#2563eb0f,stroke:#2563eb,stroke-width:1.5px
  classDef personalGroup fill:#16a34a0f,stroke:#16a34a,stroke-width:1.5px
  classDef claudeGroup fill:#ea580c0f,stroke:#ea580c,stroke-width:1.5px
  classDef engineGroup fill:#d977060f,stroke:#d97706,stroke-width:1.5px
  classDef notesGroup fill:#7c3aed0f,stroke:#7c3aed,stroke-width:1.5px
  classDef emph stroke:#d97706,stroke-width:2.5px
  classDef truthLink stroke:#059669,stroke-width:2.5px
  classDef muted stroke:#94a3b8
```

`docs/diagrams/palette.dark.mmd`:

```
%% Dark palette: replaces the "%% palette" line of every flowchart (see render.sh). Same class names as palette.light.mmd.
  classDef kit fill:#172554,stroke:#60a5fa,stroke-width:1.5px,color:#e6e6eb
  classDef personal fill:#052e16,stroke:#4ade80,stroke-width:1.5px,color:#e6e6eb
  classDef claude fill:#431407,stroke:#fb923c,stroke-width:1.5px,color:#e6e6eb
  classDef engine fill:#422006,stroke:#fbbf24,stroke-width:2px,color:#e6e6eb
  classDef state fill:#1a1d27,stroke:#94a3b8,stroke-width:1.5px,stroke-dasharray:4 3,color:#e6e6eb
  classDef truth fill:#022c22,stroke:#34d399,stroke-width:2.5px,color:#e6e6eb
  classDef entry fill:#172554,stroke:#60a5fa,stroke-width:1.5px,color:#e6e6eb
  classDef notes fill:#2e1065,stroke:#a78bfa,stroke-width:1.5px,color:#e6e6eb
  classDef local fill:#1a1d27,stroke:#94a3b8,stroke-width:1.5px,stroke-dasharray:4 3,color:#e6e6eb
  classDef kitGroup fill:#60a5fa14,stroke:#60a5fa,stroke-width:1.5px
  classDef personalGroup fill:#4ade8014,stroke:#4ade80,stroke-width:1.5px
  classDef claudeGroup fill:#fb923c14,stroke:#fb923c,stroke-width:1.5px
  classDef engineGroup fill:#fbbf2414,stroke:#fbbf24,stroke-width:1.5px
  classDef notesGroup fill:#a78bfa14,stroke:#a78bfa,stroke-width:1.5px
  classDef emph stroke:#fbbf24,stroke-width:2.5px
  classDef truthLink stroke:#34d399,stroke-width:2.5px
  classDef muted stroke:#6b7280
```

- [ ] **Step 6: Write render.sh**

`docs/diagrams/render.sh` (then `chmod +x`):

```bash
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
```

Add to `.gitattributes`, after the `*.py` line:

```
# Diagram sources are hashed by docs/diagrams/render.sh; keep them byte-stable across platforms.
*.mmd text eol=lf
```

- [ ] **Step 7: Run the render tests**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_diagrams_render.py`
Expected: 9 passed.

Note: the stub writes its SVG without a trailing newline and awk adds one; `test_svg_records_the_hash_python_computes` checks only the prefix, so that is fine. If `test_engine_failure_writes_nothing` fails because a partial `.svg` exists, the move-after-stamp order in Step 6 was not followed.

- [ ] **Step 8: Smoke-test against the real image**

```bash
S=$(mktemp -d) && cp docs/diagrams/{render.sh,palette.*.mmd,theme.*.json} "$S" && printf 'flowchart LR\n  a e1@--> b\n  class a kit\n  class e1 emph\n%%%% palette\n' >"$S/smoke.mmd" && bash "$S/render.sh" smoke && grep -c foreignObject "$S/smoke.dark.svg"; grep -o 'diagram-source sha256:[0-9a-f]*' "$S/smoke.dark.svg"; rm -rf "$S"
```

Expected: two `wrote docs/diagrams/smoke.<variant>.svg` lines, `0` foreignObject, one `diagram-source sha256:` line. (The `wrote` path says `docs/diagrams/` even in the temp folder; that is cosmetic.)

- [ ] **Step 9: Full suite and commit**

Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: all pass.

```bash
git add .gitattributes docs/diagrams/render.sh docs/diagrams/theme.light.json docs/diagrams/theme.dark.json docs/diagrams/palette.light.mmd docs/diagrams/palette.dark.mmd tests/diagrams_support.py tests/test_diagrams_render.py
git commit -m "feat(diagrams): render Mermaid sources to light and dark SVG with a pinned mermaid-cli"
```

---

### Task 2: Diagram sources, rendered SVGs and the sync gate

**Files:**
- Create: `tests/test_diagrams.py`
- Create: `docs/diagrams/architecture-overview.mmd`, `architecture-daily-sync.mmd`, `toolset-workflow.mmd`, `documentation-layers.mmd`, `settings-merge.mmd`, and the ten rendered `.light.svg` / `.dark.svg`

**Interfaces:**
- Consumes: everything Task 1 produces (`diagrams_support`, `render.sh`, palette class names).
- Produces: five diagram names, used by Task 3's embeds: `architecture-overview`, `architecture-daily-sync`, `toolset-workflow`, `documentation-layers`, `settings-merge`.

- [ ] **Step 1: Write the failing gate tests (sources and SVGs)**

`tests/test_diagrams.py`:

```python
"""The docs' diagrams: Mermaid sources in docs/diagrams/, rendered SVGs that match them, and the embeds in the docs."""
import json
import re

from diagrams_support import DIAGRAMS, HASH_COMMENT, VARIANTS, image_ref, source_hash, sources

FIX = "run docs/diagrams/render.sh {name} and commit the source with both SVGs"
CLASS_USE = re.compile(r"^\s*class\s+\S+\s+(\w+)\s*$", re.M)
CLASS_DEF = re.compile(r"^\s*classDef\s+(\w+)\s", re.M)


def _body(text):
    """A source without its --- frontmatter."""
    return re.sub(r"\A---\n.*?\n---\n", "", text.replace("\r", ""), flags=re.S)


def _is_flowchart(name):
    body = _body((DIAGRAMS / f"{name}.mmd").read_text(encoding="utf-8"))
    first = next(line.strip() for line in body.splitlines() if line.strip() and not line.strip().startswith("%%"))
    return first.startswith(("flowchart", "graph"))


def test_there_are_diagrams():
    assert sources(), "docs/diagrams/ holds no diagram sources"


def test_every_svg_matches_its_source():
    image = image_ref(DIAGRAMS / "render.sh")
    problems = []
    for name in sources():
        for variant in VARIANTS:
            svg = DIAGRAMS / f"{name}.{variant}.svg"
            if not svg.exists():
                problems.append(f"{svg.name} is missing: " + FIX.format(name=name))
                continue
            found = HASH_COMMENT.findall(svg.read_text(encoding="utf-8"))
            if found != [source_hash(DIAGRAMS, name, variant, image)]:
                problems.append(f"{svg.name} is out of date: " + FIX.format(name=name))
    assert not problems, "\n".join(problems)


def test_no_svg_without_a_source():
    names = set(sources())
    orphans = []
    for svg in DIAGRAMS.glob("*.svg"):
        stem, _, variant = svg.name[: -len(".svg")].rpartition(".")
        if stem not in names or variant not in VARIANTS:
            orphans.append(svg.name)
    assert not orphans, f"SVGs without a <name>.mmd source (delete them or add the source): {orphans}"


def test_svgs_have_no_html_labels_or_external_resources():
    bad = []
    for svg in DIAGRAMS.glob("*.svg"):
        text = svg.read_text(encoding="utf-8")
        for needle in ("<foreignObject", "@import", "url(http"):
            if needle in text:
                bad.append(f"{svg.name}: {needle}")
    assert not bad, "image viewers drop HTML labels and cannot load external resources:\n" + "\n".join(bad)


def test_flowcharts_take_their_colours_from_the_palette():
    bad = []
    for name in filter(_is_flowchart, sources()):
        body = _body((DIAGRAMS / f"{name}.mmd").read_text(encoding="utf-8"))
        if not re.search(r"^\s*%% palette\s*$", body, re.M):
            bad.append(f"{name}: no '%% palette' line")
        for pattern in (r"^\s*classDef\b", r"^\s*style\b", r"^\s*linkStyle\b", r"#[0-9a-fA-F]{3,8}\b"):
            if re.search(pattern, body, re.M):
                bad.append(f"{name}: {pattern} (colours belong in palette.<variant>.mmd)")
    assert not bad, "\n".join(bad)


def test_palettes_define_every_class_used():
    defined = {v: set(CLASS_DEF.findall((DIAGRAMS / f"palette.{v}.mmd").read_text(encoding="utf-8"))) for v in VARIANTS}
    assert defined["light"] == defined["dark"], f"palettes differ: {defined['light'] ^ defined['dark']}"
    used = set()
    for name in sources():
        used |= set(CLASS_USE.findall((DIAGRAMS / f"{name}.mmd").read_text(encoding="utf-8")))
    assert used <= defined["light"], f"classes used but not in the palettes: {sorted(used - defined['light'])}"


def test_themes_render_svg_text_with_system_fonts():
    for variant in VARIANTS:
        theme = json.loads((DIAGRAMS / f"theme.{variant}.json").read_text(encoding="utf-8"))
        assert theme["theme"] == "base"
        assert theme["htmlLabels"] is False and theme["flowchart"]["htmlLabels"] is False
        assert theme["themeVariables"]["fontFamily"].startswith("ui-sans-serif, system-ui")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_diagrams.py`
Expected: `test_there_are_diagrams` FAILS ("holds no diagram sources"); the rest pass vacuously.

- [ ] **Step 3: Write the five sources**

Content is moved from the docs unchanged; only colour lines change. Edge IDs replace `linkStyle` indexes (index 4 of the architecture flowchart is `kBase ==> merge`, and so on).

`docs/diagrams/architecture-overview.mmd` (from `docs/explanation/architecture.md`, first block):

```
---
config:
  look: neo
  flowchart:
    curve: basis
    nodeSpacing: 24
    rankSpacing: 80
    wrappingWidth: 320
---
flowchart LR
  subgraph KIT["Kit repo · shared by everyone"]
    direction TB
    kPlugin["`**plugins/loadout/**
    hooks · skills · MCP servers`"]
    kRules["`**rules/**
    how Claude uses the tools`"]
    kBase["`**settings.base.json**
    the keys loadout manages`"]
  end

  subgraph PER["Personal layer · your git repo"]
    direction TB
    pRules["`**rules/**
    me.md, your preferences`"]
    pSkills["`**skills/ · hooks/**`"]
    pSet["`**settings.json**
    your overrides`"]
    pMcp["`**mcp.json**
    your MCP servers`"]
  end

  merge{{"`**three-way merge**`"}}
  snap[("`**~/.claude/.loadout/**
  snapshot of the last merge`")]

  subgraph CC["Claude Code configuration"]
    direction TB
    cPlugin["`**~/.claude/plugins/**
    the loadout plugin`"]
    cRulesK["`**~/.claude/rules/loadout**`"]
    cRulesP["`**~/.claude/rules/personal**`"]
    cSkills["`**~/.claude/skills/**
    **~/.claude/hooks/personal/**`"]
    cSet["`**~/.claude/settings.json**`"]
    cMcp["`**~/.claude.json**
    user-scope MCP servers`"]
  end

  kPlugin -. "Claude Code installs and auto-updates" .-> cPlugin
  kRules -- link --> cRulesK
  pRules -- link --> cRulesP
  pSkills -- link --> cSkills
  kBase e4@==> merge
  pSet e5@==> merge
  snap <-. "read, then rewrite" .-> merge
  merge e7@==> cSet
  pMcp -- "claude mcp add-json" --> cMcp

  class kPlugin,kRules,kBase kit
  class pRules,pSkills,pSet,pMcp personal
  class cPlugin,cRulesK,cRulesP,cSkills,cSet,cMcp claude
  class merge engine
  class snap state
  class KIT kitGroup
  class PER personalGroup
  class CC claudeGroup
  class e4,e5,e7 emph
%% palette
```

`docs/diagrams/architecture-daily-sync.mmd` (second block of `architecture.md`, verbatim):

```
sequenceDiagram
  autonumber
  box rgba(234, 88, 12, 0.10) Claude Code
    participant S as Session
  end
  box rgba(37, 99, 235, 0.10) loadout
    participant H as hook-session-start
    participant M as maintenance
  end
  box rgba(22, 163, 74, 0.10) Your machine
    participant G as Kit and personal repos
    participant C as ~/.claude
  end

  S->>H: session starts
  H-->>S: queued notices
  opt daily pull or weekly check due
    H-)M: start detached
    Note over S,H: the session does not wait
    activate M
    Note over M: one run at a time
    opt daily, unless LOADOUT_NO_AUTO_PULL=1
      M->>G: git pull --ff-only
      Note over G: skips a checkout with<br/>uncommitted changes
      G-->>M: new commits, or none
      opt new commits arrived
        M->>C: merge settings, add personal MCP
        M->>C: relink skills and hook scripts
      end
    end
    opt weekly
      M->>M: check tool versions
      Note right of M: notice only,<br/>never installs
    end
    M--)H: queue notices for the next session
    deactivate M
  end
```

`docs/diagrams/toolset-workflow.mmd` (from `docs/explanation/the-toolset.md`):

```
---
config:
  look: neo
  flowchart:
    curve: basis
    nodeSpacing: 26
    rankSpacing: 46
    wrappingWidth: 300
---
flowchart TB
  idea(["`**An idea or a bug**`"])

  subgraph THINK["Think first"]
    direction LR
    brain["`**brainstorming**
    asks, proposes, writes a spec`"]
    plan["`**writing-plans**
    bite-sized, test-first tasks`"]
    adv["`**execution-advisor**
    inline, subagents or both`"]
    brain --> plan --> adv
  end

  subgraph BUILD["Build"]
    direction LR
    tdd["`**test-driven build**
    red, green, commit`"]
    know["`**Know the code**
    codebase-memory · Serena
    LSP diagnostics`"]
    docs["`**Know the libraries**
    Context7 · Microsoft Learn`"]
    ui["`**UI work**
    frontend-design · playwright-cli
    impeccable`"]
    tdd ~~~ know ~~~ docs ~~~ ui
  end

  subgraph FINISH["Finish"]
    direction LR
    rev["`**Review**
    /code-review · security-guidance`"]
    sync["`**/loadout:docs-sync**
    docs stay true`"]
    ship["`**commit-commands**
    commit, push, PR`"]
    rev --> sync --> ship
  end

  rtk[("`**rtk**
  shrinks command output
  in every step`")]

  idea --> THINK
  THINK ==> BUILD
  BUILD ==> FINISH
  rtk -.- BUILD

  class adv,sync kit
  class brain,plan,tdd,rev,ship claude
  class know,docs,ui engine
  class idea,rtk state
  class THINK claudeGroup
  class BUILD engineGroup
  class FINISH kitGroup
%% palette
```

`docs/diagrams/documentation-layers.mmd` (from `docs/explanation/documentation-strategy.md`; `entry`/`local` keep their own names although they share colours with `kit`/`state`):

```
---
config:
  look: neo
  flowchart:
    curve: basis
    nodeSpacing: 30
    rankSpacing: 70
    wrappingWidth: 320
---
flowchart LR
  subgraph ENTRY["Entry points"]
    direction TB
    readme["`**README.md**
    what it is · install · run`"]
    claude["`**CLAUDE.md**
    one line: @AGENTS.md`"]
    agents["`**AGENTS.md**
    purpose · commands
    conventions · map`"]
  end

  subgraph NOTES["Agent notes"]
    memories["`**.serena/memories/**
    one summary and link per topic
    gotchas · recipes`"]
  end

  docs[("`**docs/**
  single source of truth
  tutorials · how-tos · reference
  explanation · ADRs`")]

  auto["`**Claude Code auto memory**
  machine-local notes only`"]

  claude -- imports --> agents
  agents -- maps --> memories
  readme e2@-- links into --> docs
  agents e3@-- links into --> docs
  memories e4@-- links into --> docs
  auto e5@-. "never project facts" .-x docs

  class docs truth
  class readme,claude,agents entry
  class memories notes
  class auto local
  class ENTRY kitGroup
  class NOTES notesGroup
  class e2,e3,e4 truthLink
  class e5 muted
%% palette
```

`docs/diagrams/settings-merge.mmd` (from `docs/reference/settings-merge.md`):

```
---
config:
  look: neo
  flowchart:
    curve: basis
    nodeSpacing: 30
    rankSpacing: 45
    wrappingWidth: 320
---
flowchart TB
  base["`**settings.base.json**
  from the kit`"]
  pers["`**settings.json**
  from your personal layer`"]
  des(["`**desired**
  your values win`"])
  prev[("`**previous**
  managed-settings.json
  applied last time`")]
  cur["`**current**
  ~/.claude/settings.json`"]

  subgraph ENG["merge"]
    direction LR
    km["`**Key merge** (every key except hooks)
    desired wins
    drops what the kit dropped, unless you changed it`"]
    hm["`**Hook merge** (per hook)
    add · update · keep yours
    tombstones keep deleted hooks deleted`"]
  end

  out["`**~/.claude/settings.json**
  written only if it changed`"]
  snap[("`**new snapshot**
  desired keys · applied hooks
  tombstones`")]

  base --> des
  pers --> des
  des e2@==> ENG
  prev --> ENG
  cur --> ENG
  ENG e5@==> out
  ENG -.-> snap

  class base kit
  class pers personal
  class des engine
  class cur,out claude
  class km,hm engine
  class prev,snap state
  class ENG engineGroup
  class e2,e5 emph
%% palette
```

- [ ] **Step 4: Render**

Run: `docs/diagrams/render.sh`
Expected: ten `wrote docs/diagrams/<name>.<variant>.svg` lines, exit 0. If mermaid-cli reports a parse error, the edge-ID syntax on that line is the first suspect (compare with the lines verified in Task 1 Step 8); fix the source, keep the content.

- [ ] **Step 5: Run the gate**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_diagrams.py tests/test_diagrams_render.py`
Expected: all pass (7 + 9).

Quick check that the edge classes landed: `grep -c 'stroke:#fbbf24' docs/diagrams/architecture-overview.dark.svg` prints at least 1, and `grep -c 'font-weight="bold"' docs/diagrams/architecture-overview.light.svg` prints more than 0 (bold first lines survive without HTML labels).

- [ ] **Step 6: Full suite and commit**

Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: all pass.

```bash
git add tests/test_diagrams.py docs/diagrams/*.mmd docs/diagrams/*.svg
git commit -m "docs(diagrams): move the five diagrams into sources and render them"
```

---

### Task 3: Embed the SVGs in the docs

**Files:**
- Modify: `tests/test_diagrams.py` (append the embed tests)
- Modify: `docs/explanation/architecture.md` (lines 5-78 and 105-143), `docs/explanation/the-toolset.md` (7-77), `docs/explanation/documentation-strategy.md` (29-84), `docs/reference/settings-merge.md` (13-73)

**Interfaces:**
- Consumes: the five names from Task 2; `DIAGRAMS`, `sources()` from Task 1.

- [ ] **Step 1: Append the failing embed tests**

Add to `tests/test_diagrams.py` (the imports go at the top of the file):

```python
from loadout import paths

ROOT = paths.kit_root()
PICTURE = re.compile(r"<picture>(.*?)</picture>", re.S)
SOURCE = re.compile(r'<source media="\(prefers-color-scheme: dark\)" srcset="([^"]+)">')
IMG = re.compile(r'<img alt="([^"]*)" src="([^"]+)">')
SOURCE_LINK = re.compile(r"</picture>\n\n<sub>\[Source\]\(([^)]+)\)</sub>")


def _docs():
    """README.md and docs/, without the agents' working documents."""
    files = [ROOT / "README.md", *ROOT.glob("docs/**/*.md")]
    return [f for f in files if "docs/superpowers/" not in f.relative_to(ROOT).as_posix()]


def test_no_mermaid_code_blocks_left():
    left = [str(f.relative_to(ROOT)) for f in _docs() if re.search(r"^\s*```+\s*mermaid", f.read_text(encoding="utf-8"), re.M)]
    assert not left, f"render diagrams to SVG (docs/diagrams/) instead of Mermaid code blocks: {left}"


def test_embeds_show_both_variants_with_alt_text():
    bad = []
    for md in _docs():
        for block in PICTURE.findall(md.read_text(encoding="utf-8")):
            where = md.relative_to(ROOT)
            src, img = SOURCE.search(block), IMG.search(block)
            if not (src and img):
                bad.append(f"{where}: <picture> needs a dark <source> and <img alt src> as in CONTRIBUTING.md")
                continue
            dark, (alt, light) = src.group(1), img.groups()
            if not (dark.endswith(".dark.svg") and light.endswith(".light.svg")
                    and dark[: -len(".dark.svg")] == light[: -len(".light.svg")]):
                bad.append(f"{where}: {dark} and {light} are not one diagram's two variants")
            for ref in (dark, light):
                if not (md.parent / ref).exists():
                    bad.append(f"{where}: {ref} does not exist")
            if len(alt.strip()) < 40 or alt.strip().lower().startswith("diagram"):
                bad.append(f"{where}: alt text must say what the diagram shows ({alt!r})")
    assert not bad, "\n".join(bad)


def test_each_embed_links_its_source():
    bad = []
    for md in _docs():
        text = md.read_text(encoding="utf-8").replace("\r", "")
        pictures = len(PICTURE.findall(text))
        links = SOURCE_LINK.findall(text)
        if len(links) != pictures:
            bad.append(f"{md.relative_to(ROOT)}: each </picture> needs a blank line, then <sub>[Source](….mmd)</sub>")
        bad += [f"{md.relative_to(ROOT)}: {ref} does not exist" for ref in links if not (md.parent / ref).exists()]
    assert not bad, "\n".join(bad)


def test_every_diagram_is_embedded():
    embedded = set()
    for md in _docs():
        for light in IMG.findall(md.read_text(encoding="utf-8")):
            embedded.add((md.parent / light[1]).resolve())
    missing = [n for n in sources() if (DIAGRAMS / f"{n}.light.svg").resolve() not in embedded]
    assert not missing, f"diagrams no page shows (embed or delete them): {missing}"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_diagrams.py`
Expected: `test_no_mermaid_code_blocks_left` FAILS listing the four pages; `test_every_diagram_is_embedded` FAILS listing all five names; the other two pass vacuously.

- [ ] **Step 3: Replace each code block with its embed**

Replace the whole fenced block (from ```` ```mermaid ```` to its closing ```` ``` ````) with the snippet below. Keep one blank line before `<picture>` and the blank line between `</picture>` and `<sub>`. Paths are `../diagrams/` from both `docs/explanation/` and `docs/reference/`.

`docs/explanation/architecture.md`, first block:

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../diagrams/architecture-overview.dark.svg">
  <img alt="Claude Code installs the kit's plugin and the kit's rules are linked into ~/.claude/rules/loadout. Your personal layer's rules, skills and hooks are linked into ~/.claude, and its mcp.json is added with claude mcp add-json. settings.base.json and your settings.json go through a three-way merge, which reads and rewrites a snapshot and writes ~/.claude/settings.json." src="../diagrams/architecture-overview.light.svg">
</picture>

<sub>[Source](../diagrams/architecture-overview.mmd)</sub>
```

`docs/explanation/architecture.md`, second block:

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../diagrams/architecture-daily-sync.dark.svg">
  <img alt="When a session starts, hook-session-start returns queued notices at once and, when due, starts maintenance in the background without making the session wait. Maintenance runs one at a time: daily it runs git pull --ff-only on the kit and personal repos (skipping a checkout with uncommitted changes) and, after new commits, merges settings and relinks skills and hooks; weekly it checks tool versions without installing anything. It queues notices for the next session." src="../diagrams/architecture-daily-sync.light.svg">
</picture>

<sub>[Source](../diagrams/architecture-daily-sync.mmd)</sub>
```

`docs/explanation/the-toolset.md`:

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../diagrams/toolset-workflow.dark.svg">
  <img alt="An idea or a bug goes through three stages. Think first: brainstorming, writing-plans, then execution-advisor. Build: a test-driven build, with codebase-memory, Serena and LSP diagnostics for the code, Context7 and Microsoft Learn for libraries, and frontend-design, playwright-cli and impeccable for UI work. Finish: review, /loadout:docs-sync, then commit-commands. rtk shrinks command output in every step." src="../diagrams/toolset-workflow.light.svg">
</picture>

<sub>[Source](../diagrams/toolset-workflow.mmd)</sub>
```

`docs/explanation/documentation-strategy.md`:

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../diagrams/documentation-layers.dark.svg">
  <img alt="CLAUDE.md imports AGENTS.md, and AGENTS.md maps the Serena memories. README.md, AGENTS.md and the memories all link into docs/, the single source of truth. Claude Code's auto memory holds machine-local notes only, never project facts." src="../diagrams/documentation-layers.light.svg">
</picture>

<sub>[Source](../diagrams/documentation-layers.mmd)</sub>
```

`docs/reference/settings-merge.md`:

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../diagrams/settings-merge.dark.svg">
  <img alt="settings.base.json from the kit and settings.json from your personal layer combine into the desired settings, where your values win. The merge takes the desired settings, the previous snapshot and the current ~/.claude/settings.json; a key merge and a per-hook merge write ~/.claude/settings.json only if it changed, and save a new snapshot." src="../diagrams/settings-merge.light.svg">
</picture>

<sub>[Source](../diagrams/settings-merge.mmd)</sub>
```

Then read the sentences right around each embed: if one says "the diagram below" or refers to colours ("the orange boxes"), check it still holds; the colours are the same hues in both variants.

- [ ] **Step 4: Run the gate and the link check**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_diagrams.py tests/test_repo_static.py`
Expected: all pass (`test_relative_links_resolve` covers the new `[Source]` links).

- [ ] **Step 5: Full suite and commit**

Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: all pass.

```bash
git add tests/test_diagrams.py docs/explanation/architecture.md docs/explanation/the-toolset.md docs/explanation/documentation-strategy.md docs/reference/settings-merge.md
git commit -m "docs: embed the rendered diagrams with light and dark variants"
```

---

### Task 4: Contributor docs

**Files:**
- Create: `docs/diagrams/README.md`
- Modify: `CONTRIBUTING.md` (new "Diagrams" section after "Documentation"), `AGENTS.md` (the `docs/` map line), `docs/explanation/documentation-strategy.md` (only if it states how diagrams are stored; today it does not, see `grep -n -i "mermaid\|diagram"`)

- [ ] **Step 1: Add the CONTRIBUTING section**

Insert after the "## Documentation" section of `CONTRIBUTING.md`:

````markdown
## Diagrams

The diagrams in `docs/` are Mermaid sources in [`docs/diagrams/`](docs/diagrams/README.md), rendered to one light and one dark SVG each, so they show on every viewer (phone apps, editor previews, other forges) and fit both colour schemes. To change one:

1. Edit `docs/diagrams/<name>.mmd`. Flowcharts take their colours from classes (`class nodeId kit`, `class SUBGRAPH kitGroup`, `class e4 emph` for an edge written `a e4@--> b`); the colours are in `palette.light.mmd` and `palette.dark.mmd`, the fonts and base colours in `theme.light.json` and `theme.dark.json`. A flowchart ends with the line `%% palette`.
2. Render: `docs/diagrams/render.sh <name>` (no name renders all). It runs a pinned mermaid-cli in a container without network access: podman, or `DIAGRAMS_ENGINE=docker`.
3. Commit the source and both SVGs together.

Each SVG records a hash of its source, palette, theme and the mermaid-cli version. `tests/test_diagrams.py` fails when an SVG is out of date and names the command that fixes it. It also rejects Mermaid code blocks in the docs. Embed a new diagram like this, with alt text that says what the diagram shows:

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../diagrams/<name>.dark.svg">
  <img alt="What a reader learns from the diagram, in a sentence or two." src="../diagrams/<name>.light.svg">
</picture>

<sub>[Source](../diagrams/<name>.mmd)</sub>
```
````

- [ ] **Step 2: Write `docs/diagrams/README.md`**

```markdown
# Diagrams

Sources and rendered images of the diagrams in the docs. Each `<name>.mmd` has a `<name>.light.svg` and a `<name>.dark.svg`; never edit an SVG by hand.

| File | Holds |
|---|---|
| `<name>.mmd` | the diagram (Mermaid) |
| `palette.light.mmd`, `palette.dark.mmd` | the colour classes flowcharts use |
| `theme.light.json`, `theme.dark.json` | fonts and base colours (mermaid-cli config) |
| `render.sh` | renders the SVGs: `docs/diagrams/render.sh [NAME...]` |

How to edit, render and embed: [CONTRIBUTING.md](../../CONTRIBUTING.md#diagrams).
```

- [ ] **Step 3: Update the AGENTS.md map**

In the `docs/` line of `AGENTS.md`, after `` `examples/`, `` insert `` `diagrams/` (Mermaid sources and their rendered SVGs; see CONTRIBUTING.md), ``.

- [ ] **Step 4: Run the link check and the full suite**

Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: all pass, including `test_relative_links_resolve` for `CONTRIBUTING.md#diagrams` and `docs/diagrams/README.md`.

- [ ] **Step 5: Commit**

```bash
git add CONTRIBUTING.md docs/diagrams/README.md AGENTS.md
git commit -m "docs(contributing): how to edit, render and embed diagrams"
```

(Add `docs/explanation/documentation-strategy.md` to the commit only if Step 1's grep showed a statement that needed changing.)

---

### Task 5: Visual verification

**Files:**
- Possibly modify: `docs/diagrams/palette.*.mmd`, `docs/diagrams/theme.*.json` (only to fix what the screenshots show), re-rendered SVGs.
- Scratch only: `$SCRATCH/harness/` (session scratchpad, not committed).

- [ ] **Step 1: Build a harness page**

`$SCRATCH/harness/index.html`, with `$SCRATCH/harness/diagrams` a symlink to the repo's `docs/diagrams`. It shows each diagram three ways: the light SVG on white, the dark SVG on GitHub's dark `#0d1117`, and a `<picture>` exactly as the docs embed it (switches with the emulated colour scheme). Images get `max-width: 100%` like GitHub's markdown CSS.

```html
<!doctype html>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Diagram check</title>
<style>
  body { margin: 0; padding: 16px; font: 14px system-ui; background: #fff; color: #1f2328; }
  @media (prefers-color-scheme: dark) { body { background: #0d1117; color: #e6edf3; } }
  section { margin-bottom: 32px; } img { max-width: 100%; display: block; }
  .light { background: #fff; padding: 12px; } .dark { background: #0d1117; padding: 12px; }
</style>
<script type="module">
  const names = ["architecture-overview", "architecture-daily-sync", "toolset-workflow", "documentation-layers", "settings-merge"];
  document.body.innerHTML = names.map(n => `<section><h2>${n}</h2>
    <div class="light"><img src="diagrams/${n}.light.svg"></div>
    <div class="dark"><img src="diagrams/${n}.dark.svg"></div>
    <h3>as embedded</h3><picture><source media="(prefers-color-scheme: dark)" srcset="diagrams/${n}.dark.svg"><img src="diagrams/${n}.light.svg"></picture>
  </section>`).join("");
</script>
```

Serve it: `python3 -m http.server --bind 127.0.0.1 8765 -d "$SCRATCH/harness"` (run in background).

- [ ] **Step 2: Screenshot at 320, 768 and 1280 px in light and dark**

```bash
for w in 320 768 1280; do for s in light dark; do
  playwright-cli screenshot --viewport-size "$w,900" --color-scheme "$s" --full-page --wait-for-timeout 500 http://127.0.0.1:8765/ "$SCRATCH/shots/$w-$s.png"
done; done
```

Expected: six PNGs. Open them (Read) one at a time and check, for every diagram:
- every label is readable (no blank boxes, no text overflowing a node, bold first lines bold);
- in dark, node text is light on a dark fill, edge labels are not on a white box, arrows and cluster titles are visible;
- emphasised edges are amber (architecture, settings merge) and green (documentation layers), the "never project facts" edge muted;
- the "as embedded" copy switches between light and dark with the scheme;
- at 320 px the images scale down without horizontal scrolling of the page (wide diagrams become small; that is expected and is what GitHub does).

- [ ] **Step 3: Fix what the screenshots show, then re-check**

Change only palettes or themes (never diagram content), re-run `docs/diagrams/render.sh`, re-run Step 2 for the affected scheme, and look again. Ledger every colour change with the reason.

- [ ] **Step 4: Full suite and commit (only if Step 3 changed anything)**

Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: all pass.

```bash
git add docs/diagrams/
git commit -m "fix(diagrams): <what the screenshot showed, e.g. lighter edge labels in dark mode>"
```

- [ ] **Step 5: Stop the server; leave the scratch harness out of the repo**

Kill the background `http.server`. `git status` shows a clean tree.

---

## After the tasks

- `/loadout:docs-sync` over the branch.
- Final whole-branch review (one pass).
- With the user's OK: push and open the PR; then look at the four pages on github.com in light and dark (desktop and the mobile app) and report what you saw.
