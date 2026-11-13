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


class Neighbourhood:
    """參考輪廓上「其他筆畫」的查詢：每個輪廓的多邊形近似與外框，只建一次。

    - owners(q, skip)：包含 q 的其他輪廓（以 range 起點表示）
    - clearance(p, u, max_d, skip)：從 p 沿單位向量 u 走，碰到其他輪廓前的距離（p 本身已在其中的輪廓不算）
    - attached(q_out, q_in, skip)：有其他輪廓包含 q_out 但不包含 q_in —— 該筆畫接在這裡、且在收縮範圍內結束，
      往內收會讓兩筆脫開
    """

    def __init__(self, points: list[Point], end_pts: list[int], flags: list[int]):
        self.polys = []
        for rng in contour_ranges(end_pts):
            poly = _flatten(points, flags, rng, steps=12)
            if poly:
                xs, ys = [p[0] for p in poly], [p[1] for p in poly]
                self.polys.append((rng.start, (min(xs), min(ys), max(xs), max(ys)), poly))

    def owners(self, q: Point, skip: range | None = None) -> set[int]:
        x, y = q
        s = skip.start if skip is not None else None
        return {k for k, (x0, y0, x1, y1), poly in self.polys
                if k != s and x0 <= x <= x1 and y0 <= y <= y1 and _poly_winding(poly, q)}

    def clearance(self, p: Point, u: tuple[float, float], max_d: float, skip: range | None = None,
                  step: float = 2.0) -> float:
        start = self.owners(p, skip)
        t = step
        while t <= max_d:
            if self.owners((p[0] + u[0] * t, p[1] + u[1] * t), skip) - start:
                return t
            t += step
        return max_d

    def attached(self, q_out: Point, q_in: Point, skip: range | None = None) -> bool:
        return bool(self.owners(q_out, skip) - self.owners(q_in, skip))

    def edge_attached(self, a: Point, b: Point, out: tuple[float, float], depth: float, skip: range,
                      r: float = 4.0) -> bool:
        """直線邊 a–b 往內收 depth 時，有沒有接在邊外側（r 以內）、且在收縮範圍內結束的其他筆畫。
        每 3 units 取樣：點尖可能只有幾 units 寬。"""
        n = max(2, math.ceil(math.dist(a, b) / 3))
        for t in range(1, n):
            x, y = a[0] + (b[0] - a[0]) * t / n, a[1] + (b[1] - a[1]) * t / n
            # 內外用同樣的容差：穿過的筆畫兩側都碰得到，互相抵消
            if self.near((x + out[0] * r / 2, y + out[1] * r / 2), skip, r / 2) - \
                    self.near((x - out[0] * (depth + 2), y - out[1] * (depth + 2)), skip, r / 2):
                return True
        return False

    def touching(self, rng: range, center: Point, radius: float, r: float = 2.0) -> bool:
        """輪廓 rng 在 center 周圍 radius 內的部分，有沒有碰到其他輪廓（收細筆端前檢查：
        接點可能在筆端附近的側邊，不一定在端緣上）。"""
        poly = next((poly for k, _, poly in self.polys if k == rng.start), [])
        for a, b in zip(poly, poly[1:] + poly[:1]):          # 沿邊每 3 units 取樣（多邊形近似的頂點太疏）
            n = max(1, math.ceil(math.dist(a, b) / 3))
            for t in range(n):
                v = (a[0] + (b[0] - a[0]) * t / n, a[1] + (b[1] - a[1]) * t / n)
                if math.dist(v, center) <= radius and self.near(v, rng, r):
                    return True
        return False

    def near(self, q: Point, skip: range | None = None, r: float = 2.0) -> set[int]:
        """q 周圍 r 以內碰到的其他輪廓。"""
        out = self.owners(q, skip)
        for ox, oy in ((r, 0), (-r, 0), (0, r), (0, -r)):
            out |= self.owners((q[0] + ox, q[1] + oy), skip)
        return out

    GAP_KEEP = 0.5     # 外長後至少保留原間距的比例
    GAP_MIN = 16.0     # font units；外長後至少保留的間距（原間距更小時不外長）；128 px 下約 2 px

    def room_factor(self, needs, skip: range | None = None) -> float:
        """needs = [(起點, 單位方向, 外長量)]：回傳外長量的倍率 0–1，讓每個方向外長後與其他筆畫的間距
        不小於 max(GAP_KEEP × 原間距, min(原間距, GAP_MIN))。"""
        f = 1.0
        for p, u, amount in needs:
            if amount <= 0:
                continue
            gap = self.clearance(p, u, amount + self.GAP_MIN + amount / (1 - self.GAP_KEEP) + 2, skip)
            allowed = max(0.0, gap - max(self.GAP_KEEP * gap, min(gap, self.GAP_MIN)))
            f = min(f, allowed / amount)
        return max(0.0, min(1.0, f))

    @staticmethod
    def fan(p, u, amount, angles=(-50, -25, 0, 25, 50)):
        """圓頭、肩：以 u 為中心的扇形方向，外長量隨角度的餘弦遞減。"""
        out = []
        for a in angles:
            r = math.radians(a)
            c, s = math.cos(r), math.sin(r)
            out.append((p, (u[0] * c - u[1] * s, u[0] * s + u[1] * c), amount * c))
        return out

    @staticmethod
    def along(a, b, u, amount_a, amount_b, spacing=6.0):
        """一條邊從 a 到 b 往 u 方向移動，兩端的量為 amount_a、amount_b：沿邊每 spacing units 取樣
        （鄰近筆畫的尖角可能只有十幾 units 寬，取樣太疏會漏掉）。"""
        n = max(2, math.ceil(math.dist(a, b) / spacing))
        return [((a[0] + (b[0] - a[0]) * t / n, a[1] + (b[1] - a[1]) * t / n), u,
                 amount_a + (amount_b - amount_a) * t / n) for t in range(n + 1)]
