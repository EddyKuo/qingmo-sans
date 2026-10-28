"""筆畫對比：橫畫相對豎畫變細（spec: style.contrast_h_over_v = 0.82）。

- 在參考 master（ctx["ref"]，預設 wght 400）上找出水平直線邊，依填色側分成「上緣」（填色在下）
  與「下緣」（填色在上），每條邊配對 x 重疊、距離最近、且中間為填色的相反類型邊 = 一個橫畫
- 橫畫寬 d 在當前 master 上量，兩緣各向內移動 (1 - ratio) * d / 2，點數不變
- 與移動邊共線相連的點（含切線 off-curve）跟著移動，曲線切線保持水平、短邊不被拆開
- 只處理「長橫」：重疊長度 >= 1.2 * d，且 d <= MAX_STEM；新寬度不小於 MIN_WIDTH
"""
from __future__ import annotations

from geometry import propagate, stem_pairs

MAX_STEM = 0.16      # × UPM，參考 master 上視為筆畫的最大寬度
MIN_WIDTH = 0.012    # × UPM，變細後的下限


def transform(glyph_name, points, end_pts, flags, params, wght, ctx):
    ratio = params["contrast_h_over_v"]
    if ratio >= 1:
        return points
    upm = ctx["upm"]
    ref = ctx["ref"]
    shifts: dict[int, list[float]] = {}
    for e, f in stem_pairs(ref, end_pts, flags, MAX_STEM * upm, "h"):
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
