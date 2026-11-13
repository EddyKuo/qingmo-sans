"""楷書筆意：橫（勒）、豎（努）的起筆與收筆（0.103，Design Spec v0「楷書筆意」）。

筆端沿用 terminals.stroke_ends 在參考輪廓上找（短直線端緣、兩側為垂直的長直線邊、看得見），
每個筆端依當前 master 的端緣寬 w 套用模板；端緣插入的 off-curve 讓筆端變圓，會新增點，所以本模組是結構性 transform。

- 橫的起筆（左端）：上角抬高 heng_head_raise × w（頓按），端緣往左外凸 heng_head_round × w
- 橫的收筆（右端）：上角抬高 heng_tail_raise × w、下角壓低 heng_tail_drop × w（往右下頓筆），
  端緣往右下外凸 heng_tail_round × w
- 橫的細腰：獨立的 4 點橫畫，上下兩條長邊的中點各插入一個 on-curve，往內收 heng_waist / 2 × w（極淺的折線）。
  0.104 前用一個 off-curve 做成整條長邊的平緩曲線：又長又平的二次曲線（內凹量 1–20 units、長數百 units）
  在帶 OVERLAP_SIMPLE 的可變字型裡會讓 FreeType 在 300–1500 px 渲染失敗（raster overflow）
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

複合輪廓的轉角（0.104）：口、日、國的框是「冂」形的一個輪廓，橫與豎在轉角相接，沒有獨立的筆端。
在順時針外輪廓上找凸角：前後都是長度 >= 1.5w 的水平 / 垂直直線邊、看得見，且同一輪廓裡有對應的內角
（往內 MAX_STEM 以內），由兩者的距離量出橫、豎的筆寬，w 取平均：
- 起筆角（左上：由下往上接往右）：豎與橫一起起筆，轉角換成 on–off–on 的圓角（轉角點本身移到圓角起點，不改成 off-curve），半徑 shu_qi_round × w，
  控制點往左上外推 shu_qi_bump × w（頓按）
- 折角（右上：往右接往下，橫折）：頓筆的「肩」，半徑 heng_zhe_round × w，控制點往右上外推 heng_zhe_bump × w
其餘轉角（豎折、左下、右下）仍由 corners 做墨暈軟角。轉角換成曲線後 corners 不會再處理它。

鄰近筆畫保護（0.104，與 strokes 相同）：外長的量（抬高、壓低、外推、圓頭、肩、傾斜）沿移動的邊逐點、
圓頭與肩以扇形多方向，量到其他筆畫的距離，外長後的間距不小於 Neighbourhood.room_factor 的下限；
往內收的細腰、傾斜遇到接在邊上的筆畫就不做。

terminals 已在每個 master 做了 12° 斜切與收筆微收，本模組在其結果上再移動，所有量都以當前端緣寬計算。
"""
from __future__ import annotations

import math

from geometry import Neighbourhood, _flatten, _poly_winding, contour_of, contour_ranges, inside, neighbours
from terminals import stroke_ends

XUANZHEN_LEN = 0.45        # × UPM，懸針的豎畫長度下限
XUANZHEN_X = (0.30, 0.70)  # × 字寬，懸針的豎畫中線範圍
XUANZHEN_BOTTOM = 0.03     # × UPM，下端離整字最低處的距離上限
XUANZHEN_STUB = 2.5        # × w，懸針穿過的筆畫以上至少要露出的長度
MAJOR_RAMP = (0.45, 0.9)   # L / Lmax：以下為副筆強度，以上為主筆
MAX_STEM = 0.16            # × UPM，轉角到對應內角的最大距離（筆寬上限）
CORNER_KINDS = {((0, 1), (1, 0)): ("qi", (1, -1)),     # 左上起筆角：內角在右下
                ((1, 0), (0, -1)): ("zhe", (-1, -1))}  # 右上折角：內角在左下


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


def _axis_unit(a, b):
    """a→b 為水平 / 垂直直線時回傳單位向量（整數），否則 None。"""
    dx, dy = b[0] - a[0], b[1] - a[1]
    if abs(dy) <= 1.0 and abs(dx) > 1.0:
        return (1 if dx > 0 else -1, 0)
    if abs(dx) <= 1.0 and abs(dy) > 1.0:
        return (0, 1 if dy > 0 else -1)
    return None


def _signed_area(points, rng):
    idx = list(rng)
    return sum(points[i][0] * points[idx[(k + 1) % len(idx)]][1]
               - points[idx[(k + 1) % len(idx)]][0] * points[i][1] for k, i in enumerate(idx)) / 2


def corners(points, end_pts, flags, upm):
    """[(kind, P, q)]：複合輪廓的起筆角 / 折角 P 與其對應內角 q，kind ∈ qi | zhe。"""
    out = []
    for rng in contour_ranges(end_pts):
        if len(rng) < 6 or _signed_area(points, rng) >= 0:      # 只看順時針外輪廓；矩形是獨立筆畫
            continue
        ons = [k for k in rng if flags[k] & 1]
        for i in ons:
            p, n = neighbours(end_pts, i)
            if not (flags[p] & 1 and flags[n] & 1):
                continue
            key = (_axis_unit(points[p], points[i]), _axis_unit(points[i], points[n]))
            if key not in CORNER_KINDS:
                continue
            kind, (sx, sy) = CORNER_KINDS[key]
            P = points[i]
            cand = [k for k in ons if k != i
                    and 0 < (points[k][0] - P[0]) * sx <= MAX_STEM * upm
                    and 0 < (points[k][1] - P[1]) * sy <= MAX_STEM * upm]
            if not cand:
                continue
            q = min(cand, key=lambda k: math.dist(points[k], P))
            w = (abs(points[q][0] - P[0]) + abs(points[q][1] - P[1])) / 2
            if min(math.dist(points[p], P), math.dist(P, points[n])) < 1.5 * w:
                continue
            if inside(points, end_pts, flags, P, skip=rng):
                continue
            out.append((kind, i, q))
    return out


def plan(points, end_pts, flags, upm, advance=None, minor=1.0):
    """[(kind, i, j, s)]，kind ∈ heng_head | heng_tail | shu_head | chuilu | xuanzhen | waist | tilt | qi | zhe；
    waist 的 (i, j) 是要內收的長邊，tilt 的 (i, j) 是獨立橫畫的 (range 起點, 左端 x)，
    qi / zhe 的 (i, j) 是轉角與對應內角；s 為主筆 / 副筆強度。"""
    advance = advance or upm
    ends = stroke_ends(points, end_pts, flags, upm)
    corner_ops = [(kind, i, q, 1.0) for kind, i, q in corners(points, end_pts, flags, upm)]
    if not ends:
        return corner_ops
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
    return ops + corner_ops


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
    flags = list(flags)
    gain = params.get("brush_strength", 100) / 100
    base = {k: v / 100 for k, v in params.items() if k.startswith(("heng_", "shu_", "xuanzhen_"))}
    hood = Neighbourhood(ctx["ref"], end_pts, flags)
    # 傾斜不分主副筆，只受鄰近筆畫限制；其餘乘上主副筆強度
    ops = [(kind, i, j, (1.0 if kind == "tilt" else s) * _room(hood, ctx["ref"], end_pts, kind, i, j, s * gain, base, params))
           for kind, i, j, s in ops]
    # 橫的筆勢：獨立橫畫以左端為軸剪切（先做，後面的量以剪切後的位置計算）
    tan = math.tan(math.radians(params.get("heng_tilt_deg", 0)))
    for kind, start, x0, s in ops:
        if kind == "tilt" and tan and s > 0:
            for k in range(start, start + 4):
                pts[k] = (pts[k][0], pts[k][1] + (pts[k][0] - x0) * tan * min(1.0, s))
    after = {}    # 點 i → 插在 i 之後的 [(x, y), flag]

    def add(i, p, on=False, key=None):
        # key：同一條邊上多個插入點的排序依據，預設為離點 i（移動前）的距離
        after.setdefault(i, []).append((p, 1 if on else 0, key))

    def mid(a, b):
        return ((pts[a][0] + pts[b][0]) / 2, (pts[a][1] + pts[b][1]) / 2)

    # 先移動既有點，再依移動後的位置插點
    inserts = []
    for kind, i, j, s in ops:
        if kind in ("waist", "tilt", "qi", "zhe"):
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
        if kind != "waist" or s <= 0:
            continue
        rng = contour_of(end_pts, a)
        cy = sum(pts[k][1] for k in rng) / 4
        w = abs(pts[a][1] - cy) * 2
        mx, my = mid(a, b)
        add(a, (mx, my + math.copysign(base["heng_waist"] / 2 * gain * s * w, cy - my)), True)

    # 複合輪廓的轉角：P 移到圓角起點（仍是 on-curve），其後插入外推的 off-curve 與圓角終點。
    # P 不改成 off-curve：P 可能是輪廓第一點，帶著 OVERLAP_SIMPLE 旗標，第一點變 off-curve 會讓 FreeType 在
    # 256 px 以上渲染失敗（raster overflow）
    origin = list(pts)
    for kind, i, q, s in ops:
        if kind not in ("qi", "zhe"):
            continue
        p, n = neighbours(end_pts, i)
        P = pts[i]
        u_in = _unit(P[0] - pts[p][0], P[1] - pts[p][1])
        u_out = _unit(pts[n][0] - P[0], pts[n][1] - P[1])
        w = (abs(pts[q][0] - P[0]) + abs(pts[q][1] - P[1])) / 2
        r, bump = (("shu_qi_round", "shu_qi_bump") if kind == "qi" else ("heng_zhe_round", "heng_zhe_bump"))
        r, bump = base[r] * gain * s * w, base[bump] * gain * s * w
        bx, by = _unit(u_in[0] - u_out[0], u_in[1] - u_out[1])
        add(i, (P[0] + bump * bx, P[1] + bump * by), key=0.0)
        add(i, (P[0] + r * u_out[0], P[1] + r * u_out[1]), True, key=r)
        pts[i] = (P[0] - r * u_in[0], P[1] - r * u_in[1])

    new_pts, new_flags, new_ends = [], [], []
    for rng in contour_ranges(end_pts):
        for i in rng:
            new_pts.append(pts[i])
            new_flags.append(flags[i])
            # 同一條邊上插入多個點時，依離起點的距離排序（例：兩個相鄰轉角的圓角端點）
            items = after.get(i, ())
            for p, f, _ in sorted(items, key=lambda e: math.dist(e[0], origin[i]) if e[2] is None else e[2]):
                new_pts.append(p)
                new_flags.append(f)
        new_ends.append(len(new_pts) - 1)
    return new_pts, new_ends, new_flags


def _far(end_pts, k, other):
    """筆端角點 k 沿長邊的另一端（k 的鄰點中不是端緣另一點的那個）。"""
    p, n = neighbours(end_pts, k)
    return n if p == other else p


def _room(hood, ref, end_pts, kind, i, j, g, base, params):
    """鄰近筆畫保護：回傳強度倍率（0 = 不套用，1 = 完整），在參考輪廓上量。g = brush_strength × 主副筆強度。"""
    rng = contour_of(end_pts, i)
    if kind == "xuanzhen":
        return 1.0
    if kind == "waist":
        a, b = ref[i], ref[j]
        cy = sum(ref[k][1] for k in rng) / len(rng)
        out = 1 if a[1] > cy else -1
        depth = base["heng_waist"] / 2 * g * abs(a[1] - cy) * 2
        return 0.0 if hood.edge_attached(a, b, (0.0, out), depth, rng) else 1.0
    need = []          # (起點, 方向, 外長量)
    if kind == "tilt":
        idx = list(range(i, i + 4))
        tan = math.tan(math.radians(params.get("heng_tilt_deg", 0)))
        if tan <= 0:
            return 1.0
        ys = sorted({round(ref[k][1]) for k in idx})
        top = [k for k in idx if ref[k][1] >= ys[-1] - 1]
        bottom = [k for k in idx if ref[k][1] < ys[-1] - 1]
        if len(top) != 2 or len(bottom) != 2:
            return 1.0
        # 整條上緣往上抬（越右越多）；下緣往上離開時，接在下緣的筆畫會脫開
        a, b = sorted((ref[k] for k in top))
        need += hood.along(a, b, (0.0, 1.0), (a[0] - j) * tan, (b[0] - j) * tan)
        # 四個角：原本碰到的筆畫，抬高後要仍碰得到（橫的右端頂在豎上，抬高後會脫開）
        for k in idx:
            x, y = ref[k]
            if hood.near((x, y), rng) - hood.near((x, y + (x - j) * tan), rng):
                return 0.0
        a, b = sorted(ref[k] for k in bottom)
        if hood.edge_attached(a, b, (0.0, -1.0), (b[0] - j) * tan, rng):
            return 0.0
    elif kind in ("qi", "zhe"):
        P, q = ref[i], ref[j]
        w = (abs(q[0] - P[0]) + abs(q[1] - P[1])) / 2
        p, n = neighbours(end_pts, i)
        u_in = _unit(P[0] - ref[p][0], P[1] - ref[p][1])
        u_out = _unit(ref[n][0] - P[0], ref[n][1] - P[1])
        bump = base["shu_qi_bump" if kind == "qi" else "heng_zhe_bump"] * g * w
        need += hood.fan(P, _unit(u_in[0] - u_out[0], u_in[1] - u_out[1]), bump)
    else:
        a, b = ref[i], ref[j]
        w = math.dist(a, b)
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        top, bot = (i, j) if a[1] > b[1] else (j, i)
        left, right = (i, j) if a[0] < b[0] else (j, i)

        def edge(k, other, u, amount):      # 角點 k 移動，長邊另一端不動
            return hood.along(ref[_far(end_pts, k, other)], ref[k], u, 0.0, amount)
        if kind == "heng_head":
            need += edge(top, bot, (0.0, 1.0), base["heng_head_raise"] * g * w)
            need += hood.fan(mid, (-1.0, 0.0), base["heng_head_round"] * g * w)
        elif kind == "heng_tail":
            need += edge(top, bot, (0.0, 1.0), base["heng_tail_raise"] * g * w)
            need += edge(bot, top, (0.0, -1.0), base["heng_tail_drop"] * g * w)
            need += hood.fan(mid, _unit(1.0, -0.35), base["heng_tail_round"] * g * w)
        elif kind == "shu_head":
            need += edge(right, left, (1.0, 0.0), base["shu_head_flare"] * g * w)
            need += hood.fan(mid, _unit(0.35, 1.0), base["shu_head_round"] * g * w)
        elif kind == "chuilu":
            grow = (base["shu_tail_press_pct"] - 1) * g / 2 * w
            need += edge(left, right, (-1.0, 0.0), grow) + edge(right, left, (1.0, 0.0), grow)
            need += hood.fan(mid, (0.0, -1.0), base["shu_tail_round"] * g * w)
    return hood.room_factor(need, rng)
