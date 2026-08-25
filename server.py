#!/usr/bin/env python3
"""Production entry. Bind 127.0.0.1; nginx terminates TLS."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from picket.http import serve  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(prog="picket")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7771)
    args = parser.parse_args()
    serve(args.host, args.port)


if __name__ == "__main__":
    main()
