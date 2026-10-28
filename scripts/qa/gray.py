"""QA gate「灰度一致」（Design Spec v0）：漢字字面墨色覆蓋率的標準差不得高於母體太多。

每個漢字在 SIZE px 下以 FreeType 渲染，覆蓋率 = 墨色像素和 / 字面框面積。
Phase 1 尚無結構分類資料，全部漢字視為同一類；門檻為相對母體：
    std(晴墨) <= std(母體) * qa.gray_std_ratio_max（spec.yaml）
即改造不得讓灰度比母體更不一致。結構分類（左右、上下、包圍…）於 Phase 2 字集擴充時加入。

需要 freetype-py（requirements.txt 的 QA 選用套件）。
"""
from __future__ import annotations

import argparse
import pathlib
import statistics
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import freetype  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402
from fontTools.varLib import instancer  # noqa: E402

from common import load_spec  # noqa: E402

SIZE = 64


def coverages(path: pathlib.Path, codepoints: list[int]) -> list[float]:
    face = freetype.Face(str(path))
    face.set_pixel_sizes(SIZE, SIZE)
    out = []
    for cp in codepoints:
        if not face.get_char_index(cp):
            continue
        face.load_char(chr(cp), freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
        ink = sum(face.glyph.bitmap.buffer) / 255
        out.append(ink / (SIZE * SIZE))
    return out


def static_at(path: pathlib.Path, wght: float | None, tmp: pathlib.Path) -> pathlib.Path:
    """可變字型先在 wght 切出 static；static 字型原樣使用。"""
    font = TTFont(path)
    if "fvar" not in font:
        return path
    if wght is None:
        sys.exit(f"{path.name} is variable: pass --wght")
    out = tmp / f"{path.stem}-{int(wght)}.ttf"
    instancer.instantiateVariableFont(font, {"wght": wght}).save(out)
    return out


def han(path: pathlib.Path) -> list[int]:
    face = freetype.Face(str(path))
    return sorted(cp for cp, _ in face.get_chars() if 0x4E00 <= cp <= 0x9FFF)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("font", type=pathlib.Path)
    ap.add_argument("--base", type=pathlib.Path, required=True, help="base font (static, or VF with --wght)")
    ap.add_argument("--wght", type=float, help="weight to cut from variable inputs")
    args = ap.parse_args()
    limit = load_spec()["qa"]["gray_std_ratio_max"]

    with tempfile.TemporaryDirectory() as tmp:
        font = static_at(args.font, args.wght, pathlib.Path(tmp))
        base_font = static_at(args.base, args.wght, pathlib.Path(tmp))
        cps = han(font)
        ours, base = coverages(font, cps), coverages(base_font, cps)
    s_ours, s_base = statistics.pstdev(ours), statistics.pstdev(base)
    ratio = s_ours / s_base
    print(f"{args.font.name}: {len(ours)} han, coverage mean {statistics.mean(ours):.4f} "
          f"std {s_ours:.4f} (base {s_base:.4f}, ratio {ratio:.3f}, limit {limit})")
    if ratio > limit:
        print("FAIL: gray consistency worse than base")
        sys.exit(1)
    print("OK")


if __name__ == "__main__":
    main()
