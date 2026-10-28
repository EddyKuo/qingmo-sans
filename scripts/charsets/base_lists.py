"""產生全字集清單：config/charsets/big5.txt 與 config/charsets/full.txt。

    python scripts/charsets/base_lists.py UNIHAN_DIR

- big5.txt：Unihan kBigFive 收錄的全部漢字（13,064 字，PRD v1.0「Big5 完整字集」）
- full.txt：母體（build/base/，先跑 fetch_base.py）cmap 中的全部 CJK 漢字（17,760 字，含 Big5、香港用字、擴充 A、補充平面）
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fontTools.ttLib import TTFont  # noqa: E402

from common import ROOT, base_path, load_spec  # noqa: E402

CJK = ((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF), (0x20000, 0x3134F))


def is_cjk(cp: int) -> bool:
    return any(lo <= cp <= hi for lo, hi in CJK)


def write(path: pathlib.Path, header: str, cps: list[int]) -> None:
    text = "".join(chr(c) for c in sorted(cps))
    path.write_text(header + "\n".join(text[i:i + 50] for i in range(0, len(text), 50)) + "\n",
                    encoding="utf-8")
    print(f"{path}: {len(cps)} 字")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("unihan", type=pathlib.Path)
    args = ap.parse_args()

    big5 = []
    for line in (args.unihan / "Unihan_OtherMappings.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        cp, key, _ = line.split("\t")
        if key == "kBigFive" and is_cjk(int(cp[2:], 16)):
            big5.append(int(cp[2:], 16))
    out = ROOT / "config" / "charsets"
    write(out / "big5.txt", "# Big5 全部漢字（Unicode Unihan kBigFive），PRD v1.0 目標字集\n", big5)

    base = TTFont(base_path(load_spec())).getBestCmap()
    write(out / "full.txt", "# 母體 Source Han Sans TW 的全部 CJK 漢字（含 Big5、香港用字、擴充 A、補充平面）\n",
          [cp for cp in base if is_cjk(cp)])


if __name__ == "__main__":
    main()
