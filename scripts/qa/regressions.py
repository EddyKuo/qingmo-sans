"""QA gate: transforms must not introduce self-intersecting contours in any master.

Compares build/masters (base, untouched) with build/transformed, contour by contour. The VF keeps
overlaps, so a contour that crosses itself would render with a wrong-winding sliver at that weight;
static fonts hide it (removeOverlaps), which is why this check runs on the masters.
With --vf/--base-vf it also compares interpolated weights between masters.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import pathops  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402
from fontTools.varLib import instancer  # noqa: E402

from common import BUILD  # noqa: E402
from outlines import TOL, contours, to_path  # noqa: E402


def crossing(font: TTFont) -> set[tuple[str, int]]:
    gs = font.getGlyphSet()
    out = set()
    for name in font.getGlyphOrder():
        for k, ops in enumerate(contours(gs, name)):
            p = to_path(ops)
            s = pathops.simplify(p, clockwise=p.clockwise)
            if abs(abs(s.area) - abs(p.area)) > TOL or len(list(s.contours)) > 1:
                out.add((name, k))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=pathlib.Path, default=BUILD / "masters")
    ap.add_argument("--transformed", type=pathlib.Path, default=BUILD / "transformed")
    ap.add_argument("--vf", type=pathlib.Path, help="built VF: also check interpolated weights")
    ap.add_argument("--base-vf", type=pathlib.Path, default=BUILD / "subset" / "base-phase1.ttf")
    ap.add_argument("--weights", default="300,350,500,600,700,800")
    args = ap.parse_args()

    pairs = [(p.name, TTFont(p), TTFont(args.base / p.name))
             for p in sorted(args.transformed.glob("master-wght*.ttf"))]
    if args.vf:
        for w in (float(x) for x in args.weights.split(",")):
            pairs.append((f"{args.vf.name}@{w:g}",
                          instancer.instantiateVariableFont(TTFont(args.vf), {"wght": w}),
                          instancer.instantiateVariableFont(TTFont(args.base_vf), {"wght": w})))

    failed = False
    for label, font, base in pairs:
        cmap = {name: chr(cp) for cp, name in font.getBestCmap().items()}
        new = sorted(crossing(font) - crossing(base))
        if new:
            failed = True
            print(f"FAIL {label}: {len(new)} new self-intersecting contour(s)")
            for name, k in new[:30]:
                print(f"  {cmap.get(name, name)} {name} contour {k}")
        else:
            print(f"OK {label}: no new self-intersections")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
