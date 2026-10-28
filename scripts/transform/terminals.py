"""筆端：起筆斜切、收筆微收（spec: style.entry_cut_deg / exit_taper_pct）。

在參考 master 上找筆畫端緣：一條短直線邊，兩端都以直角接上與它垂直、長度 >= 1.5 倍端緣的直線邊，
且端緣不被其他輪廓蓋住（藏在豎畫裡的橫畫末端不算筆端）。
- 橫畫左端（填色在右）= 起筆：下角向右移 w * tan(entry_cut_deg)，端緣成「\\」向斜切
- 豎畫上端（填色在下）= 起筆：右角向下移 w * tan(entry_cut_deg)
- 橫畫右端、豎畫下端 = 收筆：端緣兩點各向中線收 exit_taper_pct / 2，總寬縮 exit_taper_pct
w 為端緣在當前 master 上的長度（= 筆寬）。只移動既有點，點數不變；所有移動都朝填色內側，不會長出筆畫外。
"""
from __future__ import annotations

import math

from geometry import contour_of, inside, inside_own, neighbours

MAX_STEM = 0.16   # × UPM
FLAT = 1.0


def _axis(a, b):
    if abs(a[0] - b[0]) <= FLAT and abs(a[1] - b[1]) > FLAT:
        return "v"
    if abs(a[1] - b[1]) <= FLAT and abs(a[0] - b[0]) > FLAT:
        return "h"
    return None


def stroke_ends(points, end_pts, flags, upm):
    """[(kind, i, j)]，kind ∈ h_entry | h_exit | v_entry | v_exit；i, j 為端緣兩點。"""
    ends = []
    seen = set()
    for i in range(len(points)):
        if not flags[i] & 1:
            continue
        _, j = neighbours(end_pts, i)
        if not flags[j] & 1 or (i, j) in seen:
            continue
        seen.add((i, j))
        a, b = points[i], points[j]
        axis = _axis(a, b)
        w = math.dist(a, b)
        if axis is None or w > MAX_STEM * upm:
            continue
        p, _ = neighbours(end_pts, i)
        _, n = neighbours(end_pts, j)
        if not (flags[p] & 1 and flags[n] & 1):
            continue
        other = "h" if axis == "v" else "v"
        if _axis(points[p], a) != other or _axis(b, points[n]) != other:
            continue
        if math.dist(points[p], a) < 1.5 * w or math.dist(b, points[n]) < 1.5 * w:
            continue
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        if inside(points, end_pts, flags, (mx, my), skip=contour_of(end_pts, i)):
            continue                      # 端點藏在其他筆畫裡，不是看得見的筆端
        if axis == "v":
            fill_right = inside_own(points, end_pts, flags, i, (mx + 2, my))
            ends.append(("h_entry" if fill_right else "h_exit", i, j))
        else:
            fill_below = inside_own(points, end_pts, flags, i, (mx, my - 2))
            ends.append(("v_entry" if fill_below else "v_exit", i, j))
    return ends


def transform(glyph_name, points, end_pts, flags, params, wght, ctx):
    tan = math.tan(math.radians(params["entry_cut_deg"]))
    taper = params["exit_taper_pct"] / 100
    out = list(points)
    for kind, i, j in stroke_ends(ctx["ref"], end_pts, flags, ctx["upm"]):
        a, b = out[i], out[j]
        w = math.dist(a, b)
        if kind == "h_entry":
            k = i if a[1] < b[1] else j            # 下角
            out[k] = (out[k][0] + w * tan, out[k][1])
        elif kind == "v_entry":
            k = i if a[0] > b[0] else j            # 右角
            out[k] = (out[k][0], out[k][1] - w * tan)
        elif kind == "h_exit":
            s = w * taper / 2
            lo, hi = (i, j) if a[1] < b[1] else (j, i)
            out[lo] = (out[lo][0], out[lo][1] + s)
            out[hi] = (out[hi][0], out[hi][1] - s)
        else:                                      # v_exit
            s = w * taper / 2
            lo, hi = (i, j) if a[0] < b[0] else (j, i)
            out[lo] = (out[lo][0] + s, out[lo][1])
            out[hi] = (out[hi][0] - s, out[hi][1])
    return out
