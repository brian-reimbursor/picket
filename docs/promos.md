# Stuck card loads

If checkout dies after the card processor captures a top-up, the wallet
shows that payment as still confirming. `POST /api/billing/pending/apply`
is the customer retry: confirm with the processor, then book the wallet
once for that payment id.

Staff can set a balance from `/admin` if a customer writes in.
