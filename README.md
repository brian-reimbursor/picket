# Picket

Workspace hardware shop. Customers keep a USD wallet and buy deskside gear (hubs, stands, monitors, docks). Each order draws from that balance.

Production: https://invoices.reimbursor.info/

## HTTP

```
POST /api/auth/register
POST /api/auth/login
GET  /api/me
GET  /api/catalog
POST /api/orders
POST /api/billing/grants   # billing provider → us, after a wallet load
```

Full contract: [`openapi.yaml`](openapi.yaml).

## Run locally

```bash
python3 server.py --port 7771
```

`state.json` holds users and sessions. Do not commit it.
