# Picket

Invoice sending for small teams. You buy send credits; each invoice that goes out spends one.

Production: https://invoices.reimbursor.info/

## Usage

```
GET  /api/me
POST /api/invoices
POST /api/billing/grants   # billing provider → us, after a pack purchase
```

The HTTP surface is in [`openapi.yaml`](openapi.yaml).

## Run locally

```bash
python3 server.py --port 7771
```

State lives in `state.json` next to the process.
