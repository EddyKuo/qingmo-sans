"""QA gate: font-name records must not contain the base font's Reserved Font Name (OFL)."""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fontTools.ttLib import TTFont  # noqa: E402

from common import load_spec  # noqa: E402

# Name IDs that are font names (copyright 0 and license 13 legitimately mention the RFN)
FONT_NAME_IDS = {1, 2, 3, 4, 6, 16, 17, 18, 21, 22, 25}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("fonts", nargs="+", type=pathlib.Path)
    args = ap.parse_args()
    terms = [t.lower() for t in load_spec()["qa"]["forbidden_name_terms"]]

    failed = False
    for path in args.fonts:
        for rec in TTFont(path)["name"].names:
            if rec.nameID in FONT_NAME_IDS or rec.nameID >= 256:
                try:
                    text = rec.toUnicode()
                except UnicodeDecodeError:
                    text = str(rec)
                if any(t in text.lower() for t in terms):
                    print(f"FAIL {path.name}: nameID {rec.nameID} = {text!r}")
                    failed = True
    if failed:
        sys.exit(1)
    print(f"OK: no reserved names in {len(args.fonts)} font(s)")


if __name__ == "__main__":
    main()
