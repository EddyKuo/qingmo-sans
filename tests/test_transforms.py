"""Unit tests for the geometric transforms on synthetic outlines (no font files needed).

    python tests/test_transforms.py

The test glyph is 十 as the base draws it: two overlapping clockwise rectangles.
"""
from __future__ import annotations

import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "transform"))
sys.path.insert(0, str(ROOT / "scripts"))

import contrast  # noqa: E402
import corners  # noqa: E402
import proportion  # noqa: E402
import terminals  # noqa: E402
from common import load_spec  # noqa: E402

# 十 at wght 400: horizontal 55..952 x 389..466, vertical 461..542 x -80..839
SHI = [(952, 466), (952, 389), (55, 389), (55, 466), (542, 839), (542, -80), (461, -80), (461, 839)]
END_PTS = [3, 7]
FLAGS = [1] * 8
PARAMS = load_spec()["style"]


def ctx(ref=SHI, stem_scale=1.0):
    return {"ref": ref, "upm": 1000, "advance": 1000, "stem_scale": stem_scale}


def test_contrast_thins_horizontal_only():
    out = contrast.transform("uni5341", SHI, END_PTS, FLAGS, PARAMS, 400, ctx())
    h = out[0][1] - out[1][1]
    assert math.isclose(h, 77 * PARAMS["contrast_h_over_v"], abs_tol=0.01), h
    assert out[4][0] - out[7][0] == 81, "vertical stroke width must not change"
    assert math.isclose((out[0][1] + out[1][1]) / 2, (466 + 389) / 2), "thinning is symmetric"


def test_terminals():
    out = terminals.transform("uni5341", SHI, END_PTS, FLAGS, PARAMS, 400, ctx())
    tan = math.tan(math.radians(PARAMS["entry_cut_deg"]))
    taper = PARAMS["exit_taper_pct"] / 100
    # 橫畫左端起筆：下角 (55,389) 右移 77*tan
    assert math.isclose(out[2][0], 55 + 77 * tan), out[2]
    assert out[3] == (55, 466)
    # 橫畫右端收筆：上下各收 taper/2
    assert math.isclose(out[0][1], 466 - 77 * taper / 2) and math.isclose(out[1][1], 389 + 77 * taper / 2)
    # 豎畫上端起筆：右角 (542,839) 下移 81*tan
    assert math.isclose(out[4][1], 839 - 81 * tan), out[4]
    # 豎畫下端收筆：左右各收
    assert math.isclose(out[5][0], 542 - 81 * taper / 2) and math.isclose(out[6][0], 461 + 81 * taper / 2)


def test_hidden_terminal_is_skipped():
    # 一條橫畫兩端都藏在豎畫裡（像口的下橫）：不是筆端
    pts = [(560, 120), (560, 60), (100, 60), (100, 120),          # 橫
           (130, 800), (130, 0), (60, 0), (60, 800),               # 左豎
           (600, 800), (600, 0), (530, 0), (530, 800)]             # 右豎
    ends = terminals.stroke_ends(pts, [3, 7, 11], [1] * 12, 1000)
    assert not [e for e in ends if e[1] in (0, 1, 2, 3)], ends


def test_proportion_keeps_stroke_width():
    out = proportion.transform("uni5341", SHI, END_PTS, FLAGS, PARAMS, 400, ctx())
    assert math.isclose(out[0][1] - out[1][1], 77, abs_tol=1e-6), "horizontal width kept"
    assert math.isclose(out[4][0] - out[7][0], 81, abs_tol=1e-6), "vertical width kept"
    lift = (out[0][1] + out[1][1]) / 2 - (466 + 389) / 2
    assert 0 < lift <= PARAMS["center_shift_up_pct"] / 100 * 1000 + 3 * PARAMS["counter_open_pct"], lift


def test_corners_add_points_identically_across_masters():
    p400, e400, f400 = corners.transform_structure("uni5341", SHI, END_PTS, FLAGS, PARAMS, 400, ctx())
    heavy = [(x + (3 if x > 500 else -3), y) for x, y in SHI]
    p900, e900, f900 = corners.transform_structure("uni5341", heavy, END_PTS, FLAGS, PARAMS, 900,
                                                   ctx(stem_scale=1.9))
    assert e400 == e900 and f400 == f900, "structure must match across masters"
    # 橫畫 4 角全露在外；豎畫 4 角也露在外 → 8 角各 +2 點
    assert len(p400) == len(SHI) + 2 * 8, len(p400)
    assert sum(1 for f in f400 if not f & 1) == 8


def test_corners_skip_hidden():
    # 一個角落藏在另一個輪廓裡的方塊：只處理露在外面的角
    pts = [(0, 0), (0, 100), (100, 100), (100, 0)]                # 順時針（y 向上）
    cover = [(80, 80), (80, 200), (200, 200), (200, 80)]
    allpts = pts + cover
    hidden = corners.soft_corners(allpts, [3, 7], [1] * 8, 6)
    assert 2 not in hidden, "corner (100,100) sits inside the other contour"
    assert {0, 1, 3} <= set(hidden)


def main() -> None:
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
