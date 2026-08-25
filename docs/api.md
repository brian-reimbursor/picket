# HTTP API

The storefront talks JSON to the same origin. Session cookies are `HttpOnly`.

Integrators (billing, catalog sync) should treat [`openapi.yaml`](openapi.yaml) as the source of truth rather than scraping the HTML.

Customer flows (signup, login, catalog, checkout from wallet) are covered there, as is the billing-provider grant used when a wallet load clears.
