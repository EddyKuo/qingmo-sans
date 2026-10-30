"""楷書筆意：橫（勒）、豎（努）的起筆與收筆（0.103，Design Spec v0「楷書筆意」）。

筆端沿用 terminals.stroke_ends 在參考輪廓上找（短直線端緣、兩側為垂直的長直線邊、看得見），
每個筆端依當前 master 的端緣寬 w 套用模板；端緣插入的 off-curve 讓筆端變圓，會新增點，所以本模組是結構性 transform。

- 橫的起筆（左端）：上角抬高 heng_head_raise × w（頓按），端緣往左外凸 heng_head_round × w
- 橫的收筆（右端）：上角抬高 heng_tail_raise × w、下角壓低 heng_tail_drop × w（往右下頓筆），
  端緣往右下外凸 heng_tail_round × w
- 橫的細腰：獨立的 4 點橫畫，上下兩條長邊各插入一個 off-curve 往內收 heng_waist × w（中段曲線內收約一半）
- 豎的起筆（上端）：右角往右推 shu_head_flare × w（頓筆），端緣往右上外凸 shu_head_round × w
- 豎的收筆（下端）：垂露 —— 端緣放寬到 shu_tail_press_pct，往下外凸 shu_tail_round × w；
  懸針 —— 獨立的 4 點豎畫、長度 >= XUANZHEN_LEN、位置居中（字寬 XUANZHEN_X）、下端是整字最低處、
  穿過其他筆畫且上方露頭超過 XUANZHEN_STUB × w（十、中、年；「下」的豎掛在橫下面，是垂露），
  並且沒有曲線筆畫（撇、捺）貼著它（木、東、本的豎是垂露）：
  兩側在離下端 xuanzhen_len × w 處插入 on-curve，下端縮到 xuanzhen_tip_pct，側邊以二次曲線收成針尖

主筆與副筆（0.103）：每個筆端的強度 s = brush_minor + (1 - brush_minor) × ramp(L / Lmax, MAJOR_RAMP)，
L 是該筆端所在筆畫的長度（端緣兩側長直線邊的較長者），Lmax 是同一字同方向（橫或豎）最長的筆畫；
字裡最長的橫、豎是主筆，完整強度，短筆只帶 brush_minor 的強度，避免每一筆都一樣重。所有量再乘 brush_strength。
橫的筆勢（heng_tilt_deg，楷意版本）：兩端都是筆端的獨立橫畫以左端為軸剪切，右端抬高，成「左低右高」。

terminals 已在每個 master 做了 12° 斜切與收筆微收，本模組在其結果上再移動，所有量都以當前端緣寬計算。
"""
from __future__ import annotations

import math

from geometry import _flatten, _poly_winding, contour_of, contour_ranges, inside, neighbours
from terminals import stroke_ends

XUANZHEN_LEN = 0.45        # × UPM，懸針的豎畫長度下限
XUANZHEN_X = (0.30, 0.70)  # × 字寬，懸針的豎畫中線範圍
XUANZHEN_BOTTOM = 0.03     # × UPM，下端離整字最低處的距離上限
XUANZHEN_STUB = 2.5        # × w，懸針穿過的筆畫以上至少要露出的長度
MAJOR_RAMP = (0.45, 0.9)   # L / Lmax：以下為副筆強度，以上為主筆


def _rect(end_pts, flags, i):
    """i 所在輪廓為 4 個 on-curve 點的矩形時回傳其 range。"""
    rng = contour_of(end_pts, i)
    return rng if len(rng) == 4 and all(flags[k] & 1 for k in rng) else None


def _stroke_len(points, end_pts, i, j):
    """筆端所在筆畫的長度：端緣兩側長直線邊的較長者。"""
    p, _ = neighbours(end_pts, i)
    _, n = neighbours(end_pts, j)
    return max(math.dist(points[p], points[i]), math.dist(points[j], points[n]))


def _ramp(v, lo, hi):
    return max(0.0, min(1.0, (v - lo) / (hi - lo)))


def plan(points, end_pts, flags, upm, advance=None, minor=1.0):
    """[(kind, i, j, s)]，kind ∈ heng_head | heng_tail | shu_head | chuilu | xuanzhen | waist | tilt；
    waist 的 (i, j) 是要內收的長邊，tilt 的 (i, j) 是獨立橫畫的 (range 起點, 左端 x)；s 為主筆 / 副筆強度。"""
    advance = advance or upm
    ends = stroke_ends(points, end_pts, flags, upm)
    if not ends:
        return []
    ymin = min(y for _, y in points)
    lens = {(i, j): _stroke_len(points, end_pts, i, j) for _, i, j in ends}
    lmax = {}
    for kind, i, j in ends:
        lmax[kind[0]] = max(lmax.get(kind[0], 0), lens[(i, j)])
    ops, h_rects = [], {}
    for kind, i, j in ends:
        s = minor + (1 - minor) * _ramp(lens[(i, j)] / lmax[kind[0]], *MAJOR_RAMP)
        if kind == "h_entry":
            ops.append(("heng_head", i, j, s))
        elif kind == "h_exit":
            ops.append(("heng_tail", i, j, s))
        elif kind == "v_entry":
            ops.append(("shu_head", i, j, s))
        else:
            ops.append((_v_tail(points, end_pts, flags, i, j, upm, advance, ymin), i, j, s))
        rng = _rect(end_pts, flags, i)
        if rng is not None and kind.startswith("h_"):
            h_rects.setdefault(rng, {})[kind] = s
    for rng, kinds in h_rects.items():
        if len(kinds) == 2:
            idx = list(rng)
            s = max(kinds.values())
            ops.append(("tilt", rng.start, min(points[k][0] for k in idx), s))
            for k, a in enumerate(idx):
                b = idx[(k + 1) % 4]
                if abs(points[a][1] - points[b][1]) <= 1.0:   # 水平的長邊
                    ops.append(("waist", a, b, s))
    return ops


def _v_tail(points, end_pts, flags, i, j, upm, advance, ymin):
    rng = _rect(end_pts, flags, i)
    if rng is None:
        return "chuilu"
    ys = [points[k][1] for k in rng]
    cx = sum(points[k][0] for k in rng) / 4
    if not (max(ys) - min(ys) >= XUANZHEN_LEN * upm
            and XUANZHEN_X[0] * advance <= cx <= XUANZHEN_X[1] * advance
            and min(ys) - ymin <= XUANZHEN_BOTTOM * upm):
        return "chuilu"
    xs = [points[k][0] for k in rng]
    w, top, bottom = max(xs) - min(xs), max(ys), min(ys)
    steps = [bottom + (top - bottom) * t / 40 for t in range(1, 40)]
    # 穿過其他筆畫，且交會處以上露頭
    covered = [y for y in steps if inside(points, end_pts, flags, (cx, y), skip=rng)]
    if not covered or top - min(covered) < XUANZHEN_STUB * w:
        return "chuilu"
    # 撇、捺（含曲線的輪廓）貼著豎畫的兩側
    curved = [_flatten(points, flags, r) for r in contour_ranges(end_pts)
              if r != rng and any(not flags[k] & 1 for k in r)]
    for poly in curved:
        for y in steps:
            if any(_poly_winding(poly, (x, y)) for x in (min(xs) - 0.6 * w, max(xs) + 0.6 * w)):
                return "chuilu"
    return "xuanzhen"


def _unit(dx, dy):
    d = math.hypot(dx, dy) or 1.0
    return dx / d, dy / d


def transform_structure(glyph_name, points, end_pts, flags, params, wght, ctx):
    upm = ctx["upm"]
    ops = plan(ctx["ref"], end_pts, flags, upm, ctx.get("advance"), params.get("brush_minor", 100) / 100)
    if not ops:
        return points, end_pts, flags

    pts = list(points)
    gain = params.get("brush_strength", 100) / 100
    # 橫的筆勢：獨立橫畫以左端為軸剪切（先做，後面的量以剪切後的位置計算）
    tan = math.tan(math.radians(params.get("heng_tilt_deg", 0)))
    for kind, start, x0, s in ops:
        if kind == "tilt" and tan:
            for k in range(start, start + 4):
                pts[k] = (pts[k][0], pts[k][1] + (pts[k][0] - x0) * tan)
    after = {}    # 點 i → 插在 i 之後的 [(x, y), flag]

    def add(i, p, on=False):
        after.setdefault(i, []).append((p, 1 if on else 0))

    def mid(a, b):
        return ((pts[a][0] + pts[b][0]) / 2, (pts[a][1] + pts[b][1]) / 2)

    base = {k: v / 100 for k, v in params.items() if k.startswith(("heng_", "shu_", "xuanzhen_"))}
    # 先移動既有點，再依移動後的位置插點
    inserts = []
    for kind, i, j, s in ops:
        if kind in ("waist", "tilt"):
            continue
        g = gain * s
        pct = {k: (1 + (v - 1) * g if k.endswith("_pct") else v * g) for k, v in base.items()}
        pct["xuanzhen_len"] = base["xuanzhen_len"]
        w = math.dist(pts[i], pts[j])
        if kind == "heng_head":
            top = i if pts[i][1] > pts[j][1] else j
            pts[top] = (pts[top][0], pts[top][1] + pct["heng_head_raise"] * w)
            inserts.append((i, j, (-1.0, 0.0), pct["heng_head_round"] * w))
        elif kind == "heng_tail":
            top, bot = (i, j) if pts[i][1] > pts[j][1] else (j, i)
            pts[top] = (pts[top][0], pts[top][1] + pct["heng_tail_raise"] * w)
            pts[bot] = (pts[bot][0], pts[bot][1] - pct["heng_tail_drop"] * w)
            inserts.append((i, j, _unit(1.0, -0.35), pct["heng_tail_round"] * w))
        elif kind == "shu_head":
            right = i if pts[i][0] > pts[j][0] else j
            pts[right] = (pts[right][0] + pct["shu_head_flare"] * w, pts[right][1])
            inserts.append((i, j, _unit(0.35, 1.0), pct["shu_head_round"] * w))
        elif kind == "chuilu":
            left, right = (i, j) if pts[i][0] < pts[j][0] else (j, i)
            s = (pct["shu_tail_press_pct"] - 1) / 2 * w
            pts[left] = (pts[left][0] - s, pts[left][1])
            pts[right] = (pts[right][0] + s, pts[right][1])
            inserts.append((i, j, (0.0, -1.0), pct["shu_tail_round"] * w))
        else:   # xuanzhen
            p, _ = neighbours(end_pts, i)
            _, n = neighbours(end_pts, j)
            mx, my = mid(i, j)
            for corner, side in ((i, p), (j, n)):
                ux, uy = _unit(pts[side][0] - pts[corner][0], pts[side][1] - pts[corner][1])
                L = min(pct["xuanzhen_len"] * w, 0.6 * math.dist(pts[side], pts[corner]))
                cx, cy = pts[corner]
                on = (cx + ux * L, cy + uy * L)
                off = (cx + ux * L * 0.4, cy + uy * L * 0.4)
                if corner == i:   # 沿輪廓：side → on → off → i
                    add(p, on, True)
                    add(p, off)
                else:             # j → off → on → side
                    add(j, off)
                    add(j, on, True)
            t = pct["xuanzhen_tip_pct"]
            for k in (i, j):
                pts[k] = (mx + (pts[k][0] - mx) * t, my + (pts[k][1] - my) * t)
    for i, j, (ux, uy), h in inserts:
        mx, my = mid(i, j)
        add(i, (mx + ux * h, my + uy * h))
    for kind, a, b, s in ops:
        if kind != "waist":
            continue
        rng = contour_of(end_pts, a)
        cy = sum(pts[k][1] for k in rng) / 4
        w = abs(pts[a][1] - cy) * 2
        mx, my = mid(a, b)
        add(a, (mx, my + math.copysign(base["heng_waist"] * gain * s * w, cy - my)))

    new_pts, new_flags, new_ends = [], [], []
    for rng in contour_ranges(end_pts):
        for i in rng:
            new_pts.append(pts[i])
            new_flags.append(flags[i])
            for p, f in after.get(i, ()):
                new_pts.append(p)
                new_flags.append(f)
        new_ends.append(len(new_pts) - 1)
    return new_pts, new_ends, new_flags
