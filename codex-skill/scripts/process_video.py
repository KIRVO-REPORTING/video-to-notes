#!/usr/bin/env python3
from __future__ import annotations

import sys


def main() -> int:
    try:
        from ytlt.cli import main as ytlt_main
    except ImportError:
        print("ytlt is not installed. From the public repository root, run: python -m pip install -e .", file=sys.stderr)
        return 2
    return ytlt_main(["process", *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
