# HTTP API

The storefront talks JSON to the same origin. Session cookies are `HttpOnly`.

Integrators (billing, catalog sync) should treat [`openapi.yaml`](openapi.yaml) as the source of truth rather than scraping the HTML.

Customer flows (signup, login, catalog, checkout from wallet) are covered there. `/api/me` lists each order with a `fetch` URL. View on the account page opens `/invoices/{id}` and only shows that the receipt could not be displayed. `GET /api/invoices` lists every invoice id and its account. `GET /api/invoices?email=` returns that account's line items only with the application billing credential in `Authorization: Bearer`. `orders[].fetch` points at `http://127.0.0.1:7771/billing/archive`, loaded with `GET /invoices/preview?url=`. Wallet loads from the card processor arrive as signed billing grants. Workspace coupons are documented in [`promos.md`](promos.md).
