"""筆端：起筆斜切 12°、收筆微收 8%（spec: style.entry_cut_deg / exit_taper_pct）。

Phase 1 TODO
- 偵測筆畫端點（輪廓上兩個近似直角、相距約一個筆寬的轉角）
- 起筆：沿筆畫方向把端緣旋轉成 entry_cut_deg 的斜切
- 收筆：端緣兩點向筆畫中線收攏 exit_taper_pct
- 只移動既有端點，點數不變
"""


def transform(glyph_name, points, end_pts, flags, params, wght):
    return points  # identity until Phase 1
