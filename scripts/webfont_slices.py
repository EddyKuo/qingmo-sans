"""把字型依 unicode-range 切成多個 WOFF2 小檔，並產生 @font-face CSS，讓網頁只下載用到的字。

    python scripts/webfont_slices.py --outdir fonts/webfont-slices FONT...

切片順序（越前面越常用，一般頁面通常只需要前幾片）：
    0     非漢字（拉丁、標點、注音、全形符號…）+ 高頻 500 字
    1..   Big5 第一字面「常用字」5,401 字（依 Big5 編碼順序）
    ..    Big5 第二字面「次常用字」
    ..    其餘漢字（香港用字、擴充 A、補充平面…）
每片最多 --chunk 個漢字。輸出：
    OUTDIR/<字型檔名>/<字型檔名>.<n>.woff2
    OUTDIR/qingmo-sans-tc.css         可變字型（font-weight 範圍）
    OUTDIR/qingmo-sans-tc-static.css  6 個 static 字重
    OUTDIR/demo.html                  示範頁（用第一份 CSS）
"""
from __future__ import annotations

import argparse
import pathlib
import sys
from concurrent.futures import ProcessPoolExecutor

from fontTools import subset
from fontTools.ttLib import TTFont

from common import ROOT, load_spec, read_charset
from charsets.base_lists import is_cjk

FAMILY = load_spec()["family"]["en"]

DEMO = """<!doctype html>
<html lang="zh-Hant-TW">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>晴墨黑體 網頁字型示範</title>
<link rel="stylesheet" href="{css}">
<style>
  body {{ font-family: "{family}", sans-serif; max-width: 40em; margin: 2em auto; padding: 0 16px; line-height: 1.6; }}
  p {{ margin: .4em 0; }}
</style>
<h1>晴墨黑體 Qingmo Sans TC</h1>
<p style="font-weight:250">極細 250　黑體的骨架，加上明體的筆勢。</p>
<p style="font-weight:300">細 300　黑體的骨架，加上明體的筆勢。</p>
<p style="font-weight:400">標準 400　黑體的骨架，加上明體的筆勢。</p>
<p style="font-weight:500">中 500　黑體的骨架，加上明體的筆勢。</p>
<p style="font-weight:700">粗 700　黑體的骨架，加上明體的筆勢。</p>
<p style="font-weight:900">特粗 900　黑體的骨架，加上明體的筆勢。</p>
<p>鬱龜鑿灣臺 ABCabc 0123456789「」，。？！</p>
</html>
"""


def big5_levels() -> tuple[list[int], list[int]]:
    """Big5 編碼順序的常用字（0xA440–0xC67E）與次常用字（0xC940–0xF9D5）。"""
    def decode(lo: int, hi: int) -> list[int]:
        out = []
        for code in range(lo, hi + 1):
            if (code & 0xFF) < 0x40 or 0x7F <= (code & 0xFF) <= 0xA0 or (code & 0xFF) == 0xFF:
                continue
            try:
                out.append(ord(code.to_bytes(2, "big").decode("big5")))
            except UnicodeDecodeError:
                pass
        return out
    return decode(0xA440, 0xC67E), decode(0xC940, 0xF9D5)


def plan(cmap: set[int], chunk: int) -> list[list[int]]:
    hf = sorted(read_charset(ROOT / load_spec()["charsets"]["highfreq500"]))
    common, less = big5_levels()
    first = [cp for cp in sorted(cmap) if not is_cjk(cp)] + hf
    seen = set(first)
    han = []
    for cp in common + less + sorted(cmap):
        if cp in cmap and cp not in seen:
            seen.add(cp)
            han.append(cp)
    return [[cp for cp in first if cp in cmap]] + [han[i:i + chunk] for i in range(0, len(han), chunk)]


def unicode_range(cps: list[int]) -> str:
    cps = sorted(cps)
    spans, lo = [], cps[0]
    for prev, cp in zip(cps, cps[1:] + [None]):
        if cp != prev + 1:
            spans.append(f"U+{lo:X}" if lo == prev else f"U+{lo:X}-{prev:X}")
            lo = cp
    return ", ".join(spans)


def cut(font: pathlib.Path, cps: list[int], out: pathlib.Path) -> None:
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["*"]
    opts.name_IDs = ["*"]
    opts.name_languages = ["*"]
    opts.notdef_outline = True
    opts.glyph_names = False
    f = subset.load_font(str(font), opts)
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=cps)
    sub.subset(f)
    subset.save_font(f, str(out), opts)


def weight(font: TTFont) -> str:
    if "fvar" in font:
        axis = next(a for a in font["fvar"].axes if a.axisTag == "wght")
        return f"{axis.minValue:g} {axis.maxValue:g}"
    return str(font["OS/2"].usWeightClass)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("fonts", nargs="+", type=pathlib.Path)
    ap.add_argument("--outdir", type=pathlib.Path, required=True)
    ap.add_argument("--chunk", type=int, default=400)
    args = ap.parse_args()

    css = {"qingmo-sans-tc.css": [], "qingmo-sans-tc-static.css": []}
    jobs = []
    with ProcessPoolExecutor() as pool:
        for font in args.fonts:
            tt = TTFont(font, lazy=True)
            slices = plan(set(tt.getBestCmap()), args.chunk)
            sheet = "qingmo-sans-tc.css" if "fvar" in tt else "qingmo-sans-tc-static.css"
            stem = font.stem.replace("[", "-").replace("]", "")   # URL 不放方括號
            outdir = args.outdir / stem
            outdir.mkdir(parents=True, exist_ok=True)
            for n, cps in enumerate(slices):
                out = outdir / f"{stem}.{n}.woff2"
                jobs.append(pool.submit(cut, font, cps, out))
                css[sheet].append(
                    "@font-face {\n"
                    f'  font-family: "{FAMILY}";\n'
                    f'  src: url("{stem}/{out.name}") format("woff2");\n'
                    f"  font-weight: {weight(tt)};\n"
                    "  font-style: normal;\n"
                    "  font-display: swap;\n"
                    f"  unicode-range: {unicode_range(cps)};\n"
                    "}\n")
            print(f"{font.name}: {len(slices)} 片")
        for job in jobs:
            job.result()

    for name, rules in css.items():
        if rules:
            (args.outdir / name).write_text("".join(rules), encoding="utf-8")
            print(f"OK {args.outdir / name}")
    sheets = [name for name, rules in css.items() if rules]
    (args.outdir / "demo.html").write_text(DEMO.format(css=sheets[0], family=FAMILY), encoding="utf-8")
    print(f"OK {args.outdir / 'demo.html'}")


if __name__ == "__main__":
    sys.exit(main())
