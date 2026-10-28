"""Subset the base font to a phase charset, keeping layout features, vertical metrics and all names."""
from __future__ import annotations

import argparse
import pathlib

from fontTools import subset
from fontTools.ttLib import TTFont

from common import BUILD, ROOT, base_path, load_spec, read_charset

# Always kept: ASCII, no-break space, CJK symbols & punctuation, Bopomofo, full-width forms, common quotes/dashes
ALWAYS = (
    set(range(0x20, 0x7F))
    | {0xA0}
    | set(range(0x3000, 0x3040))
    | set(range(0x3105, 0x3130))
    | set(range(0xFF01, 0xFF5F))
    | {0x2014, 0x2018, 0x2019, 0x201C, 0x201D, 0x2026}
)


def main() -> None:
    spec = load_spec()
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=pathlib.Path, default=base_path(spec))
    ap.add_argument("--charset", default="phase1", help="key under charsets: in spec.yaml")
    ap.add_argument("--charset-file", type=pathlib.Path, help="overrides --charset")
    ap.add_argument("--out", type=pathlib.Path)
    args = ap.parse_args()

    charset_file = args.charset_file or ROOT / spec["charsets"][args.charset]
    wanted = read_charset(charset_file) | ALWAYS
    out = args.out or BUILD / "subset" / f"base-{args.charset}.ttf"
    out.parent.mkdir(parents=True, exist_ok=True)

    opts = subset.Options()
    opts.layout_features = ["*"]
    opts.name_IDs = ["*"]
    opts.name_languages = ["*"]
    opts.notdef_outline = True
    opts.glyph_names = True

    font = TTFont(args.src)
    subsetter = subset.Subsetter(opts)
    subsetter.populate(unicodes=wanted)
    subsetter.subset(font)
    font.save(out)

    have = set(font.getBestCmap())
    missing = sorted(read_charset(charset_file) - have)
    print(f"{out}: {font['maxp'].numGlyphs} glyphs, {len(have)} codepoints")
    if missing:
        print(f"missing from base ({len(missing)}): " + "".join(chr(c) for c in missing[:80]))


if __name__ == "__main__":
    main()
