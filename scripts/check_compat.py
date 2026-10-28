"""Gate: every master must have identical outline structure, or the VF cannot interpolate.

Compares, per glyph: composite components, contour end points, and on/off-curve flags.
Exit code 1 on any mismatch.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

from fontTools.ttLib import TTFont


def signature(font: TTFont, name: str) -> tuple:
    glyf = font["glyf"]
    glyph = glyf[name]
    if glyph.isComposite():
        return ("composite", tuple(c.glyphName for c in glyph.components))
    if glyph.numberOfContours <= 0:
        return ("empty",)
    _, end_pts, flags = glyph.getCoordinates(glyf)
    return ("simple", tuple(end_pts), tuple(f & 1 for f in flags))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=pathlib.Path)
    args = ap.parse_args()

    paths = sorted(args.folder.glob("*.ttf"))
    if len(paths) < 2:
        sys.exit(f"need at least 2 masters in {args.folder}")
    fonts = [TTFont(p) for p in paths]
    ref = fonts[0]

    bad: list[str] = []
    for name in ref.getGlyphOrder():
        sig = signature(ref, name)
        for path, font in zip(paths[1:], fonts[1:]):
            if name not in font["glyf"].glyphs or signature(font, name) != sig:
                bad.append(f"{name} differs in {path.name}")

    total = len(ref.getGlyphOrder())
    if bad:
        print(f"FAIL: {len(bad)} incompatible glyphs out of {total}")
        for line in bad[:50]:
            print("  " + line)
        sys.exit(1)
    print(f"OK: {total} glyphs point-compatible across {len(paths)} masters")


if __name__ == "__main__":
    main()
