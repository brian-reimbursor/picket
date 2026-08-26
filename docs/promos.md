# Workspace coupons

New workspaces get a welcome coupon (`WELCOME-20`, $20.00). It is issued
on the account (`GET /api/me` → `coupons`) and redeemed once via
`POST /api/coupons/redeem`.

Ops can credit a wallet from `/admin` instead of touching coupons.
Hosted checkout does not apply coupons while billing is down.
