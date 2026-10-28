"""Build the wght variable font from transformed masters, then apply Qingmo names and STAT."""
from __future__ import annotations

import argparse
import pathlib

from fontTools import varLib
from fontTools.designspaceLib import (
    AxisDescriptor,
    DesignSpaceDocument,
    InstanceDescriptor,
    SourceDescriptor,
)
from fontTools.otlLib.builder import buildStatTable

from common import BUILD, FONTS, load_spec, master_filename
from naming import set_names


def designspace(spec: dict, indir: pathlib.Path, masters: list[int]) -> DesignSpaceDocument:
    ax = spec["axis"]
    doc = DesignSpaceDocument()

    axis = AxisDescriptor()
    axis.tag, axis.name = ax["tag"], ax["name"]
    axis.minimum, axis.default, axis.maximum = min(masters), ax["default"], max(masters)
    doc.addAxis(axis)

    for wght in masters:
        src = SourceDescriptor()
        src.path = str(indir / master_filename(wght))
        src.name = f"master-{wght}"
        src.location = {ax["name"]: wght}
        doc.addSource(src)

    fam = spec["family"]
    for inst in spec["instances"]:
        if axis.minimum <= inst["wght"] <= axis.maximum:
            i = InstanceDescriptor()
            i.familyName = fam["en"]
            i.styleName = inst["name"]
            i.postScriptFontName = f"{fam['ps_prefix']}-{inst['name']}"
            i.location = {ax["name"]: inst["wght"]}
            doc.addInstance(i)
    return doc


def main() -> None:
    spec = load_spec()
    fam = spec["family"]
    ap = argparse.ArgumentParser()
    ap.add_argument("--indir", type=pathlib.Path, default=BUILD / "transformed")
    ap.add_argument("--out", type=pathlib.Path,
                    default=FONTS / "variable" / f"{fam['ps_prefix']}[{spec['axis']['tag']}].ttf")
    ap.add_argument("--masters", type=lambda s: [int(x) for x in s.split(",")],
                    default=spec["masters"], help="comma-separated wght values; default from spec")
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    vf, _, _ = varLib.build(designspace(spec, args.indir, args.masters))
    set_names(vf, spec, "Regular", variable=True)

    default = spec["axis"]["default"]
    lo, hi = min(args.masters), max(args.masters)
    buildStatTable(vf, [{
        "tag": spec["axis"]["tag"],
        "name": spec["axis"]["name"],
        "values": [
            {"value": i["wght"], "name": i["name"], "flags": 0x2 if i["wght"] == default else 0}
            for i in spec["instances"] if lo <= i["wght"] <= hi
        ],
    }])
    vf.save(args.out)
    print(f"OK {args.out}")


if __name__ == "__main__":
    main()
