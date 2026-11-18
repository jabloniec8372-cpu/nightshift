"""The night watchman's rules.

Every product gets exactly one decision. The important part is what NightShift
refuses to do: it never applies a price jump it can't explain, never touches a
product the supplier didn't mention, and never sells stock the supplier
doesn't safely have.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

from .feed import SupplierItem


class Action(str, Enum):
    OK = "ok"                      # nothing to change
    UPDATE = "update"              # price and/or stock corrected in the shop
    SOLD_OUT = "sold_out"          # supplier ran low: shop set to 0
    RESTOCK = "restock"            # supplier has it again: back on sale
    HOLD = "hold"                  # price jump too big: NOT applied, ask the owner
    TO_CHECK = "to_check"          # shop sells it, supplier feed doesn't mention it


@dataclass(frozen=True)
class Rules:
    margin: float = 0.35           # 35% on top of supplier cost
    safety_buffer: int = 2         # keep this many units back at the supplier
    max_listed: int = 50           # never list more than this
    max_price_jump: float = 0.30   # bigger change than 30% waits for a human
    price_ending: float = 0.99     # 24.99 instead of 24.30


@dataclass(frozen=True)
class ShopItem:
    sku: str
    title: str
    price: float
    stock: int


@dataclass
class Decision:
    sku: str
    title: str
    action: Action
    old_price: float
    new_price: float
    old_stock: int
    new_stock: int
    notes: list[str] = field(default_factory=list)

    @property
    def changes_shop(self) -> bool:
        return (self.new_price, self.new_stock) != (self.old_price, self.old_stock)


def target_price(cost: float, rules: Rules) -> float:
    raw = cost * (1 + rules.margin)
    whole = math.floor(raw)
    candidate = whole + rules.price_ending
    if candidate < raw:
        candidate += 1
    return round(candidate, 2)


def target_stock(supplier_stock: int, rules: Rules) -> int:
    return max(0, min(supplier_stock - rules.safety_buffer, rules.max_listed))


def decide(shop: ShopItem, supplier: SupplierItem | None, rules: Rules) -> Decision:
    d = Decision(shop.sku, shop.title, Action.OK, shop.price, shop.price, shop.stock, shop.stock)

    if supplier is None:
        d.action = Action.TO_CHECK
        d.notes.append("not in the supplier feed - left untouched, please check")
        return d

    new_stock = target_stock(supplier.stock, rules)
    new_price = target_price(supplier.cost, rules)

    jump = abs(new_price - shop.price) / shop.price if shop.price else 1.0
    price_held = jump > rules.max_price_jump
    if price_held:
        d.notes.append(
            f"price would move {shop.price:.2f} -> {new_price:.2f} ({jump:+.0%}); held for a human"
        )
        new_price = shop.price

    d.new_price, d.new_stock = new_price, new_stock

    if new_stock == 0 and shop.stock > 0:
        d.action = Action.SOLD_OUT
        d.notes.append(f"supplier has only {supplier.stock}; set to 0 so nobody buys air")
    elif new_stock > 0 and shop.stock == 0:
        d.action = Action.RESTOCK
        d.notes.append(f"supplier has {supplier.stock} again; back on sale")
    elif price_held:
        d.action = Action.HOLD
    elif d.changes_shop:
        d.action = Action.UPDATE

    # A held price is the headline even if stock also moved.
    if price_held and d.action in (Action.SOLD_OUT, Action.RESTOCK):
        d.notes.append("stock was corrected, price was not")
    return d


def decide_all(shop_items: list[ShopItem], feed: dict[str, SupplierItem], rules: Rules,
               broken_skus: set[str] | None = None) -> list[Decision]:
    decisions = [decide(item, feed.get(item.sku), rules) for item in shop_items]
    for d in decisions:
        if d.action is Action.TO_CHECK and broken_skus and d.sku in broken_skus:
            d.notes = ["supplier row is broken - left untouched rather than guessed"]
    return decisions
