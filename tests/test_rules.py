from pathlib import Path

from nightshift.feed import SupplierItem, load_feed
from nightshift.rules import Action, Rules, ShopItem, decide, target_price

SAMPLE = Path(__file__).resolve().parent.parent / "sample" / "supplier_feed.csv"
R = Rules()


def test_price_ends_in_99_and_never_below_margin():
    assert target_price(18.50, R) == 24.99   # 24.975 -> 24.99
    assert target_price(4.00, R) == 5.99     # 5.40 -> 5.99
    assert target_price(14.00, R) == 18.99   # 18.90 -> 18.99
    assert target_price(14.07, R) == 19.99   # 18.9945 -> 18.99 would cut the margin


def test_sold_out_when_supplier_is_below_buffer():
    d = decide(ShopItem("A", "a", 8.99, 12), SupplierItem("A", 6.0, 1), R)
    assert d.action is Action.SOLD_OUT and d.new_stock == 0


def test_restock_when_supplier_has_it_again():
    d = decide(ShopItem("A", "a", 28.99, 0), SupplierItem("A", 21.0, 15), R)
    assert d.action is Action.RESTOCK and d.new_stock == 13


def test_big_price_jump_is_held_not_applied():
    d = decide(ShopItem("A", "a", 26.99, 14), SupplierItem("A", 30.0, 25), R)
    assert d.action is Action.HOLD
    assert d.new_price == 26.99          # untouched
    assert d.new_stock == 23             # stock still corrected


def test_missing_from_feed_is_left_alone():
    d = decide(ShopItem("A", "a", 34.99, 6), None, R)
    assert d.action is Action.TO_CHECK and not d.changes_shop


def test_listing_is_capped():
    d = decide(ShopItem("A", "a", 5.99, 50), SupplierItem("A", 4.2, 100), R)
    assert d.new_stock == R.max_listed and d.action is Action.OK


def test_feed_reads_german_columns_and_reports_broken_rows():
    items, bad = load_feed(SAMPLE)
    assert items["TEA-001"].cost == 18.5
    assert "TOWEL-007" not in items
    assert bad and bad[0].sku == "TOWEL-007"
