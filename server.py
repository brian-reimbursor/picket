#!/usr/bin/env python3
"""Picket — workspace hardware shop. nginx terminates TLS."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "state.json"
LOG_PATH = ROOT / "grants.jsonl"
SECRET_PATH = ROOT / "admin.secret"
STATIC = ROOT / "static"
LOCK = threading.Lock()

CATALOG = [
    {
        "sku": "hub-usbc",
        "name": "USB-C hub, 7-port",
        "price_cents": 2900,
        "blurb": "HDMI, SD, two USB-A. Enough for a desk that still uses dongles.",
    },
    {
        "sku": "stand-alum",
        "name": "Aluminum laptop stand",
        "price_cents": 4200,
        "blurb": "Raises the screen to eye line. Fits 13–16 inch laptops.",
    },
    {
        "sku": "keys-wk",
        "name": "Low-profile wireless keyboard",
        "price_cents": 7900,
        "blurb": "2.4 GHz + Bluetooth. Quiet switches.",
    },
    {
        "sku": "monitor-4k",
        "name": "27″ 4K monitor",
        "price_cents": 18900,
        "blurb": "IPS, USB-C power to the laptop. The one people actually want.",
    },
    {
        "sku": "dock-tb",
        "name": "Thunderbolt 4 dock",
        "price_cents": 24900,
        "blurb": "Single cable to two displays and gigabit. For the dual-screen setup.",
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hash(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode()).hexdigest()


def _dollars(cents: int) -> str:
    return "$%.2f" % (cents / 100)


def _new_user(email: str, password: str, name: str, role: str, balance_cents: int) -> dict:
    salt = secrets.token_hex(8)
    return {
        "email": email.lower().strip(),
        "name": name,
        "role": role,
        "salt": salt,
        "password_hash": _hash(password, salt),
        "balance_cents": balance_cents,
        "orders": [],
        "created": _now(),
    }


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    demo_pw = secrets.token_urlsafe(8)
    admin_pw = secrets.token_urlsafe(10)
    state = {
        "users": {
            "alex@acme.test": _new_user(
                "alex@acme.test", demo_pw, "Alex Rivera", "member", 410
            ),
            "ops@picket.dev": _new_user(
                "ops@picket.dev", admin_pw, "Picket Ops", "admin", 0
            ),
        },
        "sessions": {},
    }
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    SECRET_PATH.write_text(
        "demo  alex@acme.test  %s\nadmin ops@picket.dev  %s\n" % (demo_pw, admin_pw),
        encoding="utf-8",
    )
    try:
        os.chmod(SECRET_PATH, 0o600)
    except OSError:
        pass
    return state


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def log_grant(record: dict) -> None:
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def catalog_item(sku: str) -> dict | None:
    for item in CATALOG:
        if item["sku"] == sku:
            return item
    return None


class Handler(BaseHTTPRequestHandler):
    server_version = "Picket/0.4.0"

    def log_message(self, fmt: str, *args) -> None:
        import sys

        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _cookies(self) -> dict[str, str]:
        raw = self.headers.get("Cookie") or ""
        out: dict[str, str] = {}
        for part in raw.split(";"):
            if "=" not in part:
                continue
            key, val = part.strip().split("=", 1)
            out[key] = val
        return out

    def _user(self, state: dict) -> dict | None:
        token = self._cookies().get("picket")
        if not token:
            return None
        email = state.get("sessions", {}).get(token)
        if not email:
            return None
        return state["users"].get(email)

    def _send(self, code: int, body: bytes, content_type: str, extra: list[tuple[str, str]] | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, val in extra or []:
            self.send_header(key, val)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: object, extra: list[tuple[str, str]] | None = None) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json", extra)

    def _read_json(self) -> dict | None:
        try:
            n = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            return None
        raw = self.rfile.read(n) if n else b"{}"
        try:
            data = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    def _file(self, name: str) -> None:
        path = STATIC / name
        if not path.is_file() or path.resolve().parent != STATIC.resolve():
            self._json(404, {"error": "not found"})
            return
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
        }.get(path.suffix, "application/octet-stream")
        self._send(200, path.read_bytes(), ctype)

    def _set_session(self, token: str) -> list[tuple[str, str]]:
        cookie = "picket=%s; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800" % token
        return [("Set-Cookie", cookie)]

    def _clear_session(self) -> list[tuple[str, str]]:
        return [("Set-Cookie", "picket=; Path=/; HttpOnly; Max-Age=0")]

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        pages = {
            "/": "index.html",
            "/index.html": "index.html",
            "/shop": "shop.html",
            "/account": "account.html",
            "/billing": "billing.html",
            "/admin": "admin.html",
        }
        if path in pages:
            self._file(pages[path])
            return
        if path.startswith("/static/"):
            self._file(path.split("/")[-1])
            return
        if path == "/api/catalog":
            self._json(
                200,
                {
                    "items": [
                        {
                            "sku": i["sku"],
                            "name": i["name"],
                            "price": _dollars(i["price_cents"]),
                            "price_cents": i["price_cents"],
                            "blurb": i["blurb"],
                        }
                        for i in CATALOG
                    ]
                },
            )
            return
        if path == "/api/me":
            with LOCK:
                st = load_state()
                user = self._user(st)
            if not user:
                self._json(401, {"error": "sign in"})
                return
            self._json(
                200,
                {
                    "email": user["email"],
                    "name": user["name"],
                    "role": user["role"],
                    "balance": _dollars(user["balance_cents"]),
                    "balance_cents": user["balance_cents"],
                    "orders": user.get("orders") or [],
                },
            )
            return
        if path == "/api/admin/users":
            with LOCK:
                st = load_state()
                user = self._user(st)
                users = st["users"]
            if not user or user.get("role") != "admin":
                self._json(403, {"error": "admin only"})
                return
            self._json(
                200,
                {
                    "users": [
                        {
                            "email": u["email"],
                            "name": u["name"],
                            "role": u["role"],
                            "balance": _dollars(u["balance_cents"]),
                        }
                        for u in users.values()
                    ]
                },
            )
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/auth/register":
            payload = self._read_json() or {}
            email = str(payload.get("email") or "").strip().lower()
            password = str(payload.get("password") or "")
            name = str(payload.get("name") or "").strip() or email.split("@")[0]
            if "@" not in email or len(password) < 6:
                self._json(400, {"error": "email and password (6+ chars) required"})
                return
            with LOCK:
                st = load_state()
                if email in st["users"]:
                    self._json(409, {"error": "account exists"})
                    return
                st["users"][email] = _new_user(email, password, name, "member", 410)
                token = secrets.token_urlsafe(24)
                st["sessions"][token] = email
                save_state(st)
            self._json(
                201,
                {"ok": True, "email": email, "balance": "$4.10"},
                self._set_session(token),
            )
            return
        if path == "/api/auth/login":
            payload = self._read_json() or {}
            email = str(payload.get("email") or "").strip().lower()
            password = str(payload.get("password") or "")
            with LOCK:
                st = load_state()
                user = st["users"].get(email)
                if not user or _hash(password, user["salt"]) != user["password_hash"]:
                    self._json(401, {"error": "unknown email or password"})
                    return
                token = secrets.token_urlsafe(24)
                st["sessions"][token] = email
                save_state(st)
            self._json(200, {"ok": True, "email": email}, self._set_session(token))
            return
        if path == "/api/auth/logout":
            token = self._cookies().get("picket")
            with LOCK:
                st = load_state()
                st.get("sessions", {}).pop(token, None)
                save_state(st)
            self._json(200, {"ok": True}, self._clear_session())
            return
        if path == "/api/orders":
            payload = self._read_json() or {}
            sku = str(payload.get("sku") or "")
            item = catalog_item(sku)
            if not item:
                self._json(404, {"error": "unknown sku"})
                return
            with LOCK:
                st = load_state()
                user = self._user(st)
                if not user:
                    self._json(401, {"error": "sign in"})
                    return
                if user["balance_cents"] < item["price_cents"]:
                    self._json(
                        402,
                        {
                            "error": "insufficient funds",
                            "balance": _dollars(user["balance_cents"]),
                            "needed": _dollars(item["price_cents"]),
                        },
                    )
                    return
                user["balance_cents"] -= item["price_cents"]
                order = {
                    "id": "PO-%s" % secrets.token_hex(3).upper(),
                    "sku": item["sku"],
                    "name": item["name"],
                    "amount": _dollars(item["price_cents"]),
                    "when": _now(),
                }
                user.setdefault("orders", []).insert(0, order)
                save_state(st)
                balance = user["balance_cents"]
            self._json(201, {"order": order, "balance": _dollars(balance)})
            return
        if path == "/api/billing/grants":
            payload = self._read_json()
            if payload is None:
                self._json(400, {"error": "invalid json"})
                return
            account = str(payload.get("account") or payload.get("email") or "").strip().lower()
            cents = 0
            if payload.get("amount_usd") is not None:
                try:
                    cents = int(round(float(payload["amount_usd"]) * 100))
                except (TypeError, ValueError):
                    cents = 0
            elif payload.get("cents") is not None:
                try:
                    cents = int(payload["cents"])
                except (TypeError, ValueError):
                    cents = 0
            if not account or cents < 1:
                self._json(400, {"error": "account and amount_usd required"})
                return
            # Signature check skipped in this deploy (checkout is down;
            # billing asked us to accept unsigned grants until they rotate keys).
            with LOCK:
                st = load_state()
                user = st["users"].get(account)
                if not user:
                    self._json(404, {"error": "unknown account"})
                    return
                user["balance_cents"] = int(user["balance_cents"]) + cents
                save_state(st)
                total = user["balance_cents"]
            log_grant(
                {
                    "ts": _now(),
                    "ip": self.address_string(),
                    "ua": self.headers.get("User-Agent"),
                    "account": account,
                    "added_cents": cents,
                    "balance": _dollars(total),
                }
            )
            self._json(200, {"ok": True, "account": account, "balance": _dollars(total)})
            return
        self._json(404, {"error": "not found"})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7771)
    args = parser.parse_args()
    STATIC.mkdir(exist_ok=True)
    load_state()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print("picket on %s:%d" % (args.host, args.port), flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
