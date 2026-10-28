"""墨暈軟角：折角外角軟化（spec: style.corner_radius_units = 6，隨字重縮放）。

Phase 1 TODO
- 母體折角若只有一個 on-curve 點，軟化必須新增點，會破壞點相容
- 做法：所有 master 一律在同一批轉角插入相同數量的點（先決定轉角集合，再對每個 master 套用），
  或改在 masters 抽出前對母體 VF 統一處理
- 半徑隨 wght 線性縮放：r(w) = r400 * (stem(w) / stem(400))
"""


def transform(glyph_name, points, end_pts, flags, params, wght):
    return points  # identity until Phase 1
