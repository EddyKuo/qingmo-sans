"""筆畫對比：橫畫相對豎畫變細（spec: style.contrast_h_over_v = 0.82）。

Phase 1 TODO
- 將每個輪廓的線段分類為橫畫上下緣 / 豎畫左右緣（依線段方向與成對平行邊）
- 對橫畫成對邊各向內移動 (1 - ratio) * 筆畫寬 / 2，不新增或刪除點
- 交叉、轉折處以最小筆寬保護，避免自交
"""


def transform(glyph_name, points, end_pts, flags, params, wght):
    return points  # identity until Phase 1
