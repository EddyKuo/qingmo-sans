"""產生人工抽檢用的校樣圖（PRD：12 / 16 / 24 px 全字表渲染，人工抽檢高頻 500 字）。

    python scripts/qa/proof_sheet.py FONT [--charset highfreq500] [--sizes 12,16,24] [--outdir build/proof]

每個字級輸出一張 PNG，依字表順序（高頻在前）排列，以實際像素渲染（無 hinting、灰階），
再以最近鄰放大到約 36 px 一格方便檢視。校樣圖依 PRD「不存檔、不入版控」只放在 build/。
需要 freetype-py 與 Pillow。
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import freetype  # noqa: E402
from PIL import Image  # noqa: E402

from common import BUILD, ROOT, load_spec  # noqa: E402

COLS = 25


def ordered_charset(path: pathlib.Path) -> list[str]:
    out, seen = [], set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            continue
        for c in line:
            if not c.isspace() and c not in seen:
                seen.add(c)
                out.append(c)
    return out


def sheet(font: pathlib.Path, chars: list[str], px: int, out: pathlib.Path) -> list[str]:
    face = freetype.Face(str(font))
    face.set_pixel_sizes(px, px)
    cell = px + px // 3
    rows = (len(chars) + COLS - 1) // COLS
    img = Image.new("L", (COLS * cell + 8, rows * cell + 8), 255)
    missing = []
    for k, ch in enumerate(chars):
        if not face.get_char_index(ord(ch)):
            missing.append(ch)
            continue
        face.load_char(ch, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
        bm = face.glyph.bitmap
        if not bm.width:
            continue
        glyph = Image.frombytes("L", (bm.width, bm.rows), bytes(bm.buffer))
        x = 4 + (k % COLS) * cell + face.glyph.bitmap_left
        y = 4 + (k // COLS) * cell + int(px * 0.88) - face.glyph.bitmap_top
        img.paste(0, (x, y), glyph)
    scale = max(1, 36 // px)
    img.resize((img.width * scale, img.height * scale), Image.NEAREST).save(out)
    return missing


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("font", type=pathlib.Path)
    ap.add_argument("--charset", default="highfreq500")
    ap.add_argument("--sizes", default="12,16,24")
    ap.add_argument("--outdir", type=pathlib.Path, default=BUILD / "proof")
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    chars = ordered_charset(ROOT / load_spec()["charsets"][args.charset])
    for px in (int(s) for s in args.sizes.split(",")):
        out = args.outdir / f"{args.font.stem}-{args.charset}-{px}px.png"
        missing = sheet(args.font, chars, px, out)
        note = f"，缺字 {''.join(missing)}" if missing else ""
        print(f"{out}: {len(chars)} 字{note}")


if __name__ == "__main__":
    main()
