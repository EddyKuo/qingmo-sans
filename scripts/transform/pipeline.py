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
Safety net: a glyph whose transforms raise, or that would gain a self-intersecting contour in any
master, is redone adding transforms one at a time and skipping only the ones that break it; skipped
transforms are listed in <outdir>/transform-report.json. Large fonts are processed in parallel.
Every glyph also gets a contour-direction fix: a few base glyphs (〕 ］ ｝ ㄟ …) are drawn
counter-clockwise; they are reversed in every master, decided on the reference master.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import pathlib
import sys
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pathops  # noqa: E402
from fontTools.pens.areaPen import AreaPen  # noqa: E402
from fontTools.pens.recordingPen import RecordingPen  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphCoordinates  # noqa: E402

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


def crossing_contours(points, end_pts, flags, only: set[int] | None = None) -> set[int]:
    """自我交叉的輪廓索引（pathops simplify 後面積改變或被拆成多塊）；only 限定要檢查的輪廓。"""
    glyph = Glyph()
    glyph.numberOfContours = len(end_pts)
    glyph.coordinates = GlyphCoordinates(points)
    glyph.endPtsOfContours = list(end_pts)
    glyph.flags = bytearray(f & 1 for f in flags)
    rec = RecordingPen()
    glyph.draw(rec, None)
    out, k, path, pen = set(), 0, None, None
    for op, args in rec.value:
        if pen is None:
            path = pathops.Path()
            pen = path.getPen()
        getattr(pen, op)(*args)
        if op in ("closePath", "endPath"):
            if only is None or k in only:
                simple = pathops.simplify(path, clockwise=path.clockwise)
                if abs(abs(simple.area) - abs(path.area)) > 2.0 or len(list(simple.contours)) > 1:
                    out.add(k)
            k += 1
            pen = None
    return out


# 平行 worker 的共用狀態（由 _init 設定）
_TRANSFORMS: list = []
_PARAMS: dict = {}


def _init(names: list[str], params: dict) -> None:
    global _TRANSFORMS, _PARAMS
    _TRANSFORMS = [importlib.import_module(n) for n in names]
    _PARAMS = params


def _attempt(task, active, collapse=True):
    """以 active 這組 transform 改造一個字的所有 master；collapse 決定是否先收掉折返小刺。"""
    name, ref_points, end_pts, flags, masters, stem_scale, ref_w, upm = task
    struct_refs = []
    r_pts, r_ep, r_fl = ref_points, end_pts, flags
    for module in active:
        if hasattr(module, "transform_structure"):
            struct_refs.append(r_pts)
            rctx = {"ref": r_pts, "upm": upm, "advance": masters[ref_w][1], "stem_scale": 1.0}
            r_pts, r_ep, r_fl = module.transform_structure(name, r_pts, r_ep, r_fl, _PARAMS, ref_w, rctx)

    results = {}
    for w, (original, advance) in masters.items():
        points = collapse_spurs(original, ref_points, end_pts, flags) if collapse else list(original)
        ctx = {"ref": ref_points, "upm": upm, "advance": advance, "stem_scale": stem_scale[w]}
        ep, fl, k = end_pts, flags, 0
        for module in active:
            if hasattr(module, "transform_structure"):
                points, ep, fl = module.transform_structure(name, points, ep, fl, _PARAMS, w,
                                                            dict(ctx, ref=struct_refs[k]))
                k += 1
                continue
            new = module.transform(name, points, ep, fl, _PARAMS, w, ctx)
            if len(new) != len(points):
                raise ContractError(f"{module.__name__} changed point count of {name}")
            points = new
        results[w] = ([(round(x), round(y)) for x, y in points], list(ep), list(fl))
    if len({(tuple(ep), tuple(f & 1 for f in fl)) for _, ep, fl in results.values()}) != 1:
        raise ContractError(f"{name}: structural transform diverged across masters")
    return results


def _lerp(a, b, t):
    # 與 VF instancer 一樣取整數：幾乎重合的點在取整後才會交叉（噘、魔 在 600–800）
    return [(round(x0 + (x1 - x0) * t), round(y0 + (y1 - y0) * t)) for (x0, y0), (x1, y1) in zip(a, b)]


SHORT_EDGE = 20   # font units；含這麼短的邊的輪廓，插值時可能只在很窄的區間交叉
COARSE = [i / 10 for i in range(1, 10)]
FINE = [i / 50 for i in range(1, 50)]


def _short_contours(points_list, end_pts) -> set[int]:
    out, start = set(), 0
    for k, end in enumerate(end_pts):
        for pts in points_list:
            ring = pts[start:end + 1]
            if any(abs(p[0] - q[0]) + abs(p[1] - q[1]) < SHORT_EDGE for p, q in zip(ring, ring[1:] + ring[:1])):
                out.add(k)
                break
        start = end + 1
    return out


def _safe(task, results) -> bool:
    """各 master、以及相鄰 master 之間的插值（取整數）都不得比母體多出自我交叉的輪廓。

    插值以 10% 步距檢查全部輪廓；含短邊的輪廓（交叉可能只在很窄的區間，如 噘 在 t≈0.46）改以 2% 步距檢查。
    """
    _, _, end_pts, flags, masters, _, _, _ = task
    for w, (pts, ep, fl) in results.items():
        before = crossing_contours(masters[w][0], end_pts, flags)
        if crossing_contours(pts, ep, fl) - before:
            return False
    ws = sorted(results)
    for a, b in zip(ws, ws[1:]):
        (pa, ep, fl), (pb, _, _) = results[a], results[b]
        short = _short_contours([pa, pb], ep)
        for t in sorted(set(COARSE) | (set(FINE) if short else set())):
            only = None if t in COARSE else short
            before = crossing_contours(_lerp(masters[a][0], masters[b][0], t), end_pts, flags, only)
            if crossing_contours(_lerp(pa, pb, t), ep, fl, only) - before:
                return False
    return True


def process_glyph(task):
    """回傳 (name, {w: (points, end_pts, flags, changed)}, 略過的 transform, 錯誤訊息)。

    先套用全部 transform；失敗（例外或新增自交）時逐項加入，只略過造成問題的那幾項。
    """
    name, _, _, _, masters, _, _, _ = task
    skipped, errors = [], []
    try:
        results = _attempt(task, _TRANSFORMS)
        if not _safe(task, results):
            raise ContractError("new self-intersection")
    except Exception as exc:  # noqa: BLE001 - 單字錯誤降級處理，不中斷整批
        errors.append(f"{type(exc).__name__}: {exc}")
        # 收折返小刺本身也可能造成插值交叉（噘：900 的短邊反向，壓平後 t=0.36–0.98 都交叉）
        collapse = _safe(task, _attempt(task, [], True))
        if not collapse:
            skipped.append("collapse_spurs")
        active = []
        for module in _TRANSFORMS:
            trial = active + [module]
            try:
                ok = _safe(task, _attempt(task, trial, collapse))
            except Exception:  # noqa: BLE001
                ok = False
            if ok:
                active = trial
            else:
                skipped.append(module.__name__)
        results = _attempt(task, active, collapse)
    out = {w: (pts, ep, fl, pts != masters[w][0] or len(pts) != len(masters[w][0]))
           for w, (pts, ep, fl) in results.items()}
    return name, out, skipped, errors


def run(paths: list[pathlib.Path], transforms: list, params: dict, ref_wght: float,
        jobs: int | None = None, report: pathlib.Path | None = None) -> dict:
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
    tasks = []
    for name in sorted(cjk_glyphs(ref_font)):
        ref_glyph = ref_font["glyf"][name]
        if ref_glyph.isComposite() or ref_glyph.numberOfContours <= 0:
            continue
        _, end_pts, flags = ref_glyph.getCoordinates(ref_font["glyf"])
        masters = {}
        for w, font in fonts.items():
            c, _, _ = font["glyf"][name].getCoordinates(font["glyf"])
            masters[w] = ([tuple(p) for p in c], font["hmtx"][name][0])
        tasks.append((name, masters[ref_w][0], list(end_pts), list(flags), masters, stem_scale, ref_w, upm))

    names = [m.__name__ for m in transforms]
    jobs = jobs or (1 if len(tasks) < 400 else os.cpu_count() or 1)
    pool = None
    if jobs == 1:
        _init(names, params)
        outputs = map(process_glyph, tasks)
    else:
        pool = ProcessPoolExecutor(max_workers=jobs, initializer=_init, initargs=(names, params))
        outputs = pool.map(process_glyph, tasks, chunksize=32)

    changed = {w: 0 for w in fonts}
    problems = {}
    for name, results, skipped, errors in outputs:
        if skipped or errors:
            problems[name] = {"skipped": skipped, "errors": errors}
        for w, (pts, ep, fl, did) in results.items():
            if did:
                write_glyph(fonts[w], name, pts, ep, fl)
                changed[w] += 1
    if pool:
        pool.shutdown()

    with_skips = sum(1 for v in problems.values() if v["skipped"])
    print(f"glyphs: {len(tasks)}, all transforms applied: {len(tasks) - with_skips}, "
          f"with skipped transforms: {with_skips}")
    if report:
        report.write_text(json.dumps(problems, ensure_ascii=False, indent=1), encoding="utf-8")
    return {w: (fonts[w], changed[w]) for w in fonts}


def main() -> None:
    spec = load_spec()
    ap = argparse.ArgumentParser()
    ap.add_argument("--indir", type=pathlib.Path, default=BUILD / "masters")
    ap.add_argument("--outdir", type=pathlib.Path, default=BUILD / "transformed")
    ap.add_argument("--jobs", type=int, help="worker processes; default: all cores for large fonts")
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    transforms = [importlib.import_module(n) for n in spec["transforms"]]
    paths = sorted(args.indir.glob("master-wght*.ttf"))
    report = args.outdir / "transform-report.json"
    for w, (font, changed) in run(paths, transforms, spec["style"], spec["axis"]["default"],
                                  jobs=args.jobs, report=report).items():
        out = args.outdir / f"master-wght{int(w)}.ttf"
        font.save(out)
        print(f"{out}: {changed} glyphs changed")


if __name__ == "__main__":
    main()
