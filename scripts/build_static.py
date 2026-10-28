"""Cut the static instances listed in spec.yaml from the VF, remove overlaps, name them, and write WOFF2.

Outputs:
    fonts/static/QingmoSansTC-{Style}.ttf
    fonts/webfonts/QingmoSansTC-{Style}.woff2 and QingmoSansTC[wght].woff2
"""
from __future__ import annotations

import argparse
import pathlib

import pathops
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.removeOverlaps import removeOverlaps
from fontTools.varLib import instancer

from common import FONTS, load_spec
from naming import mark_unhinted, set_names
from qa.outlines import contours, glyph_problems, to_path

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


SLIVER = 10.0   # font units²：取整後殘留的細縫碎片，小於此面積直接丟棄（12 px 下約 0.0001 像素）


def _rebuild(font: TTFont, name: str) -> None:
    """整字聯集 → 每個輪廓再拆開自我相觸處 → 丟掉細縫碎片 → 轉回 TrueType 二次曲線。"""
    glyf, gs = font["glyf"], font.getGlyphSet()
    whole = pathops.Path()
    for ops in contours(gs, name):
        whole.addPath(to_path(ops))
    union = pathops.simplify(whole, clockwise=True)
    pen = TTGlyphPen(None)
    cu2qu = Cu2QuPen(pen, max_err=1.0, reverse_direction=False)
    for contour in union.contours:
        part = pathops.Path()
        contour.draw(part.getPen())
        for piece in pathops.simplify(part, clockwise=part.clockwise).contours:
            if abs(piece.area) >= SLIVER:
                piece.draw(cu2qu)
    glyf[name] = pen.glyph()
    glyf[name].recalcBounds(glyf)
    font["hmtx"][name] = (font["hmtx"][name][0], glyf[name].xMin)


def _despike_ring(ring: list[tuple]) -> list[list[tuple]]:
    """整數座標上的清理：去連續重複點、退化的超短曲線改直線（颺：弦長 1.4 的曲線繞出 0.01 的小圈）、
    去 A→P→A 針尖、在重複的 on-curve 頂點拆開輪廓。"""
    changed = True
    while changed and len(ring) >= 3:
        changed = False
        for k in range(len(ring)):
            if ring[k][0] == ring[(k + 1) % len(ring)][0]:              # 連續重複
                keep = ring[k][1] or ring[(k + 1) % len(ring)][1]
                ring[k] = (ring[k][0], keep)
                del ring[(k + 1) % len(ring)]
                changed = True
                break
            prev, nxt = ring[k - 1], ring[(k + 1) % len(ring)]
            if not ring[k][1] and (
                    (prev[1] and nxt[1] and abs(prev[0][0] - nxt[0][0]) + abs(prev[0][1] - nxt[0][1]) <= 2)
                    or (prev[1] and max(abs(prev[0][0] - ring[k][0][0]), abs(prev[0][1] - ring[k][0][1])) <= 1)
                    or (nxt[1] and max(abs(nxt[0][0] - ring[k][0][0]), abs(nxt[0][1] - ring[k][0][1])) <= 1)):
                del ring[k]                                              # 退化的超短曲線改成直線
                changed = True
                break
            if prev[1] and nxt[1] and ring[k][1] and prev[0] == nxt[0]:  # A→P→A 針尖
                for idx in sorted({k, (k + 1) % len(ring)}, reverse=True):
                    del ring[idx]
                changed = True
                break
    if len(ring) < 3:
        return []
    seen = {}
    for k, (pt, on) in enumerate(ring):
        if on and pt in seen:
            a = seen[pt]
            return _despike_ring(ring[a:k]) + _despike_ring(ring[:a] + ring[k:])
        if on:
            seen[pt] = k
    return [ring]


def _despike(font: TTFont, name: str) -> None:
    glyf = font["glyf"]
    glyph = glyf[name]
    coords, end_pts, flags = glyph.getCoordinates(glyf)
    rings, start = [], 0
    for end in end_pts:
        rings += _despike_ring([(tuple(coords[i]), bool(flags[i] & 1)) for i in range(start, end + 1)])
        start = end + 1
    pts, fl, ends = [], [], []
    for ring in rings:
        pts += [p for p, _ in ring]
        fl += [1 if on else 0 for _, on in ring]
        ends.append(len(pts) - 1)
    glyph.coordinates = GlyphCoordinates(pts)
    glyph.flags = bytearray(fl)
    glyph.endPtsOfContours = ends
    glyph.numberOfContours = len(ends)
    glyph.recalcBounds(glyf)
    font["hmtx"][name] = (font["hmtx"][name][0], glyph.xMin)


def settle(font: TTFont, rounds: int = 4) -> list[str]:
    """removeOverlaps 後轉回整數座標，少數字（約 0.15%）會留下細小自交或重疊；反覆重建到 QA 乾淨為止。"""
    names = [n for n in font.getGlyphOrder()
             if not font["glyf"][n].isComposite() and font["glyf"][n].numberOfContours > 0]
    for _ in range(rounds):
        gs = font.getGlyphSet()
        names = [n for n in names if glyph_problems(gs, n, True)]
        if not names:
            break
        for name in names:
            _rebuild(font, name)
            _despike(font, name)
    return names


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
        left = settle(font)
        if left:
            print(f"WARNING {inst['name']}: {len(left)} glyph(s) still fail outline QA: {' '.join(left[:20])}")
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
