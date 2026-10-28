"""墨暈軟角：折角外角軟化（spec: style.corner_radius_units = 6，隨字重縮放）。

母體折角只有一個 on-curve 點，軟化必須新增點，所以本模組是「結構性 transform」：
實作 transform_structure() 而非 transform()，由 pipeline 對所有 master 用同一份參考輪廓決定轉角集合，
每個 master 在同一批轉角插入同樣的點，點相容由 pipeline 比對 end_pts / flags 保證。

- 轉角條件（參考 master）：前後皆為直線邊、夾角 60°–120°、凸角、兩邊長 >= 4r、
  且轉角不被其他輪廓蓋住（重疊筆畫內部看不到的角不處理，避免白白增加點數）
- 轉角 P 換成 on(P - r·u_in)、off(P)、on(P + r·u_out)：一段二次曲線圓角
- r(w) = corner_radius_units * stem_scale(w)，stem_scale 由 pipeline 依「一」的筆寬量測
"""
from __future__ import annotations

import math

from geometry import contour_of, contour_ranges, inside, neighbours


def _unit(a, b):
    d = math.dist(a, b)
    if d == 0:
        return (0.0, 0.0), 0.0
    return ((b[0] - a[0]) / d, (b[1] - a[1]) / d), d


def _signed_area(points, rng):
    idx = list(rng)
    return sum(points[i][0] * points[idx[(k + 1) % len(idx)]][1]
               - points[idx[(k + 1) % len(idx)]][0] * points[i][1] for k, i in enumerate(idx)) / 2


def soft_corners(points, end_pts, flags, r):
    """參考 master 上要軟化的轉角索引。"""
    areas = {rng: _signed_area(points, rng) for rng in contour_ranges(end_pts)}
    out = []
    for i in range(len(points)):
        if not flags[i] & 1:
            continue
        p, n = neighbours(end_pts, i)
        if not (flags[p] & 1 and flags[n] & 1):
            continue
        u_in, l_in = _unit(points[p], points[i])
        u_out, l_out = _unit(points[i], points[n])
        if min(l_in, l_out) < 4 * r:
            continue
        cos = u_in[0] * u_out[0] + u_in[1] * u_out[1]
        if abs(cos) > 0.5:                       # 夾角不在 60°–120°
            continue
        cross = u_in[0] * u_out[1] - u_in[1] * u_out[0]
        rng = contour_of(end_pts, i)
        if cross * areas[rng] <= 0:              # 凹角
            continue
        if inside(points, end_pts, flags, points[i], skip=rng):
            continue
        out.append(i)
    return out


def transform_structure(glyph_name, points, end_pts, flags, params, wght, ctx):
    r_ref = params["corner_radius_units"]
    r = r_ref * ctx["stem_scale"]
    if r_ref <= 0:
        return points, end_pts, flags
    corners = set(soft_corners(ctx["ref"], end_pts, flags, r_ref))
    if not corners:
        return points, end_pts, flags

    new_pts, new_flags, new_ends = [], [], []
    for rng in contour_ranges(end_pts):
        for i in rng:
            if i not in corners:
                new_pts.append(points[i])
                new_flags.append(flags[i])
                continue
            pv, nx = neighbours(end_pts, i)
            u_in, _ = _unit(points[pv], points[i])
            u_out, _ = _unit(points[i], points[nx])
            x, y = points[i]
            new_pts += [(x - r * u_in[0], y - r * u_in[1]), (x, y), (x + r * u_out[0], y + r * u_out[1])]
            # OVERLAP_SIMPLE (0x40) 只能留在字形第一點，新增的點一律不帶
            new_flags += [flags[i], 0, 1]
        new_ends.append(len(new_pts) - 1)
    return new_pts, new_ends, new_flags
