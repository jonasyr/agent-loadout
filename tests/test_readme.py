"""The README's hero, link row and install routes, and the wordmark it shows."""
import re
import subprocess
import sys

import pytest

from loadout import paths

ROOT = paths.kit_root()
ASSETS = ROOT / "docs" / "assets"
WORDMARKS = [ASSETS / "wordmark.light.svg", ASSETS / "wordmark.dark.svg"]


def test_wordmarks_are_outlines():
    for svg in WORDMARKS:
        text = svg.read_text(encoding="utf-8")
        assert "<title>loadout</title>" in text and 'role="img"' in text and "viewBox=" in text
        for needle in ("<text", "font-family", "@import", "url(", "href="):
            assert needle not in text, f"{svg.name}: {needle} (letters must be outlines, nothing loaded)"


def test_wordmark_variants_use_the_agreed_colours():
    light, dark = (s.read_text(encoding="utf-8") for s in WORDMARKS)
    assert all(c in light for c in ('fill="#7c3aed"', 'stroke="#ffffff"', 'fill="#0f172a"'))
    assert all(c in dark for c in ('fill="#a78bfa"', 'stroke="#0f1117"', 'fill="#e6e6eb"'))


@pytest.mark.skipif(sys.platform != "linux", reason="uses fc-match from fontconfig")
def test_font_lookup_refuses_other_fonts(tmp_path):
    """fc-match falls back to any font; the script must not draw the wordmark in it."""
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "fc-match").write_text("#!/bin/sh\nprintf /usr/share/fonts/TTF/DejaVuSans-Bold.ttf\n", encoding="utf-8")
    (fake / "fc-match").chmod(0o755)
    # font_path sits above the fontTools imports, so it runs without fontTools (tests have only pytest)
    code = (
        "src = open('docs/assets/wordmark.py').read().split('from fontTools')[0];"
        "ns = {'__name__': 'wordmark'}; exec(src, ns); ns['font_path'](['wordmark.py'])"
    )
    p = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True,
                       env={"PATH": f"{fake}:/usr/bin:/bin"}, timeout=30)
    assert p.returncode != 0 and "JetBrains Mono" in p.stderr
