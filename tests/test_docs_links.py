"""Every relative link and #anchor in the human docs resolves; the Codex plugin manifest points at real files."""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
BROKEN_ON_PURPOSE = DOCS / "examples" / "docs-audit-before-after" / "before"  # the audit example's "before" state
FILES = sorted([ROOT / "README.md", ROOT / "AGENTS.md", ROOT / "CONTRIBUTING.md",
                *(p for p in DOCS.rglob("*.md")
                  if p.relative_to(DOCS).parts[0] != "superpowers" and not p.is_relative_to(BROKEN_ON_PURPOSE))])
FENCE = re.compile(r"^(```|~~~)[^\n]*\n.*?^\1[ \t]*$", re.S | re.M)
CODE = re.compile(r"`[^`\n]*`")
MD_LINK = re.compile(r"\]\(<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\)")
HTML_LINK = re.compile(r"""\b(?:href|src|srcset)=["']([^"']+)["']""")
HEADING = re.compile(r"^#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$", re.M)
HTML_ID = re.compile(r"""\b(?:id|name)=["']([^"']+)["']""")


def _slug(text: str) -> str:
    """GitHub's heading anchor: lower case, markup and punctuation dropped, spaces to hyphens."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # [label](url) -> label
    text = re.sub(r"<[^>]+>", "", text).replace("`", "").lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(path: Path) -> set[str]:
    text = FENCE.sub("", path.read_text(encoding="utf-8"))
    out, seen = set(), {}
    for m in HEADING.finditer(text):
        slug = _slug(m.group(1))
        n = seen.get(slug, 0)
        seen[slug] = n + 1
        out.add(slug if n == 0 else f"{slug}-{n}")
    out.update(HTML_ID.findall(text))
    return out


def _targets(path: Path) -> list[str]:
    text = CODE.sub("", FENCE.sub("", path.read_text(encoding="utf-8")))
    return MD_LINK.findall(text) + HTML_LINK.findall(text)


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_links_resolve(path):
    bad = []
    for target in _targets(path):
        if re.match(r"[a-z][a-z0-9+.-]*:", target):  # https:, mailto:, ...
            continue
        file_part, _, anchor = target.partition("#")
        dest = (path.parent / file_part).resolve() if file_part else path
        if not dest.exists():
            bad.append(f"{target}: no such file")
        elif anchor and dest.suffix == ".md" and anchor not in anchors(dest):
            bad.append(f"{target}: no heading #{anchor} in {dest.relative_to(ROOT)}")
    assert not bad, "\n".join(bad)


def test_codex_manifest_points_at_real_files():
    plugin = ROOT / "plugins" / "loadout"
    data = json.loads((plugin / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert data.get("name") == "loadout" and data.get("description")
    for key in ("skills", "mcpServers", "hooks"):
        assert (plugin / data[key]).exists(), f"{key}: {data[key]} does not exist"
