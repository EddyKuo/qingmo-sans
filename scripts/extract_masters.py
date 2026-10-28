"""Instantiate static masters from the (subset) base VF at the wght positions listed in spec.yaml.

Masters cut from one VF share point structure by construction; every later transform
must preserve it (see scripts/check_compat.py).
"""
from __future__ import annotations

import argparse
import pathlib
import sys

from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

from common import BUILD, load_spec, master_filename


def main() -> None:
    spec = load_spec()
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=pathlib.Path, default=BUILD / "subset" / "base-phase1.ttf")
    ap.add_argument("--outdir", type=pathlib.Path, default=BUILD / "masters")
    ap.add_argument("--masters", type=lambda s: [int(x) for x in s.split(",")],
                    default=spec["masters"], help="comma-separated wght values; default from spec")
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    probe = TTFont(args.src)
    if "glyf" not in probe:
        print("WARNING: base has CFF/CFF2 outlines; transforms expect TrueType (glyf). "
              "Use the TTF variable release or convert first.")
    axes = {a.axisTag: a for a in probe["fvar"].axes} if "fvar" in probe else {}
    if not axes:
        print("WARNING: source is static; every master is a copy (smoke-test mode only)")

    tag = spec["axis"]["tag"]
    for wght in args.masters:
        font = TTFont(args.src)
        if axes:
            axis = axes[tag]
            if not axis.minValue <= wght <= axis.maxValue:
                sys.exit(f"master {tag}={wght} outside base range "
                         f"{axis.minValue}..{axis.maxValue}; update masters in config/spec.yaml")
            limits = {t: (wght if t == tag else a.defaultValue) for t, a in axes.items()}
            font = instancer.instantiateVariableFont(font, limits)
        out = args.outdir / master_filename(wght)
        font.save(out)
        print(out)


if __name__ == "__main__":
    main()
