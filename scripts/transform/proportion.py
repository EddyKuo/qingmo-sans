"""中宮與重心：中宮放鬆、重心上移、字身比例（spec: style.counter_open_pct / center_shift_up_pct / aspect_ratio）。

Design Spec v0：中宮「per-component 外移，保持部件筆畫粗細」；重心「上移 ≤ 0.5%」；字身「不做整字縮放」。

位移場（字面框內、對框中心歸一化座標 t）：
- 中宮：D(t) = h * k * t * (1 - |t|)。框邊 D = 0，越靠中心的部件越往外推，內部空間打開、外框不變
- 重心：y 方向再加 δ * (1 - t²)，框頂框底不動、中段上移 δ
保持筆畫粗細：參考 master 上配成對的豎畫左右緣（x）、橫畫上下緣（y）一律以「筆畫中線」的位移整體平移，
所以筆寬不變；未配對的點（斜筆、曲線、短筆）逐點取位移。與這些邊相切的 off-curve 點跟著邊移動。
字身比例：x 對中心縮放 aspect_ratio，1.00 為不動。只移動點，點數不變。
"""
from __future__ import annotations

from geometry import FLAT, neighbours, stem_pairs

# 母體 BASE 表 ideo 基線 -120，em box 高 1000（見 scripts/inspect_base.py 輸出）
IDEO_BOTTOM = -120
MAX_STEM = 0.16      # × UPM


def transform(glyph_name, points, end_pts, flags, params, wght, ctx):
    upm = ctx["upm"]
    ref = ctx["ref"]
    k = params["counter_open_pct"] / 100
    lift = params["center_shift_up_pct"] / 100 * upm
    aspect = params["aspect_ratio"]

    half_w, half_h = ctx["advance"] / 2, upm / 2
    cx, cy = half_w, IDEO_BOTTOM + half_h

    def dx(x):
        t = (x - cx) / half_w
        return half_w * k * t * (1 - abs(t)) if abs(t) < 1 else 0.0

    def dy(y):
        t = (y - cy) / half_h
        if abs(t) >= 1:
            return 0.0
        return half_h * k * t * (1 - abs(t)) + lift * (1 - t * t)

    # 每個點在兩個方向各自的位移；配對筆畫的邊用筆畫中線的位移
    move_x = {i: dx(p[0]) for i, p in enumerate(points)}
    move_y = {i: dy(p[1]) for i, p in enumerate(points)}
    for axis, coord, field, move in (("v", 0, dx, move_x), ("h", 1, dy, move_y)):
        locked: dict[int, list[float]] = {}
        for e, f in stem_pairs(ref, end_pts, flags, MAX_STEM * upm, axis):
            mid = (points[e[0]][coord] + points[f[0]][coord]) / 2
            for i in e:
                locked.setdefault(i, []).append(field(mid))
        for i, vals in locked.items():
            move[i] = sum(vals) / len(vals)
            for n in neighbours(end_pts, i):
                if not flags[n] & 1 and n not in locked and abs(ref[n][coord] - ref[i][coord]) <= FLAT:
                    move[n] = move[i]

    return [(cx + (x + move_x[i] - cx) * aspect, y + move_y[i]) for i, (x, y) in enumerate(points)]
