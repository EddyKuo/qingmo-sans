"""產生 GitHub Release 說明：FONTLOG.txt 中指定版本的段落 + 檔案說明。

    python scripts/release_notes.py 0.101 > notes.md
"""
from __future__ import annotations

import sys

from common import ROOT, load_spec

FILES = """\
## 檔案

| 檔案 | 內容 |
| --- | --- |
| `QingmoSansTC-{v}.zip` | `variable/`（可變字型 wght 250–900）、`static/`（6 個字重 TTF）、`webfonts/`（整檔 WOFF2）、fontconfig 設定、OFL、FONTLOG |
| `QingmoSansTC-{v}-webfont-slices.zip` | 依 unicode-range 切片的 WOFF2 與 `@font-face` CSS，網頁只下載用到的字 |
| `SHA256SUMS.txt` | 上述檔案的 sha256 |

安裝與使用方式見 [README]({repo}#使用)。字型以 SIL Open Font License 1.1 授權，衍生自 Source Han Sans TC。
"""


def section(version: str) -> str:
    log = (ROOT / "FONTLOG.txt").read_text(encoding="utf-8")
    for block in log.split("\n\n"):
        head, _, body = block.partition("\n")
        if head.rstrip().endswith(f"Version {version}"):
            return f"## 變更（{head.split(' ')[0]}）\n\n{body}\n"
    sys.exit(f"FONTLOG.txt 沒有 Version {version} 的段落")


def main() -> None:
    version = sys.argv[1]
    repo = load_spec()["family"]["repo"]
    print(section(version))
    print(FILES.format(v=version, repo=repo))


if __name__ == "__main__":
    main()
