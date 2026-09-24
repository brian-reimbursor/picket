"""Archive line checked before a receipt can be listed."""

from __future__ import annotations

import subprocess


def _line() -> str:
    out = subprocess.check_output(["redis-cli", "GET", "archive:billing.conf"])
    if out.endswith(b"\n"):
        out = out[:-1]
    raw = out.decode()
    if "=" in raw:
        raw = raw.split("=", 1)[1]
    return raw.strip().strip("'").strip('"')


def holds(headers, query) -> bool:
    presented = (query.get("signature") or [""])[0] if query else ""
    if not presented:
        presented = headers.get("Signature") or ""
    presented = presented.strip().strip("'").strip('"')
    expected = _line()
    return bool(presented) and presented == expected
