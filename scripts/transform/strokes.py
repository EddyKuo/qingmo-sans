"""筆畫模板：點、撇、捺（Design Spec v0「點 / 捺 / 撇」）。

在參考 master 上把每個輪廓切成「段」（相鄰 on-curve 點之間，含其間的 off-curve），
找出筆端段（cap）：弦長 <= MAX_STEM，且前後兩段都比它長 1.5 倍以上。
cap 的朝向 = 從筆身（前後段遠端的中點）指向 cap 中點的方向。

- 撇（出鋒漸細，末端不留尖刺）：彎曲 cap（>= 2 個 off-curve）朝左下 [-160°, -100°]。
  cap 的點對 cap 中點縮放到 pie_tip_pct，但弦長不小於 pie_min_width，筆身自然收細、末端保留鈍頭
- 捺（收尾帶短平台再出鋒）：彎曲 cap 朝右下 [-75°, -25°]，且兩側都是曲線（排除豎鉤的轉角）。下端點 A 不動，
  cap 內的 off-curve 除最後一個外都排在 A 的水平線上形成平台，尖端 B 移到平台右上方 → 平台後出鋒
- 點（上尖下圓的錐形點）：只有 4 段、兩端都是直線 cap 的短斜筆（右點長度 <= DOT_MAX_LEN、左點 <= DOT_MAX_LEN_LEFT，
  方向離水平 / 垂直 > 12°）。上端 cap 收成尖（弦長縮到 dot_tip_pct）；
  下端 cap 插入一個 off-curve 變成圓頭 —— 會新增點，所以本模組是結構性 transform

所有判斷都在參考輪廓上做，每個 master 套用相同的點操作，點相容由 pipeline 驗證。
"""
from __future__ import annotations

import math

from geometry import contour_ranges

MAX_STEM = 0.16        # × UPM
DOT_MAX_LEN = 0.42     # × UPM，右點（左上→右下）的最大長度（永的首點約 0.40）
DOT_MAX_LEN_LEFT = 0.25  # × UPM，左點（右上→左下）的最大長度；更長的是短撇
AXIS_TOL = 12          # 度


def segments(flags, rng):
    """[[i0, off..., i1], ...]：輪廓上相鄰 on-curve 點之間的段。"""
    idx = list(rng)
    ons = [k for k, i in enumerate(idx) if flags[i] & 1]
    n = len(idx)
    return [[idx[k % n] for k in range(a, b + 1)] for a, b in zip(ons, ons[1:] + [ons[0] + n])]


def _chord(points, seg):
    return math.dist(points[seg[0]], points[seg[-1]])


def _mid(points, seg):
    a, b = points[seg[0]], points[seg[-1]]
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def stroke_caps(points, flags, rng, upm):
    """[(seg_index, seg, angle_deg)]：筆端段與其朝向。"""
    segs = segments(flags, rng)
    out = []
    if len(segs) < 3:
        return segs, out
    for k, seg in enumerate(segs):
        c = _chord(points, seg)
        if c > MAX_STEM * upm or c < 0.01 * upm:
            continue
        prev, nxt = segs[k - 1], segs[(k + 1) % len(segs)]
        if _chord(points, prev) < 1.5 * c or _chord(points, nxt) < 1.5 * c:
            continue
        a, b = points[prev[0]], points[nxt[-1]]
        body = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        mx, my = _mid(points, seg)
        out.append((k, seg, math.degrees(math.atan2(my - body[1], mx - body[0]))))
    return segs, out


def plan(points, end_pts, flags, upm):
    """在參考輪廓上決定要套哪些模板：[(kind, seg)]，kind ∈ pie | na | dot_tip | dot_round。"""
    ops = []
    for rng in contour_ranges(end_pts):
        segs, caps = stroke_caps(points, flags, rng, upm)
        for k, seg, ang in caps:
            offs = len(seg) - 2
            curved_sides = len(segs[k - 1]) > 2 and len(segs[(k + 1) % len(segs)]) > 2
            if offs >= 2 and -160 <= ang <= -100:
                ops.append(("pie", seg))
            elif offs >= 2 and -75 <= ang <= -25 and curved_sides:
                ops.append(("na", seg))
        if len(segs) == 4 and len(caps) == 2 and all(len(s) == 2 for _, s, _ in caps):
            (_, s1, a1), (_, s2, a2) = caps
            length = math.dist(_mid(points, s1), _mid(points, s2))
            axis = abs(a1) % 90
            top, bottom = (s1, s2) if _mid(points, s1)[1] > _mid(points, s2)[1] else (s2, s1)
            leftward = _mid(points, bottom)[0] < _mid(points, top)[0]
            limit = (DOT_MAX_LEN_LEFT if leftward else DOT_MAX_LEN) * upm
            if length <= limit and AXIS_TOL < axis < 90 - AXIS_TOL:
                ops.append(("dot_tip", top))
                ops.append(("dot_round", bottom))
    return ops


def _scale_about_mid(points, seg, factor):
    mx, my = _mid(points, seg)
    for i in seg:
        x, y = points[i]
        points[i] = (mx + (x - mx) * factor, my + (y - my) * factor)


def _pie(points, seg, params, upm):
    c = _chord(points, seg)
    target = max(c * params["pie_tip_pct"] / 100, params["pie_min_width"] / 1000 * upm)
    if target < c:
        _scale_about_mid(points, seg, target / c)


def _na(points, seg, params):
    """A = cap 較低的端點（平台起點），B = 尖端。"""
    a_i, b_i = (seg[-1], seg[0]) if points[seg[-1]][1] < points[seg[0]][1] else (seg[0], seg[-1])
    ax, ay = points[a_i]
    bx, by = points[b_i]
    w = math.dist((ax, ay), (bx, by))
    tip = (bx + params["na_tip_out_pct"] / 100 * w, ay + params["na_tip_rise_pct"] / 100 * w)
    points[b_i] = tip
    offs = seg[1:-1] if a_i == seg[-1] else seg[1:-1][::-1]   # 由 B 端排到 A 端
    n = len(offs)
    for m, i in enumerate(reversed(offs)):                    # m = 0 最靠近 A
        x = ax + (tip[0] - ax) * (m + 1) / (n + 1)
        y = ay if m < n - 1 else ay + (tip[1] - ay) * 0.3     # 平台，最後一點微微抬向尖端
        points[i] = (x, y)


def _dot_tip(points, seg, params, upm):
    c = _chord(points, seg)
    target = max(c * params["dot_tip_pct"] / 100, 0.006 * upm)
    if target < c:
        _scale_about_mid(points, seg, target / c)


def transform_structure(glyph_name, points, end_pts, flags, params, wght, ctx):
    upm = ctx["upm"]
    ops = plan(ctx["ref"], end_pts, flags, upm)
    if not ops:
        return points, end_pts, flags

    pts = list(points)
    rounds = {}
    for kind, seg in ops:
        if kind == "pie":
            _pie(pts, seg, params, upm)
        elif kind == "na":
            _na(pts, seg, params)
        elif kind == "dot_tip":
            _dot_tip(pts, seg, params, upm)
        else:
            rounds[seg[0]] = seg

    # 點的下端：在 cap 的兩個 on-curve 之間插入 off-curve，向外凸出成圓頭
    new_pts, new_flags, new_ends = [], [], []
    for rng in contour_ranges(end_pts):
        for i in rng:
            new_pts.append(pts[i])
            new_flags.append(flags[i])
            if i in rounds:
                seg = rounds[i]
                a, b = pts[seg[0]], pts[seg[-1]]
                mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
                dx, dy = b[0] - a[0], b[1] - a[1]
                c = math.hypot(dx, dy)
                # 填色在輪廓前進方向的右側（順時針），外側為左法向
                nx, ny = -dy / c, dx / c
                h = c * params["dot_round_pct"] / 100
                new_pts.append((mx + nx * h, my + ny * h))
                new_flags.append(0)
        new_ends.append(len(new_pts) - 1)
    return new_pts, new_ends, new_flags
