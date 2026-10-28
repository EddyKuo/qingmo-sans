"""Apply the ordered geometric transforms from spec.yaml to every master.

Masters are processed together, glyph by glyph, so every decision about *which* points to touch is
made once on the reference master (the axis default, wght 400) and reused for all masters.

Contracts:
    transform(glyph_name, points, end_pts, flags, params, wght, ctx) -> list[(x, y)]
        Point transform. May move points but must return exactly as many points as it received.
    transform_structure(glyph_name, points, end_pts, flags, params, wght, ctx) -> (points, end_pts, flags)
        Structural transform (e.g. strokes, corners adding points). Must make the same structural
        change in every master; the pipeline verifies end_pts/flags match across masters.
        Structural transforms come after all point transforms.

ctx: {"ref", "upm", "advance", "stem_scale"}. "ref" is the reference-master outline before any
transform; for the k-th structural transform it is that outline after structural transforms 1..k-1,
so its indices match the points the transform receives.

Scope: only CJK ideographs are transformed; Latin, punctuation and symbols keep the base outlines.
Before transforming, folded-back spurs are collapsed: a horizontal / vertical straight edge that runs
the opposite way in some master than in the reference master (the base draws a few of these at
wght 250, e.g. 進) becomes zero-length there, so later small moves cannot turn it into a crossing.
Every glyph also gets a contour-direction fix: a few base glyphs (〕 ］ ｝ ㄟ …) are drawn
counter-clockwise; they are reversed in every master, decided on the reference master.
"""
from __future__ import annotations

import argparse
import importlib
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fontTools.pens.areaPen import AreaPen  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates  # noqa: E402

from common import BUILD, load_spec  # noqa: E402
from geometry import FLAT, straight_edges  # noqa: E402

CJK_RANGES = (
    (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF), (0x20000, 0x3134F),
)
STEM_PROBE = 0x4E00  # 「一」：量測各 master 的筆寬，供 stem_scale


class ContractError(RuntimeError):
    pass


def cjk_glyphs(font: TTFont) -> set[str]:
    return {name for cp, name in font.getBestCmap().items()
            if any(lo <= cp <= hi for lo, hi in CJK_RANGES)}


def stem_width(font: TTFont) -> float | None:
    name = font.getBestCmap().get(STEM_PROBE)
    if not name:
        return None
    glyph = font["glyf"][name]
    glyph.recalcBounds(font["glyf"])
    return glyph.yMax - glyph.yMin


def write_glyph(font: TTFont, name: str, points, end_pts, flags) -> None:
    glyf = font["glyf"]
    glyph = glyf[name]
    old_ymax = glyph.yMax
    glyph.coordinates = GlyphCoordinates(points)
    glyph.endPtsOfContours = list(end_pts)
    glyph.flags = bytearray(flags)
    glyph.recalcBounds(glyf)
    adv, _ = font["hmtx"][name]
    font["hmtx"][name] = (adv, glyph.xMin)
    if "vmtx" in font:
        vadv, tsb = font["vmtx"][name]
        font["vmtx"][name] = (vadv, tsb + old_ymax - glyph.yMax)


def reversed_contours(points, end_pts, flags):
    """每個輪廓反向（保留起點），點數與 on/off 結構對所有 master 一致。"""
    out_p, out_f, start = [], [], 0
    for end in end_pts:
        idx = [start] + list(range(end, start, -1))
        out_p += [points[i] for i in idx]
        out_f += [flags[i] for i in idx]
        start = end + 1
    return out_p, list(end_pts), out_f


def fix_directions(fonts: dict, ref_font: TTFont) -> int:
    """外輪廓應為順時針（有號面積為負）；母體少數字形相反，全部 master 一起反轉。"""
    gs = ref_font.getGlyphSet()
    fixed = 0
    for name in ref_font.getGlyphOrder():
        glyph = ref_font["glyf"][name]
        if glyph.isComposite() or glyph.numberOfContours <= 0:
            continue
        pen = AreaPen(gs)
        gs[name].draw(pen)
        if pen.value <= 0:
            continue
        for font in fonts.values():
            c, ep, fl = font["glyf"][name].getCoordinates(font["glyf"])
            write_glyph(font, name, *reversed_contours([tuple(p) for p in c], list(ep), list(fl)))
        fixed += 1
    return fixed


def collapse_spurs(points, ref, end_pts, flags):
    """參考 master 上的水平 / 垂直直線邊，在本 master 反向時縮成零長度（母體細字重的折返小刺）。"""
    out = list(points)
    for i, j in straight_edges(ref, end_pts, flags):
        for c in (0, 1):
            other = 1 - c
            if abs(ref[i][other] - ref[j][other]) > FLAT:
                continue                                   # 不是沿 c 軸的直線邊
            d_ref = ref[j][c] - ref[i][c]
            d_now = out[j][c] - out[i][c]
            if abs(d_ref) > FLAT and d_ref * d_now < 0:
                p = list(out[i])
                p[c] = out[j][c]
                out[i] = tuple(p)
    return out


def run(paths: list[pathlib.Path], transforms: list, params: dict, ref_wght: float) -> dict:
    fonts = {float(p.stem.removeprefix("master-wght")): TTFont(p) for p in paths}
    ref_w = ref_wght if ref_wght in fonts else sorted(fonts)[len(fonts) // 2]
    ref_font = fonts[ref_w]
    upm = ref_font["head"].unitsPerEm

    structural = [hasattr(m, "transform_structure") for m in transforms]
    if any(structural) and structural.index(True) != structural.count(False):
        raise ContractError("structural transforms must come after all point transforms")

    ref_stem = stem_width(ref_font)
    stem_scale = {w: (stem_width(f) / ref_stem if ref_stem else w / ref_w) for w, f in fonts.items()}

    print(f"contour direction fixed: {fix_directions(fonts, ref_font)} glyphs")
    changed = {w: 0 for w in fonts}
    for name in sorted(cjk_glyphs(ref_font)):
        ref_glyph = ref_font["glyf"][name]
        if ref_glyph.isComposite() or ref_glyph.numberOfContours <= 0:
            continue
        coords, end_pts, flags = ref_glyph.getCoordinates(ref_font["glyf"])
        ref_points = [tuple(p) for p in coords]
        end_pts, flags = list(end_pts), list(flags)

        # 結構性 transform 的參考輪廓：原始參考輪廓依序套用前面的結構性 transform
        struct_refs = []
        r_pts, r_ep, r_fl = ref_points, end_pts, flags
        for module in transforms:
            if hasattr(module, "transform_structure"):
                struct_refs.append(r_pts)
                rctx = {"ref": r_pts, "upm": upm, "advance": ref_font["hmtx"][name][0], "stem_scale": 1.0}
                r_pts, r_ep, r_fl = module.transform_structure(name, r_pts, r_ep, r_fl, params, ref_w, rctx)

        results = {}
        for w, font in fonts.items():
            c, _, _ = font["glyf"][name].getCoordinates(font["glyf"])
            original = [tuple(p) for p in c]
            points = collapse_spurs(original, ref_points, end_pts, flags)
            ctx = {"ref": ref_points, "upm": upm, "advance": font["hmtx"][name][0],
                   "stem_scale": stem_scale[w]}
            ep, fl = end_pts, flags
            k = 0
            for module in transforms:
                if hasattr(module, "transform_structure"):
                    sctx = dict(ctx, ref=struct_refs[k])
                    points, ep, fl = module.transform_structure(name, points, ep, fl, params, w, sctx)
                    k += 1
                    continue
                new = module.transform(name, points, ep, fl, params, w, ctx)
                if len(new) != len(points):
                    raise ContractError(f"{module.__name__} changed point count of {name}")
                points = new
            points = [(round(x), round(y)) for x, y in points]
            results[w] = (points, list(ep), list(fl), points != original or len(ep) != len(end_pts))

        shapes = {(tuple(ep), tuple(f & 1 for f in fl)) for _, ep, fl, _ in results.values()}
        if len(shapes) != 1:
            raise ContractError(f"{name}: structural transform diverged across masters")
        for w, (points, ep, fl, did) in results.items():
            if did:
                write_glyph(fonts[w], name, points, ep, fl)
                changed[w] += 1
    return {w: (fonts[w], changed[w]) for w in fonts}


def main() -> None:
    spec = load_spec()
    ap = argparse.ArgumentParser()
    ap.add_argument("--indir", type=pathlib.Path, default=BUILD / "masters")
    ap.add_argument("--outdir", type=pathlib.Path, default=BUILD / "transformed")
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    transforms = [importlib.import_module(n) for n in spec["transforms"]]
    paths = sorted(args.indir.glob("master-wght*.ttf"))
    for w, (font, changed) in run(paths, transforms, spec["style"], spec["axis"]["default"]).items():
        out = args.outdir / f"master-wght{int(w)}.ttf"
        font.save(out)
        print(f"{out}: {changed} glyphs changed")


if __name__ == "__main__":
    main()
