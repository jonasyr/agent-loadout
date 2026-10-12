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
