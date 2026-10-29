"""筆畫模板：點、撇、捺，以及 0.102 的提、長點、鉤（Design Spec v0「點 / 捺 / 撇」「楷書筆意」）。

在參考 master 上把每個輪廓切成「段」（相鄰 on-curve 點之間，含其間的 off-curve），
找出筆端段（cap）：弦長 <= MAX_STEM，且前後兩段都比它長 1.5 倍以上。
cap 的朝向 = 從筆身（前後段遠端的中點）指向 cap 中點的方向。

- 撇（出鋒漸細，末端不留尖刺）：彎曲 cap（>= 2 個 off-curve）朝左下 [-160°, -100°]。
  cap 的點對 cap 中點縮放到 pie_tip_pct，但弦長不小於 pie_min_width，筆身自然收細、末端保留鈍頭
- 捺（收尾帶短平台再出鋒）：彎曲 cap 朝右下 [-75°, -25°]，且兩側都是曲線（排除豎鉤的轉角）。下端點 A 不動，
  cap 內的 off-curve 除最後一個外都排在 A 的水平線上形成平台，尖端 B 移到平台右上方 → 平台後出鋒
- 點（上尖下圓的錐形點）：只有 4 段、兩端都是直線 cap 的短斜筆（右點長度 <= DOT_MAX_LEN、左點 <= DOT_MAX_LEN_LEFT，
  近垂直者離垂直 > DOT_V_MIN 即為完整強度；近水平者離水平 DOT_H_RAMP 線性漸強）。上端 cap 收成尖（弦長縮到 dot_tip_pct）；
  下端 cap 插入一個 off-curve 變成圓頭 —— 會新增點，所以本模組是結構性 transform
- 提（策，0.102）：4 段、兩端直線 cap，左下往右上 TI_ANGLE、長度 TI_LEN，左下端在字寬 TI_MAX_X 內（左偏旁；
  與幾何相同的短撇區分）。朝向到 TI_FULL 才是完整強度。起筆（左下）cap 放大到 ti_head_pct 並插入圓頭（頓按），尖端（右上）縮到 ti_tip_pct
- 長點（側，0.102）：4 段、左上往右下 CHANGDIAN_ANGLE，比右點長、不超過 CHANGDIAN_MAX_LEN；頂端直線 cap；
  尾端為直線 cap，或為曲線 cap 但兩側皆直線（捺是尾端與兩側都彎）。頂端縮到 changdian_tip_pct，
  尾端放大到 changdian_press_pct，直線尾端再插入圓頭
- 鉤（趯，0.102）：彎曲 cap、輪廓在此折返（前後切線夾角 > 120°）、所在輪廓 >= HOOK_MIN_SEGS 段（鉤與前一筆連成一體），
  鉤尖朝左（|角度| >= 160°：豎鉤、彎鉤、橫折鉤）或朝右上 HOOK_RIGHT（臥鉤、斜鉤、豎彎鉤、豎提）。
  內側端點 = 筆畫轉彎的凹側（朝左取較高端、朝右上取較左上端）。cap 對內側端點縮到 hook_tip_pct（出鋒）；
  外側邊最靠近鉤尖的控制點跟著移動 hook_sweep_pct（上挑）；外側兩段中轉彎最大的一段，控制點往外推
  hook_press_pct × 鉤尖寬（鉤前頓筆）。只移動既有點

強度 s（0–1）：門檻附近線性漸強，避免同一個部件因為差 1° 而一個字有、一個字沒有（例：金字旁的提 11–14°）。
模板參數依 s 往「不變」內插：寬度比例 100 + (pct - 100) × s，圓頭凸出 × s。

所有判斷都在參考輪廓上做，每個 master 套用相同的點操作，點相容由 pipeline 驗證。
"""
from __future__ import annotations

import math

from geometry import contour_ranges

MAX_STEM = 0.16        # × UPM
DOT_MAX_LEN = 0.42     # × UPM，右點（左上→右下）的最大長度（永的首點約 0.40）
DOT_MAX_LEN_LEFT = 0.25  # × UPM，左點（右上→左下）的最大長度；更長的是短撇
DOT_V_MIN = 0.2        # 度，近垂直的點離垂直超過此值即為點（母體的豎畫離垂直正好 0°；灬、糸的點約 0.4–12°）
DOT_V_NEAR = 12        # 度，離垂直小於此值的點另有長度上限 DOT_V_MAX_LEN（排除弓的斜豎，約 2°、0.29 UPM）
DOT_V_MAX_LEN = 0.26   # × UPM
DOT_H_RAMP = (8, 25)   # 度，近水平的點離水平的角度：以下不套用，到上限才是完整強度（女的長橫約 3°）
TI_ANGLE = (5, 75)     # 度，提的尖端朝向（金、虫約 8–14°，扌、土約 15–25°，氵、冫約 60–64°）
TI_FULL = 25           # 度，提的朝向到此才是完整強度；較平的提（金、虫、王）只帶少許筆意
TI_LEN = (0.25, 0.48)  # × UPM；下限即左點上限，上限排除「也」的斜橫等長筆
TI_MAX_X = (0.45, 0.70)  # × 字寬：起筆端、尖端的 x 上限（提在左偏旁）
CHANGDIAN_ANGLE = (-70, -20)  # 度，長點尾端朝向
CHANGDIAN_MAX_LEN = 0.85      # × UPM，下限為 DOT_MAX_LEN（凶的乂右筆約 0.77）
HOOK_MIN_SEGS = 6             # 鉤所在輪廓的最少段數；獨立的 4 段筆畫是點、提、撇
HOOK_LEFT = 160               # 度，|角度| >= 此值為朝左的鉤
HOOK_RIGHT = (20, 100)        # 度，朝右上的鉤
HOOK_TURN = -0.5              # cap 前後切線的內積上限（< -0.5 即折返 > 120°）


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


def _unit(a, b):
    d = math.dist(a, b) or 1.0
    return ((b[0] - a[0]) / d, (b[1] - a[1]) / d)


def _turn(points, seg):
    """段的起點切線與終點切線的夾角（度）。"""
    t0, t1 = _unit(points[seg[0]], points[seg[1]]), _unit(points[seg[-2]], points[seg[-1]])
    return math.degrees(math.acos(max(-1.0, min(1.0, t0[0] * t1[0] + t0[1] * t1[1]))))


def _hook(points, segs, k, ang):
    """(cap, 內側端點, 上挑控制點 | None, 頓筆段 | None)；不是鉤則回傳 None。"""
    seg = segs[k]
    n = len(segs)
    prev, nxt = segs[k - 1], segs[(k + 1) % n]
    tp, tn = _unit(points[prev[-2]], points[prev[-1]]), _unit(points[nxt[0]], points[nxt[1]])
    if tp[0] * tn[0] + tp[1] * tn[1] > HOOK_TURN:
        return None
    left = abs(ang) >= HOOK_LEFT
    # 凹側法向：朝左的鉤順時針轉彎（取右法向），朝右上的鉤逆時針轉彎（取左法向）
    r = math.radians(ang + (-90 if left else 90))
    nx, ny = math.cos(r), math.sin(r)
    a, b = points[seg[0]], points[seg[-1]]
    inner_first = a[0] * nx + a[1] * ny >= b[0] * nx + b[1] * ny
    if inner_first:   # 外側邊在 cap 之後，沿輪廓前進
        inner, outer = seg[0], [nxt, segs[(k + 2) % n]]
        sweep = nxt[1] if len(nxt) > 2 else None
    else:             # 外側邊在 cap 之前
        inner, outer = seg[-1], [prev, segs[k - 2]]
        sweep = prev[-2] if len(prev) > 2 else None
    curved = [s for s in outer if len(s) > 2]
    bend = max(curved, key=lambda s: _turn(points, s)) if curved else None
    return seg, inner, sweep, bend


def plan(points, end_pts, flags, upm, advance=None):
    """在參考輪廓上決定要套哪些模板：[(kind, seg, s)]，s 為強度 0–1，
    kind ∈ pie | na | hook | dot_tip | dot_round | ti_tip | ti_head | changdian_tip | changdian_press；
    hook 的 seg 是 _hook() 的 tuple。"""
    advance = advance or upm
    ops = []
    for rng in contour_ranges(end_pts):
        segs, caps = stroke_caps(points, flags, rng, upm)
        for k, seg, ang in caps:
            offs = len(seg) - 2
            curved_sides = len(segs[k - 1]) > 2 and len(segs[(k + 1) % len(segs)]) > 2
            if (offs >= 2 and len(segs) >= HOOK_MIN_SEGS
                    and (abs(ang) >= HOOK_LEFT or HOOK_RIGHT[0] <= ang <= HOOK_RIGHT[1])):
                hook = _hook(points, segs, k, ang)
                if hook:
                    ops.append(("hook", hook, 1.0))
            elif offs >= 2 and -160 <= ang <= -100:
                ops.append(("pie", seg, 1.0))
            elif offs >= 2 and -75 <= ang <= -25 and curved_sides:
                ops.append(("na", seg, 1.0))
        if len(segs) == 4 and len(caps) == 2:
            ops += _four_segment(points, segs, caps, upm, advance)
    return ops


def _four_segment(points, segs, caps, upm, advance):
    """只有 4 段（兩個 cap + 兩側）的單筆：點、提、長點，三者條件互斥。"""
    (_, s1, a1), (_, s2, a2) = caps
    (top, a_top), (bottom, a_bot) = sorted(((s1, a1), (s2, a2)), key=lambda c: -_mid(points, c[0])[1])
    (tx, ty), (bx, by) = _mid(points, top), _mid(points, bottom)
    length = math.dist((tx, ty), (bx, by))
    straight_top, straight_bottom = len(top) == 2, len(bottom) == 2
    leftward = bx < tx

    if straight_top and straight_bottom:
        limit = (DOT_MAX_LEN_LEFT if leftward else DOT_MAX_LEN) * upm
        off_v, off_h = abs(abs(a1) - 90), min(abs(a1), 180 - abs(a1))
        if length <= limit:
            if off_v < off_h:
                if off_v <= DOT_V_MIN or (off_v < DOT_V_NEAR and length > DOT_V_MAX_LEN * upm):
                    return []
                k = 1.0
            else:
                if off_h <= DOT_H_RAMP[0]:
                    return []
                k = _ramp(off_h, *DOT_H_RAMP)
            return [("dot_tip", top, k), ("dot_round", bottom, k)]
        if (leftward and TI_ANGLE[0] < a_top <= TI_ANGLE[1]
                and TI_LEN[0] * upm < length <= TI_LEN[1] * upm
                and bx < TI_MAX_X[0] * advance and tx < TI_MAX_X[1] * advance):
            k = _ramp(a_top, TI_ANGLE[0], TI_FULL)
            return [("ti_tip", top, k), ("ti_head", bottom, k)]

    sides_straight = all(len(s) == 2 for s in segs if s is not top and s is not bottom)
    if (not leftward and CHANGDIAN_ANGLE[0] <= a_bot <= CHANGDIAN_ANGLE[1] and straight_top
            and (straight_bottom or sides_straight)
            and DOT_MAX_LEN * upm < length <= CHANGDIAN_MAX_LEN * upm):
        return [("changdian_tip", top, 1.0), ("changdian_press", bottom, 1.0)]
    return []


def _ramp(v, lo, hi):
    return max(0.0, min(1.0, (v - lo) / (hi - lo)))


def _eased(pct, k):
    """寬度比例 pct% 依強度 k 往 100%（不變）內插。"""
    return 100 + (pct - 100) * k


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


def _taper(points, seg, pct, min_width):
    """筆端收窄到 pct%，但弦長不小於 min_width。"""
    c = _chord(points, seg)
    target = max(c * pct / 100, min_width)
    if target < c:
        _scale_about_mid(points, seg, target / c)


def _hook_apply(points, hook, params, upm):
    seg, inner, sweep, bend = hook
    c = _chord(points, seg)
    if c == 0:
        return
    outer = seg[-1] if inner == seg[0] else seg[0]
    # 頓筆：轉彎外緣的控制點沿該段弦的左法向（外側）推出
    if bend:
        (ax, ay), (bx, by) = points[bend[0]], points[bend[-1]]
        dx, dy = bx - ax, by - ay
        d = math.hypot(dx, dy) or 1.0
        h = c * params["hook_press_pct"] / 100
        for i in bend[1:-1]:
            x, y = points[i]
            points[i] = (x - dy / d * h, y + dx / d * h)
    # 出鋒：cap 對內側端點縮放
    t = max(params["hook_tip_pct"] / 100, 0.008 * upm / c)
    ix, iy = points[inner]
    ox, oy = points[outer]
    for i in seg:
        if i != inner:
            x, y = points[i]
            points[i] = (ix + (x - ix) * t, iy + (y - iy) * t)
    if sweep is not None:
        nx_, ny_ = points[outer]
        k = params["hook_sweep_pct"] / 100
        x, y = points[sweep]
        points[sweep] = (x + (nx_ - ox) * k, y + (ny_ - oy) * k)


def transform_structure(glyph_name, points, end_pts, flags, params, wght, ctx):
    upm = ctx["upm"]
    ops = plan(ctx["ref"], end_pts, flags, upm, ctx.get("advance"))
    if not ops:
        return points, end_pts, flags

    pts = list(points)
    rounds = {}   # cap 起點 → (cap, 圓頭凸出 × 端寬 %)
    for kind, seg, k in ops:
        if kind == "pie":
            _pie(pts, seg, params, upm)
        elif kind == "na":
            _na(pts, seg, params)
        elif kind == "hook":
            _hook_apply(pts, seg, params, upm)
        elif kind == "dot_tip":
            _taper(pts, seg, _eased(params["dot_tip_pct"], k), 0.006 * upm)
        elif kind == "dot_round":
            rounds[seg[0]] = (seg, params["dot_round_pct"] * k)
        elif kind == "ti_tip":
            _taper(pts, seg, _eased(params["ti_tip_pct"], k), 0.008 * upm)
        elif kind == "ti_head":
            _scale_about_mid(pts, seg, _eased(params["ti_head_pct"], k) / 100)
            rounds[seg[0]] = (seg, params["ti_round_pct"] * k)
        elif kind == "changdian_tip":
            _taper(pts, seg, _eased(params["changdian_tip_pct"], k), 0.008 * upm)
        elif kind == "changdian_press":
            _scale_about_mid(pts, seg, _eased(params["changdian_press_pct"], k) / 100)
            if len(seg) == 2:   # 尾端原本是曲線就已經是圓的，不再插點
                rounds[seg[0]] = (seg, params["changdian_round_pct"] * k)

    # 點、提、長點的圓頭：在 cap 的兩個 on-curve 之間插入 off-curve，向外凸出
    new_pts, new_flags, new_ends = [], [], []
    for rng in contour_ranges(end_pts):
        for i in rng:
            new_pts.append(pts[i])
            new_flags.append(flags[i])
            if i in rounds:
                seg, pct = rounds[i]
                a, b = pts[seg[0]], pts[seg[-1]]
                mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
                dx, dy = b[0] - a[0], b[1] - a[1]
                c = math.hypot(dx, dy)
                # 填色在輪廓前進方向的右側（順時針），外側為左法向
                nx, ny = -dy / c, dx / c
                h = c * pct / 100
                new_pts.append((mx + nx * h, my + ny * h))
                new_flags.append(0)
        new_ends.append(len(new_pts) - 1)
    return new_pts, new_ends, new_flags
