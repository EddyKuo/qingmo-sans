"""Build the wght variable font from transformed masters, then apply Qingmo names and STAT.

The base VF maps wght non-linearly through its avar table (e.g. user 400 -> 39 % of the design range).
Masters are cut at user positions, so the designspace carries the same user->design map; otherwise
every weight between masters would drift away from the base's weight curve.
"""
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

from fontTools.ttLib import TTFont

from common import BUILD, FONTS, load_spec, master_filename
from naming import mark_unhinted, set_names


def base_axis_map(path: pathlib.Path, tag: str) -> list[tuple[float, float]]:
    """(user, design) pairs reproducing the base font's avar; identity if it has none."""
    font = TTFont(path)
    if "fvar" not in font:
        return []
    a = next(x for x in font["fvar"].axes if x.axisTag == tag)
    segs = font["avar"].segments.get(tag, {}) if "avar" in font else {}

    def denorm(n):
        return a.defaultValue + n * ((a.maxValue - a.defaultValue) if n >= 0 else (a.defaultValue - a.minValue))

    # avar 以 F2Dot14 儲存，breakpoint 反算的 user 值有 0.003 級誤差；母體 breakpoint 都落在整數字重上
    return sorted({(float(round(denorm(k))), round(denorm(v), 3)) for k, v in segs.items()
                   if a.minValue <= denorm(k) <= a.maxValue})


def to_design(mapping: list[tuple[float, float]], user: float) -> float:
    if not mapping:
        return user
    for (u0, d0), (u1, d1) in zip(mapping, mapping[1:]):
        if u0 <= user <= u1:
            return d0 + (user - u0) * (d1 - d0) / (u1 - u0)
    return user


def designspace(spec: dict, indir: pathlib.Path, masters: list[int],
                mapping: list[tuple[float, float]]) -> DesignSpaceDocument:
    ax = spec["axis"]
    doc = DesignSpaceDocument()

    axis = AxisDescriptor()
    axis.tag, axis.name = ax["tag"], ax["name"]
    axis.minimum, axis.default, axis.maximum = min(masters), ax["default"], max(masters)
    axis.map = [(u, d) for u, d in mapping if axis.minimum <= u <= axis.maximum]
    doc.addAxis(axis)

    for wght in masters:
        src = SourceDescriptor()
        src.path = str(indir / master_filename(wght))
        src.name = f"master-{wght}"
        src.location = {ax["name"]: to_design(mapping, wght)}
        doc.addSource(src)

    fam = spec["family"]
    for inst in spec["instances"]:
        if axis.minimum <= inst["wght"] <= axis.maximum:
            i = InstanceDescriptor()
            i.familyName = fam["en"]
            i.styleName = inst["name"]
            i.postScriptFontName = f"{fam['ps_prefix']}-{inst['name']}"
            i.location = {ax["name"]: to_design(mapping, inst["wght"])}
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
    ap.add_argument("--avar-src", type=pathlib.Path, default=BUILD / "subset" / "base-phase1.ttf",
                    help="font whose avar defines the user->design weight curve (the base VF)")
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    mapping = base_axis_map(args.avar_src, spec["axis"]["tag"]) if args.avar_src.exists() else []
    vf, _, _ = varLib.build(designspace(spec, args.indir, args.masters, mapping))
    set_names(vf, spec, "Regular", variable=True)
    mark_unhinted(vf)

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
    vf["name"].removeNames(platformID=1)                 # buildStatTable 會補 Mac 名稱
    vf["OS/2"].fsSelection = (vf["OS/2"].fsSelection & ~0b1100001) | 0x40   # 預設 instance 為 Regular
    vf.save(args.out)
    print(f"OK {args.out}")


if __name__ == "__main__":
    main()
