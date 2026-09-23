# HTTP API

The storefront talks JSON to the same origin. Session cookies are `HttpOnly`.

Integrators (billing, catalog sync) should treat [`openapi.yaml`](openapi.yaml) as the source of truth rather than scraping the HTML.

Customer flows (signup, login, catalog, checkout from wallet) are covered there. `/api/me` lists each order with a `fetch` URL. The receipt itself is loaded with `GET /invoices/preview?url=`; the account page calls that and does not render the body. Wallet loads from the card processor arrive as signed billing grants. Workspace coupons are documented in [`promos.md`](promos.md).
