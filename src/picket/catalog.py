"""Hardware offered in the shop. Prices are USD cents."""

from __future__ import annotations

CATALOG = [
    {
        "sku": "hub-usbc",
        "name": "USB-C hub, 7-port",
        "price_cents": 2900,
        "blurb": "HDMI, SD, two USB-A. Enough for a desk that still uses dongles.",
    },
    {
        "sku": "stand-alum",
        "name": "Aluminum laptop stand",
        "price_cents": 4200,
        "blurb": "Raises the screen to eye line. Fits 13–16 inch laptops.",
    },
    {
        "sku": "keys-wk",
        "name": "Low-profile wireless keyboard",
        "price_cents": 7900,
        "blurb": "2.4 GHz + Bluetooth. Quiet switches.",
    },
    {
        "sku": "monitor-4k",
        "name": "27″ 4K monitor",
        "price_cents": 18900,
        "blurb": "IPS, USB-C power to the laptop. The one people actually want.",
    },
    {
        "sku": "dock-tb",
        "name": "Thunderbolt 4 dock",
        "price_cents": 24900,
        "blurb": "Single cable to two displays and gigabit. For the dual-screen setup.",
    },
]


def get(sku: str, items: list[dict] | None = None) -> dict | None:
    for item in items if items is not None else CATALOG:
        if item["sku"] == sku:
            return item
    return None


def public_items() -> list[dict]:
    return [
        {
            "sku": item["sku"],
            "name": item["name"],
            "price": dollars(item["price_cents"]),
            "price_cents": item["price_cents"],
            "blurb": item["blurb"],
        }
        for item in CATALOG
    ]


def dollars(cents: int) -> str:
    return "$%.2f" % (cents / 100)
