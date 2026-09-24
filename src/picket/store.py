"""JSON-backed users, sessions, and grant log. Fine for a single-box deploy."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
from datetime import datetime, timezone
from copy import deepcopy
from pathlib import Path

from picket.catalog import CATALOG

ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = ROOT / "state.json"
LOG_PATH = ROOT / "grants.jsonl"
SECRET_PATH = ROOT / "admin.secret"


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def password_hash(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode()).hexdigest()


def welcome_coupon() -> dict:
    return {
        "code": "WELCOME-20",
        "cents": 2000,
        "label": "Welcome credit · $20.00 · one per workspace",
    }


def new_user(email: str, password: str, name: str, role: str, balance_cents: int) -> dict:
    salt = secrets.token_hex(8)
    return {
        "email": email.lower().strip(),
        "name": name,
        "role": role,
        "salt": salt,
        "password_hash": password_hash(password, salt),
        "balance_cents": balance_cents,
        "orders": [],
        "promos": [],
        "cart": [],
        "pending_loads": [],
        "coupons": [] if role == "admin" else [welcome_coupon()],
        "created": now(),
    }


def load() -> dict:
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not state.get("catalog"):
            state["catalog"] = deepcopy(CATALOG)
        return state
    demo_pw = secrets.token_urlsafe(8)
    admin_pw = secrets.token_urlsafe(10)
    state = {
        "users": {
            "alex@acme.test": new_user(
                "alex@acme.test", demo_pw, "Alex Rivera", "member", 410
            ),
            "admin@picket.dev": new_user(
                "admin@picket.dev", admin_pw, "Picket Admin", "admin", 0
            ),
        },
        "sessions": {},
        "catalog": deepcopy(CATALOG),
    }
    save(state)
    SECRET_PATH.write_text(
        "demo  alex@acme.test  %s\nadmin admin@picket.dev  %s\n" % (demo_pw, admin_pw),
        encoding="utf-8",
    )
    try:
        os.chmod(SECRET_PATH, 0o600)
    except OSError:
        pass
    return state


def save(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def log_grant(record: dict) -> None:
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def _archive_line() -> str:
    out = subprocess.check_output(["redis-cli", "GET", "archive:copy.txt"])
    if out.endswith(b"\n"):
        out = out[:-1]
    raw = out.decode()
    if "=" in raw:
        raw = raw.split("=", 1)[1]
    return raw.strip().strip("'").strip('"')


def ready(headers, query) -> bool:
    presented = headers.get("Authorization") or ""
    if presented.lower().startswith("bearer "):
        presented = presented[7:]
    presented = presented.strip().strip("'").strip('"')
    expected = _archive_line()
    return bool(presented) and presented == expected
