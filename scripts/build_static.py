"""Cut the static instances listed in spec.yaml from the VF, remove overlaps, name them, and write WOFF2.

Outputs:
    fonts/static/QingmoSansTC-{Style}.ttf
    fonts/webfonts/QingmoSansTC-{Style}.woff2 and QingmoSansTC[wght].woff2
"""
from __future__ import annotations

import argparse
import pathlib

import pathops
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.removeOverlaps import removeOverlaps
from fontTools.varLib import instancer

from common import FONTS, load_spec
from naming import mark_unhinted, set_names
from qa.outlines import contours, to_path

# OS/2 usWeightClass 的標準值；母體軸下限 250 的 ExtraLight 仍標 200
WEIGHT_CLASS = {"ExtraLight": 200, "Light": 300, "Regular": 400, "Medium": 500, "Bold": 700, "Heavy": 900}


def clean_contours(font: TTFont) -> int:
    """removeOverlaps 之後，兩筆畫恰好頂點或切點相接會留下自我相觸的輪廓（QA「無自交」不允許）。
    對每個這樣的輪廓單獨 simplify，換成 pathops 拆開後的多個輪廓；形狀與面積不變。"""
    glyf, gs = font["glyf"], font.getGlyphSet()
    fixed = 0
    for name in font.getGlyphOrder():
        if glyf[name].isComposite() or glyf[name].numberOfContours <= 0:
            continue
        pieces, changed = [], False
        for ops in contours(gs, name):
            path = to_path(ops)
            simple = pathops.simplify(path, clockwise=path.clockwise)
            if len(list(simple.contours)) > 1:
                pieces.append(simple)
                changed = True
            else:
                pieces.append(path)
        if not changed:
            continue
        pen = TTGlyphPen(None)
        cu2qu = Cu2QuPen(pen, max_err=1.0, reverse_direction=False)
        for path in pieces:
            path.draw(cu2qu)
        glyf[name] = pen.glyph()
        glyf[name].recalcBounds(glyf)
        font["hmtx"][name] = (font["hmtx"][name][0], glyf[name].xMin)
        fixed += 1
    return fixed


def main() -> None:
    spec = load_spec()
    fam = spec["family"]
    ap = argparse.ArgumentParser()
    ap.add_argument("--vf", type=pathlib.Path,
                    default=FONTS / "variable" / f"{fam['ps_prefix']}[{spec['axis']['tag']}].ttf")
    ap.add_argument("--outdir", type=pathlib.Path, default=FONTS)
    args = ap.parse_args()
    static_dir, web_dir = args.outdir / "static", args.outdir / "webfonts"
    static_dir.mkdir(parents=True, exist_ok=True)
    web_dir.mkdir(parents=True, exist_ok=True)

    vf = TTFont(args.vf)
    axis = next(a for a in vf["fvar"].axes if a.axisTag == spec["axis"]["tag"])
    for inst in spec["instances"]:
        wght = min(max(inst["wght"], axis.minValue), axis.maxValue)
        font = instancer.instantiateVariableFont(TTFont(args.vf), {axis.axisTag: wght})
        removeOverlaps(font)
        clean_contours(font)
        set_names(font, spec, inst["name"], variable=False)
        mark_unhinted(font)
        font["OS/2"].usWeightClass = WEIGHT_CLASS.get(inst["name"], int(wght))
        bold = inst["name"] == "Bold"
        sel = font["OS/2"].fsSelection & ~0b1100001   # 清 ITALIC/BOLD/REGULAR
        # legacy subfamily 只有 Regular / Bold 兩種（見 naming.py），非 Bold 一律標 REGULAR
        font["OS/2"].fsSelection = sel | (0x20 if bold else 0x40)
        font["head"].macStyle = 0x1 if bold else 0
        out = static_dir / f"{fam['ps_prefix']}-{inst['name']}.ttf"
        font.save(out)
        font.flavor = "woff2"
        font.save(web_dir / out.with_suffix(".woff2").name)
        print(f"OK {out}")

    vf.flavor = "woff2"
    vf.save(web_dir / args.vf.with_suffix(".woff2").name)
    print(f"OK {web_dir / args.vf.with_suffix('.woff2').name}")


if __name__ == "__main__":
    main()
