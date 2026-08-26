# Stuck card loads

When checkout is bouncing, the card processor may capture a load while the wallet still shows the old balance. Staff can credit from `/admin`. Customers who already paid can press **Apply pending load** on the wallet page (`POST /api/billing/pending/apply`).

That call confirms the capture with the processor, then credits the workspace once.
