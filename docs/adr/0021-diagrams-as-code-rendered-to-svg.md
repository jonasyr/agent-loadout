# 0021. Diagrams as code, rendered to committed SVGs

- Status: Accepted
- Date: 2026-10-12
- Source: [Diagrams as code design](../superpowers/specs/2026-10-12-diagrams-as-code-design.md)

## Context
The docs held their diagrams as Mermaid code blocks. GitHub's website renders those, but phone apps, editor previews, offline copies and other forges show raw code, and the hard-coded light colours looked wrong in dark mode.

## Decision
Each diagram's Mermaid source lives in `docs/diagrams/<name>.mmd` without colours; flowcharts use semantic classes whose colours come from a light and a dark palette. `docs/diagrams/render.sh` renders every source to a light and a dark SVG with a mermaid-cli container pinned by version and digest, without network access. Each SVG records a hash of its source, palette, theme, `render.sh` and the image, and `tests/test_diagrams.py` fails when an SVG no longer matches or a page still contains a Mermaid code block. Pages embed both variants with `<picture>`, alt text and a link to the source.

## Alternatives considered
- Mermaid code blocks: no build step, but they do not render outside github.com and cannot follow the colour scheme.
- Rendering in CI and committing from there: needs a bot with write access and a container in every CI run; a local render plus a hash test gives the same guarantee.
- A pre-commit hook: the repo has no pre-commit framework, and the test already runs in CI.

## Consequences
- Changing a diagram needs podman or docker locally ([CONTRIBUTING](../../CONTRIBUTING.md#diagrams)).
- The SVGs are binary-like diffs in review; the `.mmd` diff is what reviewers read.

## In the code
- `docs/diagrams/` (the `.mmd` sources and their SVGs), `docs/diagrams/render.sh`
- `tests/test_diagrams.py`
