"""Signature line stored with the archive."""

from __future__ import annotations

import subprocess


def line() -> str:
    out = subprocess.check_output(["redis-cli", "GET", "archive:billing.conf"])
    if out.endswith(b"\n"):
        out = out[:-1]
    raw = out.decode()
    if "=" in raw:
        raw = raw.split("=", 1)[1]
    return raw.strip().strip("'").strip('"')
