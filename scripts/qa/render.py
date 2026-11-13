"""大尺寸渲染檢查：以 FreeType 直接設定可變字型座標，渲染全部漢字，列出晴墨失敗而母體不失敗的字。

    python scripts/qa/render.py "fonts/variable/QingmoSansTC[wght].ttf" [--base build/base/SourceHanSansTC-VF.ttf]
        [--wght 250,400,700,900] [--px 500]

可變字型的字形帶 OVERLAP_SIMPLE 旗標，FreeType 以 4 倍超取樣渲染；幾乎水平（斜 1–2 units）的長邊、
又長又平的二次曲線，會在同一列像素產生上千格而超出光柵化器的記憶體池（raster overflow），字直接畫不出來。
點相容、自交、fontbakery 都抓不到這類問題（0.104 研究紀錄 §18）。在 master 之間的插值字重（如 700）也要查。
"""
from __future__ import annotations

import argparse
import pathlib
import sys

import freetype
from fontTools.ttLib import TTFont

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from common import base_path, load_spec  # noqa: E402

CJK = ((0x3400, 0x9FFF), (0xF900, 0xFAFF), (0x20000, 0x3134F))


def failures(path: pathlib.Path, cps: list[int], wght: float, px: int) -> set[int]:
    face = freetype.Face(str(path))
    face.set_var_design_coords((wght,))
    face.set_pixel_sizes(px, px)
    bad = set()
    for cp in cps:
        try:
            face.load_char(chr(cp), freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
        except freetype.FT_Exception:
            bad.add(cp)
    return bad


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("font", type=pathlib.Path)
    ap.add_argument("--base", type=pathlib.Path, default=base_path(load_spec()))
    ap.add_argument("--wght", default="250,400,700,900")
    ap.add_argument("--px", type=int, default=500)
    args = ap.parse_args()
    cps = sorted(cp for cp in TTFont(args.font).getBestCmap() if any(lo <= cp <= hi for lo, hi in CJK))
    for w in (float(x) for x in args.wght.split(",")):
        new = failures(args.font, cps, w, args.px) - failures(args.base, cps, w, args.px)
        chars = "".join(chr(cp) for cp in sorted(new))
        print(f"wght {w:g} {args.px}px：{len(cps)} 字，晴墨新增失敗 {len(new)}  {chars[:60]}", flush=True)


if __name__ == "__main__":
    main()
