"""Generates docs/assets/wordmark.{light,dark}.svg: a violet tile with a chevron, then "loadout" in JetBrains Mono Bold.

The letters become outlines, so the SVG needs no font and looks the same in every viewer (an image cannot load web
fonts). JetBrains Mono is under the SIL Open Font License, which permits this. Maintainer tool, not part of the CLI:
    uv run --with fonttools docs/assets/wordmark.py [FONT]
FONT defaults to the JetBrains Mono Bold that fontconfig finds (fc-match).
"""
import subprocess
import sys
from pathlib import Path


def font_path(argv):
    """The font file: the argument, else fontconfig's JetBrains Mono Bold; refuses a fallback font."""
    if len(argv) > 1:
        return argv[1]
    found = subprocess.run(["fc-match", "-f", "%{file}", "JetBrains Mono:style=Bold"],
                           capture_output=True, text=True, check=True).stdout
    if "JetBrainsMono" not in Path(found).name.replace(" ", ""):
        sys.exit(f"JetBrains Mono Bold is not installed (fontconfig offered {found}); pass the .ttf path as an argument")
    return found


from fontTools.pens.svgPathPen import SVGPathPen  # noqa: E402  (font_path above must work without fontTools)
from fontTools.pens.transformPen import TransformPen  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402

HERE = Path(__file__).resolve().parent
WORD = "loadout"
SIZE = 64  # font size in px
TILE = 72  # tile edge in px
GAP = 18  # space between tile and word
VARIANTS = {
    "light": {"tile": "#7c3aed", "chevron": "#ffffff", "text": "#0f172a"},
    "dark": {"tile": "#a78bfa", "chevron": "#0f1117", "text": "#e6e6eb"},
}


def word_path(font):
    """The word's outline as one SVG path with its baseline at y=0; returns (d, width, cap height)."""
    glyphs, cmap = font.getGlyphSet(), font.getBestCmap()
    scale = SIZE / font["head"].unitsPerEm
    pen = SVGPathPen(glyphs)
    x = 0
    for ch in WORD:
        name = cmap[ord(ch)]
        glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, x, 0)))
        x += glyphs[name].width * scale
    return pen.getCommands(), x, font["OS/2"].sCapHeight * scale


def svg(variant, d, width, cap):
    c = VARIANTS[variant]
    total = TILE + GAP + width
    base = (TILE + cap) / 2  # centres the cap height on the tile
    cx, cy, a = TILE / 2 + 3, TILE / 2, 13  # the chevron: two strokes meeting at a point
    chevron = f"M{cx - a / 1.4:.1f} {cy - a:.1f} L{cx + a / 1.4:.1f} {cy:.1f} L{cx - a / 1.4:.1f} {cy + a:.1f}"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total:.1f} {TILE}" width="{total:.0f}" height="{TILE}" role="img">\n'
        f"<title>loadout</title>\n"
        f'<rect width="{TILE}" height="{TILE}" rx="16" fill="{c["tile"]}"/>\n'
        f'<path d="{chevron}" fill="none" stroke="{c["chevron"]}" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>\n'
        f'<path transform="translate({TILE + GAP} {base:.1f})" fill="{c["text"]}" d="{d}"/>\n'
        f"</svg>\n"
    )


def main(argv):
    font = TTFont(font_path(argv))
    d, width, cap = word_path(font)
    for variant in VARIANTS:
        (HERE / f"wordmark.{variant}.svg").write_text(svg(variant, d, width, cap), encoding="utf-8", newline="\n")
        print(f"wrote docs/assets/wordmark.{variant}.svg")


if __name__ == "__main__":
    main(sys.argv)
