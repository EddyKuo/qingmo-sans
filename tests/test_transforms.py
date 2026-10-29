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
import strokes  # noqa: E402
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
    assert 0 < lift <= PARAMS["center_shift_up_pct"] / 100 * 1000 + 3 * abs(PARAMS["counter_open_pct"]), lift


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


def bar(start, end, width):
    """順時針的直筆矩形：start → end 的中線，兩端 cap 都是直線。"""
    (x0, y0), (x1, y1) = start, end
    d = math.dist(start, end)
    nx, ny = -(y1 - y0) / d * width / 2, (x1 - x0) / d * width / 2
    pts = [(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)]
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1]))
    assert area < 0, "must be clockwise (y up)"
    return pts


def _cap_widths(pts):
    """bar() 的兩個 cap 弦長：(起點端, 終點端)。"""
    return math.dist(pts[3], pts[0]), math.dist(pts[1], pts[2])


def test_ti_template():
    # 氵的提：左下 (90, 40) → 右上 (260, 340)，約 60°、長 345
    ti = bar((90, 40), (260, 340), 72)
    ops = strokes.plan(ti, [3], [1] * 4, 1000, 1000)
    assert [k for k, *_ in ops] == ["ti_tip", "ti_head"], ops
    out, ends, fl = strokes.transform_structure("uni6CB3", ti, [3], [1] * 4, PARAMS, 400, ctx(ti))
    assert len(out) == 5 and ends == [4] and fl.count(0) == 1, "one off-curve for the round head"
    on = [p for p, f in zip(out, fl) if f & 1]
    head, tip = _cap_widths(on)
    assert math.isclose(head, 72 * PARAMS["ti_head_pct"] / 100, abs_tol=0.01), head
    assert math.isclose(tip, 72 * PARAMS["ti_tip_pct"] / 100, abs_tol=0.01), tip
    # 同一條筆畫放到字的右半部（短撇的位置）就不算提
    assert not strokes.plan(bar((640, 380), (900, 640), 72), [3], [1] * 4, 1000, 1000)


def test_flat_ti_strength_ramps():
    # 金字旁的提很平（11–14°）：強度隨朝向線性漸增，差 2° 的兩個字不會一個有、一個沒有
    def head_width(deg):
        r = math.radians(deg)
        b = bar((60, 20), (60 + 340 * math.cos(r), 20 + 340 * math.sin(r)), 70)
        out, _, fl = strokes.transform_structure("uni9304", b, [3], [1] * 4, PARAMS, 400, ctx(b))
        return _cap_widths([p for p, f in zip(out, fl) if f & 1])[0]
    w11, w13, w60 = head_width(11), head_width(13), head_width(60)
    full = 70 * PARAMS["ti_head_pct"] / 100
    assert 70 < w11 < w13 < full and math.isclose(w60, full, abs_tol=0.01), (w11, w13, w60)
    assert w13 - w11 < 0.2 * (full - 70), "相近朝向的強度要相近"


def test_near_vertical_dots():
    # 灬、糸底下的點幾乎是直的（離垂直 0.4–12°）也要上尖下圓；正直的豎畫、弓的長斜豎不算點
    def kinds(deg_off_vertical, length):
        r = math.radians(90 - deg_off_vertical)
        top = (400 + length * math.cos(r), 100 + length * math.sin(r))
        return [k for k, *_ in strokes.plan(bar(top, (400, 100), 75), [3], [1] * 4, 1000, 1000)]
    assert kinds(5, 190) == ["dot_tip", "dot_round"]
    assert kinds(0.8, 185) == ["dot_tip", "dot_round"]
    assert kinds(0, 190) == []
    assert kinds(2, 293) == []


def test_changdian_template():
    # 凶的乂右筆：左上 (220, 730) → 右下 (760, 130)，約 -48°、長 807
    cd = bar((220, 730), (760, 130), 80)
    ops = strokes.plan(cd, [3], [1] * 4, 1000, 1000)
    assert [k for k, *_ in ops] == ["changdian_tip", "changdian_press"], ops
    p400, e400, f400 = strokes.transform_structure("uni51F6", cd, [3], [1] * 4, PARAMS, 400, ctx(cd))
    heavy = bar((215, 735), (765, 125), 150)
    p900, e900, f900 = strokes.transform_structure("uni51F6", heavy, [3], [1] * 4, PARAMS, 900, ctx(cd))
    assert e400 == e900 and f400 == f900, "structure must match across masters"
    on = [p for p, f in zip(p400, f400) if f & 1]
    top, bottom = _cap_widths(on)
    assert math.isclose(top, 80 * PARAMS["changdian_tip_pct"] / 100, abs_tol=0.01), top
    assert math.isclose(bottom, 80 * PARAMS["changdian_press_pct"] / 100, abs_tol=0.01), bottom
    # 比點短的是點，不是長點
    assert [k for k, *_ in strokes.plan(bar((400, 600), (600, 400), 80), [3], [1] * 4, 1000, 1000)] \
        == ["dot_tip", "dot_round"]


# 豎鉤（仿「小」的中豎）：右緣往下 → 外側轉彎 → 鉤底 → 鉤尖（朝左）→ 鉤內緣 → 內轉角 → 左緣往上
HOOK = [(540, 20), (540, -20), (520, -55), (490, -65), (460, -75), (370, -80), (300, -80),
        (298, -70), (288, -40), (276, -12), (270, 0), (310, 0), (375, 0), (425, 0), (435, 0),
        (450, 0), (460, 10), (460, 20), (460, 820), (540, 820)]
HOOK_FLAGS = [1, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 1, 1]
HOOK_ENDS = [len(HOOK) - 1]


def test_hook_template():
    ops = strokes.plan(HOOK, HOOK_ENDS, HOOK_FLAGS, 1000, 1000)
    assert [k for k, *_ in ops] == ["hook"], ops
    seg, inner, sweep, bend = ops[0][1]
    assert (seg[0], seg[-1], inner, sweep) == (6, 10, 10, 5), ops[0][1]
    assert bend == [0, 1, 2, 3], "外側轉彎是鉤底之前的那段"
    out, ends, fl = strokes.transform_structure("uni5C0F", HOOK, HOOK_ENDS, HOOK_FLAGS, PARAMS, 400, ctx(HOOK))
    assert len(out) == len(HOOK) and ends == HOOK_ENDS and fl == HOOK_FLAGS, "鉤只移動既有點"
    assert out[10] == HOOK[10], "內側端點不動"
    tip = math.dist(out[6], out[10])
    assert math.isclose(tip, math.dist(HOOK[6], HOOK[10]) * PARAMS["hook_tip_pct"] / 100, abs_tol=0.01), tip
    assert out[6][1] > HOOK[6][1] + 30, "鉤尖外側端點往上收（挑勢）"
    assert out[5][1] > HOOK[5][1], "外側邊跟著上挑"
    assert out[1][0] > HOOK[1][0] and out[2][1] < HOOK[2][1], "轉彎外緣往右下鼓（頓筆）"
    # 獨立的 4 段筆畫（撇、點）不是鉤
    assert all(k != "hook" for k, *_ in strokes.plan(bar((300, 300), (100, 280), 70), [3], [1] * 4, 1000, 1000))


def main() -> None:
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
