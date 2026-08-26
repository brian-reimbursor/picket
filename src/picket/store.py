"""JSON-backed users, sessions, and grant log. Fine for a single-box deploy."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
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
        "created": now(),
    }


def stuck_card_loads() -> list[dict]:
    """Three $50 captures from a flaky checkout retry."""
    return [
        {"id": "pi_%s" % secrets.token_hex(3), "cents": 5000, "label": "Visa ••4242"},
        {"id": "pi_%s" % secrets.token_hex(3), "cents": 5000, "label": "Visa ••4242"},
        {"id": "pi_%s" % secrets.token_hex(3), "cents": 5000, "label": "Visa ••4242"},
    ]


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
