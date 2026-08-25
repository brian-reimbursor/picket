# Picket

Hardware for the desk, paid from a workspace wallet.

Teams keep a USD balance and buy the usual kit — hubs, stands, keyboards, monitors, docks — without a separate invoice round-trip for every dongle. Production lives at [invoices.reimbursor.info](https://invoices.reimbursor.info/).

## Features

- Email signup and session login
- Catalog with USD prices
- Wallet that orders draw from
- Staff view of workspace balances
- Billing provider hooks when a load clears (see the HTTP spec under `docs/`)

## Stack

Python 3.10+, stdlib only in production. The front is static HTML/CSS/JS served by the same process. nginx terminates TLS.

```
src/picket/     application
static/         storefront
docs/           product + OpenAPI
tests/
```

## Local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python3 server.py --port 7771
```

Then http://127.0.0.1:7771/

```bash
python -m pytest -q
```

Self-hosting notes: [`docs/self-hosting.md`](docs/self-hosting.md).  
HTTP contract: [`docs/openapi.yaml`](docs/openapi.yaml).

## License

MIT. See `LICENSE`.
