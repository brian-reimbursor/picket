from picket.catalog import dollars, get, public_items


def test_monitor_price() -> None:
    item = get("monitor-4k")
    assert item is not None
    assert item["price_cents"] == 18900
    assert dollars(item["price_cents"]) == "$189.00"


def test_unknown_sku() -> None:
    assert get("nope") is None


def test_public_catalog_has_five() -> None:
    items = public_items()
    assert len(items) == 5
    assert {row["sku"] for row in items} >= {"hub-usbc", "monitor-4k", "dock-tb"}
