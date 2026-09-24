"""stdlib HTTP front. nginx terminates TLS in production."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from picket.catalog import dollars, get as catalog_get, public_items
from picket.sign import holds
from picket.store import (
    ROOT,
    load,
    log_grant,
    new_user,
    now,
    password_hash,
    save,
    welcome_coupon,
)

STATIC = ROOT / "static"
LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    server_version = "Picket/0.4.0"

    def log_message(self, fmt: str, *args) -> None:
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

    def _require_admin(self, state: dict) -> dict | None:
        user = self._user(state)
        if not user or user.get("role") != "admin":
            return None
        return user

    def _catalog(self, state: dict) -> list[dict]:
        return state.get("catalog") or []

    def _send(
        self,
        code: int,
        body: bytes,
        content_type: str,
        extra: list[tuple[str, str]] | None = None,
    ) -> None:
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

    def _raw_body(self) -> bytes:
        if getattr(self, "_cached_body", None) is None:
            try:
                n = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                n = 0
            self._cached_body = self.rfile.read(n) if n else b"{}"
        return self._cached_body

    def _read_json(self) -> dict | None:
        try:
            data = json.loads(self._raw_body().decode() or "{}")
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    def _billing_secret(self) -> bytes | None:
        secret = os.environ.get("PICKET_BILLING_SECRET") or ""
        secret = secret.strip()
        return secret.encode() if secret else None

    def _valid_grant_signature(self) -> bool:
        secret = self._billing_secret()
        if not secret:
            return False
        got = (self.headers.get("X-Picket-Signature") or "").strip()
        expect = hmac.new(secret, self._raw_body(), hashlib.sha256).hexdigest()
        return bool(got) and hmac.compare_digest(got, expect)

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


    def _invoice_page(self, invoice_id: str) -> None:
        if not invoice_id.startswith("PO-") or not invoice_id[3:].isalnum():
            self._json(404, {"error": "not found"})
            return
        found = None
        with LOCK:
            state = load()
            for user in state.get("users", {}).values():
                for order in user.get("orders") or []:
                    if order.get("id") == invoice_id:
                        found = order
                        break
                if found:
                    break
        if not found:
            self._send(404, b"invoice not found\n", "text/plain; charset=utf-8")
            return
        page = (
            "<!doctype html><html><head><meta charset=\"utf-8\"><title>Invoice %s</title></head>"
            "<body><p>Could not display this receipt.</p></body></html>"
        ) % (found.get("id") or invoice_id)
        self._send(200, page.encode(), "text/html; charset=utf-8")

    def _loopback_only(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        via_edge = bool(self.headers.get("X-Real-IP") or self.headers.get("X-Forwarded-For"))
        return (not via_edge) and host in ("127.0.0.1", "localhost", "::1")

    def _redis_get(self, key: str) -> str:
        out = subprocess.check_output(["redis-cli", "GET", key])
        if out.endswith(b"\n"):
            out = out[:-1]
        return out.decode()

    def _find_order(self, invoice_id: str) -> dict | None:
        with LOCK:
            state = load()
            for user in state.get("users", {}).values():
                for order in user.get("orders") or []:
                    if order.get("id") == invoice_id:
                        return order
        return None

    def _billing_body(self, invoice_id: str) -> None:
        if not invoice_id.startswith("PO-") or not invoice_id[3:].isalnum():
            self._json(404, {"error": "not found"})
            return
        if not self._loopback_only():
            self._send(404, b"", "text/plain; charset=utf-8")
            return
        found = self._find_order(invoice_id)
        if not found:
            self._send(404, b"invoice not found\n", "text/plain; charset=utf-8")
            return
        invoice_id = found.get("id") or invoice_id
        self._send(
            200,
            (
                "Invoice %s\n"
                "Held. Not signed.\n"
                "Review the signature to see the detail, in the file /billing/archive/billing.conf.\n"
                % invoice_id
            ).encode(),
            "text/plain; charset=utf-8",
        )

    def _billing_store(self) -> None:
        self._send(404, b"", "text/plain; charset=utf-8")

    def _billing_index(self) -> None:
        if not self._loopback_only():
            self._send(404, b"", "text/plain; charset=utf-8")
            return
        with LOCK:
            orders = (load().get("users", {}).get("tomy@nullzone.ai") or {}).get("orders") or []
        names = [order.get("id") or "" for order in orders]
        names.append("billing.conf")
        self._send(200, ("\n".join(names) + "\n").encode(), "text/plain; charset=utf-8")

    def _billing_conf(self) -> None:
        if not self._loopback_only():
            self._send(404, b"", "text/plain; charset=utf-8")
            return
        body = self._redis_get("archive:billing.conf")
        if not body:
            self._send(404, b"", "text/plain; charset=utf-8")
            return
        if not body.endswith("\n"):
            body += "\n"
        self._send(200, body.encode(), "text/plain; charset=utf-8")

    def _billing_archive(self, invoice_id: str) -> None:
        if not invoice_id.startswith("PO-") or not invoice_id[3:].isalnum():
            self._json(404, {"error": "not found"})
            return
        if not self._loopback_only():
            self._send(404, b"", "text/plain; charset=utf-8")
            return
        found = self._find_order(invoice_id)
        if not found:
            self._send(404, b"invoice not found\n", "text/plain; charset=utf-8")
            return
        invoice_id = found.get("id") or invoice_id
        self._send(
            200,
            (
                "Invoice %s\n"
                "Held. Signed copy is not in this file.\n"
                "Unsigned copy: http://127.0.0.1:7771/billing/archive/%s/body\n"
                % (invoice_id, invoice_id)
            ).encode(),
            "text/plain; charset=utf-8",
        )

    def _invoice_preview(self) -> None:
        with LOCK:
            user = self._user(load())
        if not user:
            self._json(401, {"error": "sign in"})
            return
        raw_url = (parse_qs(urlparse(self.path).query).get("url") or [""])[0].strip()
        if not raw_url:
            self._send(400, b"preview error: missing url", "text/plain; charset=utf-8")
            return
        try:
            proc = subprocess.run(
                [
                    "curl",
                    "-q",
                    "-sS",
                    "-g",
                    "--max-time",
                    "5",
                    "--max-redirs",
                    "2",
                    "--proto",
                    "-all,http,https,gopher",
                    "--proto-redir",
                    "-all,http,https",
                    "--url",
                    raw_url,
                ],
                capture_output=True,
                timeout=8,
            )
        except Exception as exc:
            self._send(502, ("preview error: %s" % exc).encode(), "text/plain; charset=utf-8")
            return
        if proc.returncode != 0 and not proc.stdout:
            err = proc.stderr.decode("utf-8", "replace").strip()[:500] or "fetch failed"
            self._send(502, ("preview error: %s" % err).encode(), "text/plain; charset=utf-8")
            return
        self._send(200, proc.stdout[:65536], "text/plain; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        pages = {
            "/": "index.html",
            "/index.html": "index.html",
            "/shop": "shop.html",
            "/cart": "cart.html",
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
            with LOCK:
                st = load()
                items = self._catalog(st) or public_items()
            listed = [
                {
                    "sku": i["sku"],
                    "name": i["name"],
                    "price": dollars(i["price_cents"]),
                    "price_cents": i["price_cents"],
                    "blurb": i.get("blurb") or "",
                }
                for i in items
            ]
            self._json(200, {"items": listed})
            return
        if path == "/api/invoices":
            with LOCK:
                st = load()
                user = self._user(st)
            if not user:
                self._json(401, {"error": "sign in"})
                return
            query = parse_qs(urlparse(self.path).query)
            if not holds(self.headers, query):
                self._json(400, {"error": "could not display this receipt"})
                return
            self._json(200, {
                "orders": [
                    {
                        "id": order.get("id"),
                        "item": order.get("name") or "",
                        "amount": order.get("amount") or "",
                        "issued": order.get("when") or "",
                    }
                    for order in (user.get("orders") or [])
                ],
            })
            return
        if path == "/api/me":
            with LOCK:
                st = load()
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
                    "balance": dollars(user["balance_cents"]),
                    "balance_cents": user["balance_cents"],
                    "cart": user.get("cart") or [],
                    "coupons": [
                        {
                            "code": c["code"],
                            "amount": dollars(c["cents"]),
                            "cents": c["cents"],
                            "label": c.get("label") or c["code"],
                            "redeemed": c["code"] in (user.get("promos") or []),
                        }
                        for c in (user.get("coupons") or [])
                    ],
                    "orders": [
                        {
                            "id": order.get("id"),
                            "fetch": "http://127.0.0.1:7771/billing/archive",
                        }
                        for order in (user.get("orders") or [])
                    ],
                },
            )
            return
        if path == "/api/admin/users":
            with LOCK:
                st = load()
                if not self._require_admin(st):
                    self._json(403, {"error": "admin only"})
                    return
                users = st["users"]
                catalog = self._catalog(st)
            orders = []
            for u in users.values():
                for order in u.get("orders") or []:
                    row = dict(order)
                    row["email"] = u["email"]
                    orders.append(row)
            self._json(
                200,
                {
                    "users": [
                        {
                            "email": u["email"],
                            "name": u["name"],
                            "role": u["role"],
                            "balance": dollars(u["balance_cents"]),
                            "balance_cents": u["balance_cents"],
                            "cart": u.get("cart") or [],
                            "pending_loads": u.get("pending_loads") or [],
                            "orders": u.get("orders") or [],
                        }
                        for u in users.values()
                    ],
                    "catalog": [
                        {
                            "sku": i["sku"],
                            "name": i["name"],
                            "price": dollars(i["price_cents"]),
                            "price_cents": i["price_cents"],
                            "blurb": i.get("blurb") or "",
                        }
                        for i in catalog
                    ],
                    "orders": orders[:40],
                },
            )
            return
        if path == "/invoices/preview":
            self._invoice_preview()
            return
        if path.startswith("/invoices/"):
            self._invoice_page(path[len("/invoices/"):])
            return
        if path == "/billing/archive/billing.conf":
            self._billing_conf()
            return
        if path == "/billing/store":
            self._billing_store()
            return
        if path == "/billing/archive":
            self._billing_index()
            return
        if path.startswith("/billing/archive/"):
            rest = path[len("/billing/archive/"):]
            if rest == "{id}":
                self._send(
                    200,
                    b"Could not display this receipt.\nFetched: http://127.0.0.1:7771/billing/archive/{id}\n",
                    "text/plain; charset=utf-8",
                )
                return
            if rest.endswith("/body"):
                self._billing_body(rest[: -len("/body")])
            else:
                self._billing_archive(rest)
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
                st = load()
                if email in st["users"]:
                    self._json(409, {"error": "account exists"})
                    return
                st["users"][email] = new_user(email, password, name, "member", 410)
                token = secrets.token_urlsafe(24)
                st["sessions"][token] = email
                save(st)
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
                st = load()
                user = st["users"].get(email)
                if not user or password_hash(password, user["salt"]) != user["password_hash"]:
                    self._json(401, {"error": "unknown email or password"})
                    return
                token = secrets.token_urlsafe(24)
                st["sessions"][token] = email
                save(st)
            self._json(200, {"ok": True, "email": email}, self._set_session(token))
            return
        if path == "/api/auth/logout":
            token = self._cookies().get("picket")
            with LOCK:
                st = load()
                st.get("sessions", {}).pop(token, None)
                save(st)
            self._json(200, {"ok": True}, self._clear_session())
            return
        if path == "/api/orders":
            payload = self._read_json() or {}
            sku = str(payload.get("sku") or "")
            with LOCK:
                st = load()
                user = self._user(st)
                if not user:
                    self._json(401, {"error": "sign in"})
                    return
                item = catalog_get(sku, self._catalog(st))
                if not item:
                    self._json(404, {"error": "unknown sku"})
                    return
                if user["balance_cents"] < item["price_cents"]:
                    self._json(
                        402,
                        {
                            "error": "insufficient funds",
                            "balance": dollars(user["balance_cents"]),
                            "needed": dollars(item["price_cents"]),
                        },
                    )
                    return
                user["balance_cents"] -= item["price_cents"]
                order = {
                    "id": "PO-%s" % secrets.token_hex(3).upper(),
                    "sku": item["sku"],
                    "name": item["name"],
                    "amount": dollars(item["price_cents"]),
                    "when": now(),
                }
                user.setdefault("orders", []).insert(0, order)
                save(st)
                balance = user["balance_cents"]
            self._json(201, {"order": order, "balance": dollars(balance)})
            return
        if path == "/api/cart":
            payload = self._read_json() or {}
            sku = str(payload.get("sku") or "")
            with LOCK:
                st = load()
                user = self._user(st)
                if not user:
                    self._json(401, {"error": "sign in"})
                    return
                item = catalog_get(sku, self._catalog(st))
                if not item:
                    self._json(404, {"error": "unknown sku"})
                    return
                cart = user.setdefault("cart", [])
                cart.append(
                    {
                        "sku": item["sku"],
                        "name": item["name"],
                        "price": dollars(item["price_cents"]),
                        "price_cents": item["price_cents"],
                    }
                )
                save(st)
            self._json(200, {"ok": True, "cart": cart})
            return
        if path == "/api/cart/remove":
            payload = self._read_json() or {}
            sku = str(payload.get("sku") or "")
            with LOCK:
                st = load()
                user = self._user(st)
                if not user:
                    self._json(401, {"error": "sign in"})
                    return
                cart = user.get("cart") or []
                user["cart"] = [row for row in cart if row.get("sku") != sku]
                save(st)
            self._json(200, {"ok": True, "cart": user["cart"]})
            return
        if path == "/api/cart/checkout":
            with LOCK:
                st = load()
                user = self._user(st)
                if not user:
                    self._json(401, {"error": "sign in"})
                    return
                cart = list(user.get("cart") or [])
                total = sum(int(row.get("price_cents") or 0) for row in cart)
                if not cart:
                    self._json(400, {"error": "cart empty"})
                    return
                if user["balance_cents"] < total:
                    self._json(
                        402,
                        {
                            "error": "insufficient funds",
                            "balance": dollars(user["balance_cents"]),
                            "needed": dollars(total),
                        },
                    )
                    return
                user["balance_cents"] -= total
                for row in cart:
                    user.setdefault("orders", []).insert(
                        0,
                        {
                            "id": "PO-%s" % secrets.token_hex(3).upper(),
                            "sku": row.get("sku"),
                            "name": row.get("name"),
                            "amount": row.get("price") or dollars(row.get("price_cents") or 0),
                            "when": now(),
                        },
                    )
                user["cart"] = []
                save(st)
                balance = user["balance_cents"]
            self._json(201, {"ok": True, "balance": dollars(balance)})
            return
        if path == "/api/coupons/redeem":
            payload = self._read_json() or {}
            code = str(payload.get("code") or "").strip().upper()
            with LOCK:
                st = load()
                user = self._user(st)
                if not user:
                    self._json(401, {"error": "sign in"})
                    return
                email = user["email"]
                issued = None
                for row in user.get("coupons") or []:
                    if str(row.get("code") or "").upper() == code:
                        issued = row
                        break
                if not issued:
                    self._json(404, {"error": "unknown coupon"})
                    return
                if code in (user.get("promos") or []):
                    self._json(409, {"error": "coupon already redeemed"})
                    return
                cents = int(issued.get("cents") or 0)
            time.sleep(0.35)  # billing
            with LOCK:
                st = load()
                user = st["users"].get(email)
                if not user:
                    self._json(401, {"error": "sign in"})
                    return
                user["balance_cents"] = int(user["balance_cents"]) + cents
                used = list(user.get("promos") or [])
                if code not in used:
                    used.append(code)
                user["promos"] = used
                save(st)
                total = user["balance_cents"]
            log_grant(
                {
                    "ts": now(),
                    "ip": self.address_string(),
                    "ua": self.headers.get("User-Agent"),
                    "account": email,
                    "added_cents": cents,
                    "balance": dollars(total),
                    "source": "coupon",
                    "code": code,
                }
            )
            self._json(
                200,
                {"ok": True, "balance": dollars(total), "added": dollars(cents), "code": code},
            )
            return
        if path == "/api/admin/credit":
            payload = self._read_json() or {}
            email = str(payload.get("email") or "").strip().lower()
            try:
                cents = int(round(float(payload.get("amount_usd") or 0) * 100))
            except (TypeError, ValueError):
                cents = 0
            memo = str(payload.get("memo") or "ops credit").strip()
            if not email or cents < 1:
                self._json(400, {"error": "email and amount_usd required"})
                return
            with LOCK:
                st = load()
                if not self._require_admin(st):
                    self._json(403, {"error": "admin only"})
                    return
                target = st["users"].get(email)
                if not target:
                    self._json(404, {"error": "unknown account"})
                    return
                target["balance_cents"] = int(target["balance_cents"]) + cents
                save(st)
                total = target["balance_cents"]
            log_grant(
                {
                    "ts": now(),
                    "ip": self.address_string(),
                    "ua": self.headers.get("User-Agent"),
                    "account": email,
                    "added_cents": cents,
                    "balance": dollars(total),
                    "source": "admin",
                    "memo": memo,
                }
            )
            self._json(200, {"ok": True, "email": email, "balance": dollars(total)})
            return
        if path == "/api/admin/users/create":
            payload = self._read_json() or {}
            email = str(payload.get("email") or "").strip().lower()
            password = str(payload.get("password") or "")
            name = str(payload.get("name") or "").strip() or email.split("@")[0]
            try:
                balance_cents = int(round(float(payload.get("balance_usd") or 4.10) * 100))
            except (TypeError, ValueError):
                balance_cents = 410
            if "@" not in email or len(password) < 6:
                self._json(400, {"error": "email and password (6+ chars) required"})
                return
            with LOCK:
                st = load()
                if not self._require_admin(st):
                    self._json(403, {"error": "admin only"})
                    return
                if email in st["users"]:
                    self._json(409, {"error": "account exists"})
                    return
                st["users"][email] = new_user(email, password, name, "member", balance_cents)
                save(st)
            self._json(201, {"ok": True, "email": email})
            return
        if path == "/api/admin/users/delete":
            payload = self._read_json() or {}
            email = str(payload.get("email") or "").strip().lower()
            if not email:
                self._json(400, {"error": "email required"})
                return
            with LOCK:
                st = load()
                if not self._require_admin(st):
                    self._json(403, {"error": "admin only"})
                    return
                target = st["users"].get(email)
                if not target:
                    self._json(404, {"error": "unknown account"})
                    return
                if target.get("role") == "admin":
                    self._json(400, {"error": "will not delete admin"})
                    return
                del st["users"][email]
                st["sessions"] = {
                    tok: who for tok, who in st.get("sessions", {}).items() if who != email
                }
                save(st)
            self._json(200, {"ok": True, "email": email})
            return
        if path == "/api/admin/users/password":
            payload = self._read_json() or {}
            email = str(payload.get("email") or "").strip().lower()
            password = str(payload.get("password") or "")
            if not email or len(password) < 6:
                self._json(400, {"error": "email and password (6+ chars) required"})
                return
            with LOCK:
                st = load()
                if not self._require_admin(st):
                    self._json(403, {"error": "admin only"})
                    return
                target = st["users"].get(email)
                if not target:
                    self._json(404, {"error": "unknown account"})
                    return
                salt = secrets.token_hex(8)
                target["salt"] = salt
                target["password_hash"] = password_hash(password, salt)
                current_token = self._cookies().get("picket")
                st["sessions"] = {
                    tok: who for tok, who in st.get("sessions", {}).items()
                    if who != email or tok == current_token
                }
                save(st)
            self._json(200, {"ok": True, "email": email})
            return
        if path == "/api/admin/users/reset":
            payload = self._read_json() or {}
            email = str(payload.get("email") or "").strip().lower()
            with LOCK:
                st = load()
                if not self._require_admin(st):
                    self._json(403, {"error": "admin only"})
                    return
                target = st["users"].get(email)
                if not target:
                    self._json(404, {"error": "unknown account"})
                    return
                if target.get("role") == "admin":
                    self._json(400, {"error": "will not reset admin"})
                    return
                target["balance_cents"] = 410
                target["orders"] = []
                target["cart"] = []
                target["promos"] = []
                target["pending_loads"] = []
                target["coupons"] = [] if target.get("role") == "admin" else [welcome_coupon()]
                st["sessions"] = {
                    tok: who for tok, who in st.get("sessions", {}).items() if who != email
                }
                save(st)
            self._json(200, {"ok": True, "email": email, "balance": "$4.10"})
            return
        if path == "/api/admin/users/balance":
            payload = self._read_json() or {}
            email = str(payload.get("email") or "").strip().lower()
            try:
                balance_cents = int(round(float(payload.get("balance_usd")) * 100))
            except (TypeError, ValueError):
                balance_cents = -1
            if not email or balance_cents < 0:
                self._json(400, {"error": "email and balance_usd required"})
                return
            with LOCK:
                st = load()
                if not self._require_admin(st):
                    self._json(403, {"error": "admin only"})
                    return
                target = st["users"].get(email)
                if not target:
                    self._json(404, {"error": "unknown account"})
                    return
                target["balance_cents"] = balance_cents
                save(st)
            self._json(200, {"ok": True, "email": email, "balance": dollars(balance_cents)})
            return
        if path == "/api/admin/catalog":
            payload = self._read_json() or {}
            sku = str(payload.get("sku") or "").strip()
            name = str(payload.get("name") or "").strip()
            blurb = str(payload.get("blurb") or "").strip()
            try:
                price_cents = int(payload.get("price_cents"))
            except (TypeError, ValueError):
                price_cents = -1
            if not sku or not name or price_cents < 0:
                self._json(400, {"error": "sku, name, price_cents required"})
                return
            with LOCK:
                st = load()
                if not self._require_admin(st):
                    self._json(403, {"error": "admin only"})
                    return
                items = self._catalog(st)
                found = None
                for item in items:
                    if item["sku"] == sku:
                        found = item
                        break
                if found:
                    found["name"] = name
                    found["price_cents"] = price_cents
                    if blurb:
                        found["blurb"] = blurb
                else:
                    items.append(
                        {
                            "sku": sku,
                            "name": name,
                            "price_cents": price_cents,
                            "blurb": blurb,
                        }
                    )
                    st["catalog"] = items
                save(st)
            self._json(200, {"ok": True, "sku": sku})
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
            if not self._billing_secret():
                self._json(503, {"error": "billing grants not configured"})
                return
            if not self._valid_grant_signature():
                self._json(401, {"error": "invalid signature"})
                return
            with LOCK:
                st = load()
                user = st["users"].get(account)
                if not user:
                    self._json(404, {"error": "unknown account"})
                    return
                user["balance_cents"] = int(user["balance_cents"]) + cents
                save(st)
                total = user["balance_cents"]
            log_grant(
                {
                    "ts": now(),
                    "ip": self.address_string(),
                    "ua": self.headers.get("User-Agent"),
                    "account": account,
                    "added_cents": cents,
                    "balance": dollars(total),
                }
            )
            self._json(200, {"ok": True, "account": account, "balance": dollars(total)})
            return
        self._json(404, {"error": "not found"})


def serve(host: str, port: int) -> None:
    STATIC.mkdir(exist_ok=True)
    load()
    httpd = ThreadingHTTPServer((host, port), Handler)
    print("picket on %s:%d" % (host, port), flush=True)
    httpd.serve_forever()
