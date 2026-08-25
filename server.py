#!/usr/bin/env python3
"""Picket — invoice sending. Bind 127.0.0.1; nginx terminates TLS."""

from __future__ import annotations

import argparse
import json
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "state.json"
LOG_PATH = ROOT / "grants.jsonl"
STATIC = ROOT / "static"

LOCK = threading.Lock()

DEFAULT_STATE = {
    "account": "acme-payments",
    "plan": "starter",
    "credits": 3,
    "invoices": [
        {
            "id": "INV-1841",
            "to": "northwind.example",
            "amount": "$240.00",
            "status": "sent",
            "when": "21 Aug",
        },
        {
            "id": "INV-1840",
            "to": "harbor freight co",
            "amount": "$1,080.00",
            "status": "sent",
            "when": "18 Aug",
        },
        {
            "id": "INV-1837",
            "to": "picket labs (internal)",
            "amount": "$0.00",
            "status": "draft",
            "when": "12 Aug",
        },
    ],
}


def load_state() -> dict:
    if not STATE_PATH.exists():
        STATE_PATH.write_text(json.dumps(DEFAULT_STATE, indent=2) + "\n", encoding="utf-8")
        return json.loads(json.dumps(DEFAULT_STATE))
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def log_grant(record: dict) -> None:
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


class Handler(BaseHTTPRequestHandler):
    server_version = "Picket/0.3.1"

    def log_message(self, fmt: str, *args) -> None:
        sys_stderr = __import__("sys").stderr
        sys_stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: object) -> None:
        raw = json.dumps(obj).encode()
        self._send(code, raw, "application/json")

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

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            return
        if path == "/billing":
            self._send(200, (STATIC / "billing.html").read_bytes(), "text/html; charset=utf-8")
            return
        if path.startswith("/static/"):
            name = path.split("/")[-1]
            file = STATIC / name
            if file.is_file() and file.resolve().parent == STATIC.resolve():
                ctype = {
                    ".css": "text/css; charset=utf-8",
                    ".js": "application/javascript; charset=utf-8",
                    ".svg": "image/svg+xml",
                }.get(file.suffix, "application/octet-stream")
                self._send(200, file.read_bytes(), ctype)
                return
            self._json(404, {"error": "not found"})
            return
        if path == "/api/me":
            with LOCK:
                st = load_state()
            self._json(
                200,
                {
                    "account": st["account"],
                    "plan": st["plan"],
                    "credits": st["credits"],
                },
            )
            return
        if path == "/api/invoices":
            with LOCK:
                st = load_state()
            self._json(200, {"invoices": st["invoices"]})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/invoices":
            payload = self._read_json()
            if payload is None:
                self._json(400, {"error": "invalid json"})
                return
            with LOCK:
                st = load_state()
                if st["credits"] < 1:
                    self._json(402, {"error": "no send credits remaining", "credits": st["credits"]})
                    return
                st["credits"] -= 1
                inv = {
                    "id": "INV-%d" % (1842 + len(st["invoices"])),
                    "to": str(payload.get("to") or "unknown"),
                    "amount": "$%.2f" % (int(payload.get("amount_cents") or 0) / 100),
                    "status": "sent",
                    "when": "today",
                }
                st["invoices"].insert(0, inv)
                save_state(st)
                credits = st["credits"]
            self._json(201, {"invoice": inv, "credits": credits})
            return
        if path == "/api/billing/grants":
            payload = self._read_json()
            if payload is None:
                self._json(400, {"error": "invalid json"})
                return
            account = str(payload.get("account") or "").strip()
            try:
                add = int(payload.get("credits"))
            except (TypeError, ValueError):
                add = 0
            if not account or add < 1:
                self._json(400, {"error": "account and credits>=1 required"})
                return
            # Signature check is skipped in this deploy (checkout is down;
            # billing asked us to accept unsigned grants until they rotate keys).
            with LOCK:
                st = load_state()
                if account != st["account"]:
                    self._json(404, {"error": "unknown account"})
                    return
                st["credits"] = int(st["credits"]) + add
                save_state(st)
                total = st["credits"]
            log_grant(
                {
                    "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "ip": self.address_string(),
                    "ua": self.headers.get("User-Agent"),
                    "account": account,
                    "added": add,
                    "credits": total,
                }
            )
            self._json(200, {"ok": True, "account": account, "credits": total})
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
