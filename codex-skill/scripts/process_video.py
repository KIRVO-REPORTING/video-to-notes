#!/usr/bin/env python3
from __future__ import annotations

import sys


def main() -> int:
    try:
        from ytlt.cli import main as ytlt_main
    except ImportError:
        print("video-to-notes is not installed. From the repository root, run ./install.sh or install.ps1.", file=sys.stderr)
        return 2
    return ytlt_main(["process", *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
