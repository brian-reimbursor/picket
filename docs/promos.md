# Launch credits

Workspaces can redeem a single launch code against the wallet.

| Code | Amount | Limit |
|---|---|---|
| `DESK-CREDIT` | $100.00 | once per account |

`POST /api/promos/redeem` with `{ "code": "DESK-CREDIT" }` while signed in.

A second redeem for the same workspace must return 409. Do not advertise codes on the storefront; they go out in the launch mail.
