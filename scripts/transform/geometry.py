"""Outline helpers shared by the transforms: contour ranges, straight edges, inside test."""
from __future__ import annotations

import math

Point = tuple[float, float]


def contour_ranges(end_pts: list[int]) -> list[range]:
    start = 0
    out = []
    for end in end_pts:
        out.append(range(start, end + 1))
        start = end + 1
    return out


def straight_edges(points: list[Point], end_pts: list[int], flags: list[int]) -> list[tuple[int, int]]:
    """(i, j) index pairs of consecutive on-curve points joined by a straight line."""
    edges = []
    for rng in contour_ranges(end_pts):
        idx = list(rng)
        for k, i in enumerate(idx):
            j = idx[(k + 1) % len(idx)]
            if flags[i] & 1 and flags[j] & 1 and i != j:
                edges.append((i, j))
    return edges


def neighbours(end_pts: list[int], i: int) -> tuple[int, int]:
    """Previous and next point index of i within its contour."""
    for rng in contour_ranges(end_pts):
        if i in rng:
            k = i - rng.start
            n = len(rng)
            return rng.start + (k - 1) % n, rng.start + (k + 1) % n
    raise IndexError(i)


def _flatten(points: list[Point], flags: list[int], rng: range, steps: int = 4) -> list[Point]:
    """Polyline approximation of one TrueType contour (quadratics, implied on-curve points)."""
    raw = [(points[i], bool(flags[i] & 1)) for i in rng]
    if not raw:
        return []
    # insert implied on-curve midpoints so on/off strictly alternate around every off-curve
    seq: list[tuple[Point, bool]] = []
    for k, (p, on) in enumerate(raw):
        q, q_on = raw[(k + 1) % len(raw)]
        seq.append((p, on))
        if not on and not q_on:
            seq.append((((p[0] + q[0]) / 2, (p[1] + q[1]) / 2), True))
    first = next(k for k, (_, on) in enumerate(seq) if on)
    seq = seq[first:] + seq[:first]
    poly: list[Point] = []
    n = len(seq)
    k = 0
    while k < n:
        p, _ = seq[k]
        poly.append(p)
        c, c_on = seq[(k + 1) % n]
        if c_on:
            k += 1
            continue
        e, _ = seq[(k + 2) % n]
        for s in range(1, steps):
            t = s / steps
            poly.append((
                (1 - t) ** 2 * p[0] + 2 * (1 - t) * t * c[0] + t * t * e[0],
                (1 - t) ** 2 * p[1] + 2 * (1 - t) * t * c[1] + t * t * e[1],
            ))
        k += 2
    return poly


def _poly_winding(poly: list[Point], q: Point) -> int:
    wn = 0
    x, y = q
    for a, b in zip(poly, poly[1:] + poly[:1]):
        if a[1] <= y < b[1] or b[1] <= y < a[1]:
            xi = a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if xi > x:
                wn += 1 if b[1] > a[1] else -1
    return wn


def winding(points: list[Point], end_pts: list[int], flags: list[int], q: Point,
            skip: range | None = None) -> int:
    """Nonzero winding number of q against the outline (optionally ignoring one contour)."""
    return sum(_poly_winding(_flatten(points, flags, rng), q)
               for rng in contour_ranges(end_pts) if rng != skip)


def inside(points, end_pts, flags, q, skip=None) -> bool:
    return winding(points, end_pts, flags, q, skip) != 0


def inside_own(points, end_pts, flags, i, q) -> bool:
    """q 是否在點 i 所屬的那一個輪廓內（筆畫多為互相重疊的獨立輪廓，判斷填色側只能看自己）。"""
    return _poly_winding(_flatten(points, flags, contour_of(end_pts, i)), q) != 0


def contour_of(end_pts: list[int], i: int) -> range:
    for rng in contour_ranges(end_pts):
        if i in rng:
            return rng
    raise IndexError(i)


def length(a: Point, b: Point) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


FLAT = 1.0  # 視為水平 / 垂直的最大偏差（font units）


def stem_pairs(points: list[Point], end_pts: list[int], flags: list[int], max_stem: float,
               axis: str = "h") -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """[(edge, partner)]：每條平行於 axis 的直線邊，與同一筆畫另一緣的配對。

    axis="h" 找橫畫（水平邊上下配對），axis="v" 找豎畫（垂直邊左右配對）。
    配對條件：填色側相反、在垂直方向上最近、重疊長度 >= 1.2 倍距離、距離 <= max_stem、兩邊中間為填色。
    """
    a, b = (0, 1) if axis == "h" else (1, 0)    # a: 邊的方向分量, b: 筆寬方向分量

    edges = [(i, j) for i, j in straight_edges(points, end_pts, flags)
             if abs(points[i][b] - points[j][b]) <= FLAT and abs(points[i][a] - points[j][a]) > FLAT]

    def probe(along, across):
        return (along, across) if axis == "h" else (across, along)

    def fill_low(e):
        i, j = e
        return inside_own(points, end_pts, flags, i, probe((points[i][a] + points[j][a]) / 2, points[i][b] - 2))

    kinds = {e: fill_low(e) for e in edges}
    pairs = []
    for e in edges:
        e0, e1 = sorted((points[e[0]][a], points[e[1]][a]))
        ec = points[e[0]][b]
        low = kinds[e]
        best = None
        for f in edges:
            if f == e or kinds[f] == low:
                continue
            fc = points[f[0]][b]
            d = (ec - fc) if low else (fc - ec)
            if d <= FLAT or d > max_stem:
                continue
            f0, f1 = sorted((points[f[0]][a], points[f[1]][a]))
            lo, hi = max(e0, f0), min(e1, f1)
            if hi - lo < 1.2 * d:
                continue
            if not inside(points, end_pts, flags, probe((lo + hi) / 2, (ec + fc) / 2)):
                continue
            if best is None or d < best[0]:
                best = (d, f)
        if best:
            pairs.append((e, best[1]))
    return pairs


def propagate(locked: dict[int, float], ref: list[Point], end_pts: list[int], flags: list[int],
              coord: int) -> dict[int, float]:
    """把鎖定點的位移沿「同一條水平 / 垂直線」擴散到相連的點（coord 0 = x、1 = y）。

    與鎖定點在 coord 上相差 <= FLAT 的相鄰點（含 off-curve 切線點）用同樣的位移，
    避免共線的短邊或幾乎重合的點被拆開而自交（例：不、進 的轉折處）。
    """
    out = dict(locked)
    stack = list(locked)
    while stack:
        i = stack.pop()
        for n in neighbours(end_pts, i):
            if n not in out and abs(ref[n][coord] - ref[i][coord]) <= FLAT:
                out[n] = out[i]
                stack.append(n)
    return out
