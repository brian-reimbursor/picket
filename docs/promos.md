# Stuck card loads

A top-up can clear at the processor while billing is still reconnecting.
The wallet lists it on `GET /api/me` as `pending_loads`. Ops books it with
`POST /api/billing/pending/apply` `{ "id": "<payment id>" }` — one credit
per payment id. Customers do not have a button for this; they wait or write
in to staff.
