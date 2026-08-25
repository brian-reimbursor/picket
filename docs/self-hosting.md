# Self-hosting

Bind the app to loopback and put TLS in front of it.

```bash
python3 server.py --host 127.0.0.1 --port 7771
```

`state.json` next to the process holds users and sessions. `grants.jsonl` is an append-only log of wallet loads from the billing provider. Neither file belongs in git.

A typical nginx `location /` proxies to `http://127.0.0.1:7771` and forwards `Host`, `X-Forwarded-For`, and `X-Forwarded-Proto`.
