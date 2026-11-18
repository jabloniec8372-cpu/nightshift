"""Reading the supplier's feed.

Suppliers send stock and prices in every shape imaginable. NightShift reads a
CSV with at least three columns (sku, cost, stock) and refuses to guess when a
row is broken: a bad row is reported, never silently turned into a zero.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SupplierItem:
    sku: str
    cost: float
    stock: int


@dataclass(frozen=True)
class BadRow:
    line: int
    sku: str
    reason: str


# Column names suppliers actually use, mapped to ours.
ALIASES = {
    "sku": {"sku", "artikelnummer", "art_nr", "item_code", "code"},
    "cost": {"cost", "price", "ek", "einkaufspreis", "net_price", "cena"},
    "stock": {"stock", "qty", "quantity", "bestand", "available", "stan"},
}


def _column_map(header: list[str]) -> dict[str, str]:
    found = {}
    lowered = {h.strip().lower(): h for h in header}
    for ours, names in ALIASES.items():
        for name in names:
            if name in lowered:
                found[ours] = lowered[name]
                break
    missing = set(ALIASES) - set(found)
    if missing:
        raise ValueError(f"Supplier feed is missing columns: {', '.join(sorted(missing))}")
    return found


def _number(raw: str) -> float:
    # Accept both 18.50 and the German/Polish 18,50.
    return float(raw.strip().replace(" ", "").replace(",", "."))


def load_feed(path: str | Path) -> tuple[dict[str, SupplierItem], list[BadRow]]:
    items: dict[str, SupplierItem] = {}
    bad: list[BadRow] = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        sample = fh.read(2048)
        fh.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        reader = csv.DictReader(fh, dialect=dialect)
        cols = _column_map(reader.fieldnames or [])
        for line, row in enumerate(reader, start=2):
            sku = (row.get(cols["sku"]) or "").strip()
            if not sku:
                bad.append(BadRow(line, "", "empty SKU"))
                continue
            try:
                cost = _number(row.get(cols["cost"]) or "")
                stock = int(_number(row.get(cols["stock"]) or ""))
            except ValueError:
                bad.append(BadRow(line, sku, "cost or stock is not a number"))
                continue
            if cost <= 0:
                bad.append(BadRow(line, sku, f"cost {cost} is not a real price"))
                continue
            if stock < 0:
                bad.append(BadRow(line, sku, f"negative stock {stock}"))
                continue
            items[sku] = SupplierItem(sku, cost, stock)
    return items, bad
