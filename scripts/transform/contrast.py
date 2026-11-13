"""筆畫對比：橫畫相對豎畫變細（spec: style.contrast_h_over_v = 0.82）。

- 在參考 master（ctx["ref"]，預設 wght 400）上找出水平直線邊，依填色側分成「上緣」（填色在下）
  與「下緣」（填色在上），每條邊配對 x 重疊、距離最近、且中間為填色的相反類型邊 = 一個橫畫
- 橫畫寬 d 在當前 master 上量，兩緣各向內移動 (1 - ratio) * d / 2，點數不變
- 與移動邊共線相連的點（含切線 off-curve）跟著移動，曲線切線保持水平、短邊不被拆開
- 只處理「長橫」：重疊長度 >= 1.2 * d，且 d <= MAX_STEM；新寬度不小於 MIN_WIDTH
- 接點保護（0.104）：有其他筆畫接在這條邊外側、且在內收範圍內結束（貝的撇點接在目的底橫下緣），
  這條邊不動，只收另一緣；否則兩筆會脫開。穿過橫畫的筆畫不受影響
"""
from __future__ import annotations

from geometry import Neighbourhood, contour_of, propagate, stem_pairs

MAX_STEM = 0.16      # × UPM，參考 master 上視為筆畫的最大寬度
MIN_WIDTH = 0.012    # × UPM，變細後的下限


def transform(glyph_name, points, end_pts, flags, params, wght, ctx):
    ratio = params["contrast_h_over_v"]
    if ratio >= 1:
        return points
    upm = ctx["upm"]
    ref = ctx["ref"]
    shifts: dict[int, list[float]] = {}
    hood = None
    for e, f in stem_pairs(ref, end_pts, flags, MAX_STEM * upm, "h"):
        hood = hood or Neighbourhood(ref, end_pts, flags)
        if _attached(hood, ref, end_pts, e, f, ratio):
            continue
        ey, fy = points[e[0]][1], points[f[0]][1]
        d = abs(ey - fy)
        s = min((1 - ratio) * d / 2, max(0.0, (d - MIN_WIDTH * upm) / 2))
        dy = -s if ey > fy else s
        for i in e:
            shifts.setdefault(i, []).append(dy)

    out = list(points)
    moved = propagate({i: sum(v) / len(v) for i, v in shifts.items()}, ref, end_pts, flags, 1)
    for i, dy in moved.items():
        x, y = out[i]
        out[i] = (x, y + dy)
    return out


def _attached(hood, ref, end_pts, e, f, ratio):
    """參考輪廓上，邊 e 外側有筆畫接著、且在內收量內結束。"""
    ey, fy = ref[e[0]][1], ref[f[0]][1]
    out = (0.0, 1.0) if ey > fy else (0.0, -1.0)
    s = (1 - ratio) * abs(ey - fy) / 2
    return hood.edge_attached(ref[e[0]], ref[e[1]], out, s, contour_of(end_pts, e[0]))
