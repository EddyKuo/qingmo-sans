"""Apply the ordered geometric transforms from spec.yaml to every master.

Contract for every transform module:
    transform(glyph_name, points, end_pts, flags, params, wght) -> list[(x, y)]
It may move points but must return exactly as many points as it received; contours and
on/off-curve flags are untouched. The pipeline enforces this so VF interpolation survives.
"""
from __future__ import annotations

import argparse
import importlib
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fontTools.ttLib import TTFont  # noqa: E402
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates  # noqa: E402

from common import BUILD, load_spec  # noqa: E402


class ContractError(RuntimeError):
    pass


def apply(font: TTFont, transforms: list, params: dict, wght: float) -> int:
    glyf = font["glyf"]
    changed = 0
    for name in font.getGlyphOrder():
        glyph = glyf[name]
        if glyph.isComposite() or glyph.numberOfContours <= 0:
            continue
        coords, end_pts, flags = glyph.getCoordinates(glyf)
        points = [tuple(p) for p in coords]
        original = list(points)
        for module in transforms:
            new = module.transform(name, points, list(end_pts), list(flags), params, wght)
            if len(new) != len(points):
                raise ContractError(f"{module.__name__} changed point count of {name}")
            points = [(round(x), round(y)) for x, y in new]
        if points != original:
            glyph.coordinates = GlyphCoordinates(points)
            glyph.recalcBounds(glyf)
            changed += 1
    return changed


def main() -> None:
    spec = load_spec()
    ap = argparse.ArgumentParser()
    ap.add_argument("--indir", type=pathlib.Path, default=BUILD / "masters")
    ap.add_argument("--outdir", type=pathlib.Path, default=BUILD / "transformed")
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    transforms = [importlib.import_module(n) for n in spec["transforms"]]
    for path in sorted(args.indir.glob("master-wght*.ttf")):
        wght = float(path.stem.removeprefix("master-wght"))
        font = TTFont(path)
        changed = apply(font, transforms, spec["style"], wght)
        out = args.outdir / path.name
        font.save(out)
        print(f"{out}: {changed} glyphs changed")


if __name__ == "__main__":
    main()
