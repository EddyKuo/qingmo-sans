"""Shared helpers: project paths, spec loading, charset files."""
from __future__ import annotations

import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
FONTS = ROOT / "fonts"


def load_spec() -> dict:
    with open(ROOT / "config" / "spec.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def base_path(spec: dict) -> pathlib.Path:
    return BUILD / "base" / spec["base"]["filename"]


def read_charset(path: pathlib.Path) -> set[int]:
    """Read a charset file: every non-space character on non-comment lines."""
    cps: set[int] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            continue
        cps.update(ord(c) for c in line if not c.isspace())
    return cps


def master_filename(wght: int | float) -> str:
    return f"master-wght{int(wght)}.ttf"
