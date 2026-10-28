"""QA gate: every character of a phase charset must be in the font's cmap."""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fontTools.ttLib import TTFont  # noqa: E402

from common import ROOT, load_spec, read_charset  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("font", type=pathlib.Path)
    ap.add_argument("--charset", default="phase1")
    ap.add_argument("--charset-file", type=pathlib.Path)
    args = ap.parse_args()

    charset_file = args.charset_file or ROOT / load_spec()["charsets"][args.charset]
    wanted = read_charset(charset_file)
    missing = sorted(wanted - set(TTFont(args.font).getBestCmap()))
    if missing:
        print(f"FAIL: {len(missing)}/{len(wanted)} missing: " + "".join(chr(c) for c in missing[:80]))
        sys.exit(1)
    print(f"OK: {len(wanted)} characters covered")


if __name__ == "__main__":
    main()
