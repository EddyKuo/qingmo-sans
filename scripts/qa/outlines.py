"""QA gate「破字 0」（Design Spec v0）：自交、方向錯誤、殘留 overlap，以 skia-pathops 檢查。

- 方向：整個字形的有號面積須為負（TrueType 外輪廓順時針）
- 自交（--no-overlap）：單一輪廓經 pathops.simplify 後面積改變（8 字形等）或被拆成多個輪廓
- 殘留 overlap（--no-overlap）：整字 simplify 後的面積須等於各輪廓有號面積和
可變字型允許重疊（glyf OVERLAP_SIMPLE 旗標；母體的 & e 4 等拉丁字形本身就是自我重疊的單一輪廓），
所以 VF 只檢查方向；static 字型（build_static.py 已 removeOverlaps）加 --no-overlap 檢查全部三項。
"""
from __future__ import annotations

import argparse
import pathlib
import sys

import pathops
from fontTools.pens.areaPen import AreaPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont

TOL = 2.0  # font units²，量化誤差容忍
# 殘留 overlap 的容忍：removeOverlaps 後座標取整數會留下次像素細縫（或、新 約 2–3 units²，
# 整字面積 30 萬以上）。取 TOL 與整字面積 0.002% 的較大者
OVERLAP_REL = 2e-5


def contours(glyphset, name):
    rec = RecordingPen()
    glyphset[name].draw(rec)
    out, cur = [], []
    for op, args in rec.value:
        cur.append((op, args))
        if op in ("closePath", "endPath"):
            out.append(cur)
            cur = []
    return out


def to_path(ops) -> pathops.Path:
    path = pathops.Path()
    pen = path.getPen()
    for op, args in ops:
        getattr(pen, op)(*args)
    return path


def check_font(path: pathlib.Path, no_overlap: bool) -> list[str]:
    font = TTFont(path)
    gs = font.getGlyphSet()
    problems = []
    for name in font.getGlyphOrder():
        cs = contours(gs, name)
        if not cs:
            continue
        for k, ops in enumerate(cs if no_overlap else []):
            p = to_path(ops)
            s = pathops.simplify(p, clockwise=p.clockwise)
            if abs(abs(s.area) - abs(p.area)) > TOL or len(list(s.contours)) > 1:
                problems.append(f"{name}: contour {k} self-intersects")
        area = AreaPen(gs)
        gs[name].draw(area)
        if area.value > TOL:
            problems.append(f"{name}: wrong direction (signed area {area.value:.0f})")
        if no_overlap:
            whole = pathops.Path()
            for ops in cs:
                whole.addPath(to_path(ops))
            union = pathops.simplify(whole, clockwise=True)
            if abs(abs(union.area) - abs(area.value)) > max(TOL, OVERLAP_REL * abs(area.value)):
                problems.append(f"{name}: residual overlap")
    return problems


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("fonts", nargs="+", type=pathlib.Path)
    ap.add_argument("--no-overlap", action="store_true",
                    help="also fail on self-intersecting or overlapping contours (static fonts)")
    args = ap.parse_args()

    failed = False
    for path in args.fonts:
        problems = check_font(path, args.no_overlap)
        if problems:
            failed = True
            print(f"FAIL {path.name}: {len(problems)} problem(s)")
            for line in problems[:30]:
                print("  " + line)
        else:
            print(f"OK {path.name}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
