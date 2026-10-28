"""Print the facts Phase 1 needs from the base font: UPM, outline format, axes, instances, BASE values."""
from __future__ import annotations

import argparse
import pathlib

from fontTools.ttLib import TTFont

from common import base_path, load_spec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=pathlib.Path, default=base_path(load_spec()))
    args = ap.parse_args()

    font = TTFont(args.src)
    outline = "glyf (TrueType)" if "glyf" in font else ("CFF2" if "CFF2" in font else "CFF")
    print(f"file       : {args.src}")
    print(f"UPM        : {font['head'].unitsPerEm}")
    print(f"outlines   : {outline}")
    print(f"glyphs     : {font['maxp'].numGlyphs}")
    print(f"cmap size  : {len(font.getBestCmap())}")
    print(f"vertical   : vhea={'vhea' in font} vmtx={'vmtx' in font}")

    if "fvar" in font:
        for axis in font["fvar"].axes:
            print(f"axis       : {axis.axisTag} {axis.minValue}..{axis.defaultValue}..{axis.maxValue}")
        name = font["name"]
        for inst in font["fvar"].instances:
            print(f"instance   : {name.getDebugName(inst.subfamilyNameID)} {inst.coordinates}")
    else:
        print("axis       : (static font)")

    if "BASE" in font:
        axis = font["BASE"].table.HorizAxis
        if axis and axis.BaseTagList:
            tags = list(axis.BaseTagList.BaselineTag)
            for rec in axis.BaseScriptList.BaseScriptRecord:
                values = rec.BaseScript.BaseValues
                if values:
                    coords = [c.Coordinate for c in values.BaseCoord]
                    print(f"BASE {rec.BaseScriptTag}: {dict(zip(tags, coords))}")


if __name__ == "__main__":
    main()
