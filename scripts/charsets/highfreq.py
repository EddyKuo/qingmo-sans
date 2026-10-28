"""產生 config/charsets/highfreq500.txt：繁體高頻字表（PRD QA 的 12/16/24 px 抽檢範圍）。

    python scripts/charsets/highfreq.py UNIHAN_DIR [--count 500]

UNIHAN_DIR 為解壓後的 Unicode Unihan.zip（https://www.unicode.org/Public/UCD/latest/ucd/Unihan.zip）。
Unihan 已移除 kFrequency，因此改用 kHanyuPinlu（《現代漢語頻率詞典》字頻，記在簡化字上）：
每個簡化字的頻率平均分給它在 Big5 常用字區（A440–C67E）的所有繁體寫法（kTraditionalVariant，含自己）。
只靠簡體語料無法判斷哪個繁體寫法是主流（了/瞭 以「了」為主，么/麼 以「麼」為主），平均分配會讓少數罕用寫法
（齣、韆）進榜，但不會漏掉高頻字 —— 對抽檢範圍而言寧可多收。語料為簡體，結果是近似值。
"""
from __future__ import annotations

import argparse
import pathlib
import re
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[2]


def load(path: pathlib.Path, key: str) -> dict[int, str]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        cp, k, v = line.split("\t")
        if k == key:
            out[int(cp[2:], 16)] = v
    return out


def codepoints(value: str) -> list[int]:
    return [int(h, 16) for h in re.findall(r"U\+([0-9A-F]+)", value)]


def ranking(unihan: pathlib.Path) -> list[int]:
    pinlu = load(unihan / "Unihan_Readings.txt", "kHanyuPinlu")
    big5 = load(unihan / "Unihan_OtherMappings.txt", "kBigFive")
    trad = load(unihan / "Unihan_Variants.txt", "kTraditionalVariant")

    def common(cp):
        return cp in big5 and int(big5[cp][:4], 16) < 0xC940

    freq: Counter[int] = Counter()
    for s, value in pinlu.items():
        count = sum(int(n) for n in re.findall(r"\((\d+)\)", value))
        cands = [t for t in codepoints(trad.get(s, "")) if common(t)] or ([s] if s in big5 else [])
        for t in cands:
            freq[t] += count / len(cands)
    return [cp for cp, _ in freq.most_common() if 0x4E00 <= cp <= 0x9FFF]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("unihan", type=pathlib.Path)
    ap.add_argument("--count", type=int, default=500)
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "config" / "charsets" / "highfreq500.txt")
    args = ap.parse_args()

    top = "".join(chr(cp) for cp in ranking(args.unihan)[:args.count])
    args.out.write_text(
        f"# 繁體高頻 {args.count} 字（PRD QA：12/16/24 px 抽檢範圍），依頻率排序\n"
        "# 由 scripts/charsets/highfreq.py 從 Unicode Unihan kHanyuPinlu 產生，規則見該腳本說明；屬近似值\n"
        + "\n".join(top[i:i + 50] for i in range(0, len(top), 50)) + "\n", encoding="utf-8")
    print(f"{args.out}: {len(top)} 字")


if __name__ == "__main__":
    main()
