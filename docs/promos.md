# Card-on-file loads

While hosted checkout is down, a workspace can charge the card on file
(`POST /api/billing/card`) for the $25 or $100 pack.

The product rule is **$100 per UTC day**. A second serial charge the same
day is rejected. Ops credits from `/admin` are not part of that cap.

The processor call is a short round-trip. Do not overlap in-flight charges
for the same account; the daily-cap check runs before that round-trip.
