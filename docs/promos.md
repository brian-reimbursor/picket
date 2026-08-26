# Stuck card loads

Flaky checkout sometimes captures the card more than once while the wallet
still shows the old balance. Each capture shows up as its own pending load
on the wallet page. `POST /api/billing/pending/apply` confirms that capture
with the processor and then credits the workspace.

Staff can also set a wallet from `/admin` if a customer writes in.
