"""End-to-end smoke test of the whole pipeline on any TrueType font (no CJK base needed).

    python tests/smoke_test.py FONT.ttf [--masters 400,700]

A variable font exercises the real instancer path; pass --masters inside its wght range.
A static font is copied to every master (structure-only test).
"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]


def run(*args) -> None:
    print("$", " ".join(str(a) for a in args))
    subprocess.run([sys.executable, *map(str, args)], check=True, cwd=ROOT)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("font", type=pathlib.Path)
    ap.add_argument("--masters", default="400,700")
    args = ap.parse_args()
    src = args.font.resolve()

    with tempfile.TemporaryDirectory() as tmp:
        t = pathlib.Path(tmp)
        charset = t / "ascii.txt"
        charset.write_text("".join(chr(c) for c in range(0x21, 0x7F)), encoding="utf-8")
        m = ["--masters", args.masters]

        run("scripts/subset.py", "--src", src, "--charset-file", charset, "--out", t / "subset.ttf")
        run("scripts/extract_masters.py", "--src", t / "subset.ttf", "--outdir", t / "masters", *m)
        run("scripts/check_compat.py", t / "masters")
        run("scripts/transform/pipeline.py", "--indir", t / "masters", "--outdir", t / "transformed")
        run("scripts/check_compat.py", t / "transformed")
        run("scripts/build_vf.py", "--indir", t / "transformed", "--out", t / "vf.ttf", *m)
        run("scripts/inspect_base.py", "--src", t / "vf.ttf")
        run("scripts/qa/check_names.py", t / "vf.ttf")
        run("scripts/qa/coverage.py", t / "vf.ttf", "--charset-file", charset)
    print("SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
