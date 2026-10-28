"""Download the OFL base font (Source Han Sans TC VF) into build/base/ and verify its hash."""
from __future__ import annotations

import hashlib
import sys
import urllib.request

from common import base_path, load_spec


def main() -> None:
    spec = load_spec()
    base = spec["base"]
    out = base_path(spec)
    out.parent.mkdir(parents=True, exist_ok=True)

    if not out.exists():
        if not base.get("url"):
            sys.exit(
                "base.url is empty in config/spec.yaml.\n"
                "Pin the Source Han Sans TC variable TTF asset from\n"
                "https://github.com/adobe-fonts/source-han-sans/releases (Phase 1 task),\n"
                f"or place the file manually at {out}"
            )
        print(f"Downloading {base['url']}")
        urllib.request.urlretrieve(base["url"], out)

    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    expected = base.get("sha256")
    if expected and expected != digest:
        sys.exit(f"sha256 mismatch for {out}: expected {expected}, got {digest}")
    if not expected:
        print(f"sha256: {digest}  <- pin this as base.sha256 in config/spec.yaml")
    print(f"OK {out}")


if __name__ == "__main__":
    main()
