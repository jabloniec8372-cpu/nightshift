"""Level 2: forwarding orders to the supplier, live.

Level 1 compared two files once a night. Level 2 reacts to events, keeps state
and has to survive everything that goes wrong between a shop and a supplier:

- the shop sends the same order twice (webhooks are delivered "at least once")
- someone posts a fake order to the webhook URL
- the supplier's API is down for a while
- an order contains something this supplier doesn't sell
- the tracking number arrives hours after the order was placed

Every order lives in SQLite with a status, so a crash or restart loses nothing:

    RECEIVED -> FORWARDED -> SHIPPED
        |  \\-> RETRY (supplier down, try again later) -> FAILED after max attempts
        \\----> NEEDS_HUMAN (something only a person can decide)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

RECEIVED, FORWARDED, SHIPPED = "received", "forwarded", "shipped"
RETRY, FAILED, NEEDS_HUMAN = "retry", "failed", "needs_human"


class TemporaryError(Exception):
    """Supplier is down or slow: worth trying again later."""


class PermanentError(Exception):
    """Trying again won't help: a person has to look at it."""


class Supplier(Protocol):
    def sells(self, sku: str) -> bool: ...
    def place_order(self, order_id: str, lines: list[dict], address: dict) -> str: ...
    def tracking(self, supplier_ref: str) -> str | None: ...


class Shop(Protocol):
    def fulfill(self, order_id: str, tracking: str) -> None: ...


@dataclass(frozen=True)
class Policy:
    max_attempts: int = 5
    first_wait_minutes: int = 2      # 2, 4, 8, 16 ... minutes between retries


def verify_shopify_hmac(raw_body: bytes, header_hmac: str, secret: str) -> bool:
    """Shopify signs every webhook: base64(HMAC-SHA256(secret, raw body))."""
    digest = hmac.new(secret.encode(), raw_body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, header_hmac or "")


class OrderDesk:
    def __init__(self, db_path: str, supplier: Supplier, shop: Shop, secret: str,
                 policy: Policy = Policy(), clock=datetime.now):
        self.db = sqlite3.connect(db_path)
        self.db.row_factory = sqlite3.Row
        self.supplier, self.shop, self.secret = supplier, shop, secret
        self.policy, self.clock = policy, clock
        self.log: list[str] = []
        self.db.execute("""CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY, status TEXT, payload TEXT, attempts INTEGER DEFAULT 0,
            next_try TEXT, supplier_ref TEXT, tracking TEXT, note TEXT, updated TEXT)""")
        self.db.commit()

    # -- helpers -------------------------------------------------------------
    def _say(self, msg: str) -> None:
        self.log.append(f"{self.clock():%H:%M} {msg}")

    def _set(self, order_id: str, **fields) -> None:
        fields["updated"] = self.clock().isoformat()
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.db.execute(f"UPDATE orders SET {cols} WHERE id = ?", (*fields.values(), order_id))
        self.db.commit()

    def status(self, order_id: str) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()

    def by_status(self, *statuses: str) -> list[sqlite3.Row]:
        marks = ",".join("?" * len(statuses))
        return self.db.execute(f"SELECT * FROM orders WHERE status IN ({marks}) ORDER BY id", statuses).fetchall()

    # -- step 1: an order arrives ----------------------------------------------
    def receive(self, raw_body: bytes, header_hmac: str) -> str:
        if not verify_shopify_hmac(raw_body, header_hmac, self.secret):
            self._say("rejected a webhook with a wrong signature (not from the shop)")
            return "rejected"
        order = json.loads(raw_body)
        order_id = str(order["id"])
        if self.status(order_id):
            self._say(f"order {order_id} arrived again - duplicate ignored")
            return "duplicate"
        self.db.execute("INSERT INTO orders (id, status, payload, updated) VALUES (?, ?, ?, ?)",
                        (order_id, RECEIVED, raw_body.decode(), self.clock().isoformat()))
        self.db.commit()
        self._say(f"order {order_id} received")
        return "accepted"

    # -- step 2: forward to the supplier -------------------------------------
    def forward_due(self) -> None:
        now = self.clock()
        for row in self.by_status(RECEIVED, RETRY):
            if row["next_try"] and datetime.fromisoformat(row["next_try"]) > now:
                continue
            self._forward(row)

    def _forward(self, row: sqlite3.Row) -> None:
        order = json.loads(row["payload"])
        oid = row["id"]
        unknown = [line["sku"] for line in order["line_items"] if not self.supplier.sells(line["sku"])]
        if unknown:
            self._set(oid, status=NEEDS_HUMAN, note=f"supplier doesn't sell {', '.join(unknown)}")
            self._say(f"order {oid}: supplier doesn't sell {', '.join(unknown)} - nothing sent, needs you")
            return
        attempts = row["attempts"] + 1
        try:
            ref = self.supplier.place_order(oid, order["line_items"], order["shipping_address"])
        except TemporaryError as e:
            if attempts >= self.policy.max_attempts:
                self._set(oid, status=FAILED, attempts=attempts, note=f"gave up after {attempts} tries: {e}")
                self._say(f"order {oid}: supplier still down after {attempts} tries - needs you")
                return
            wait = self.policy.first_wait_minutes * 2 ** (attempts - 1)
            self._set(oid, status=RETRY, attempts=attempts, note=str(e),
                      next_try=(self.clock() + timedelta(minutes=wait)).isoformat())
            self._say(f"order {oid}: supplier down ({e}), try {attempts}, next in {wait} min")
            return
        except PermanentError as e:
            self._set(oid, status=NEEDS_HUMAN, attempts=attempts, note=str(e))
            self._say(f"order {oid}: supplier refused ({e}) - needs you")
            return
        self._set(oid, status=FORWARDED, attempts=attempts, supplier_ref=ref, note=None, next_try=None)
        self._say(f"order {oid} forwarded to supplier as {ref}")

    # -- step 3: tracking back to the shop ----------------------------------
    def collect_tracking(self) -> None:
        for row in self.by_status(FORWARDED):
            number = self.supplier.tracking(row["supplier_ref"])
            if not number:
                continue
            self.shop.fulfill(row["id"], number)
            self._set(row["id"], status=SHIPPED, tracking=number)
            self._say(f"order {row['id']} shipped, tracking {number} sent to the customer")

    def tick(self) -> None:
        """One round of work; run it every minute or two."""
        self.forward_due()
        self.collect_tracking()

    def summary(self) -> dict[str, int]:
        rows = self.db.execute("SELECT status, COUNT(*) AS n FROM orders GROUP BY status").fetchall()
        return {r["status"]: r["n"] for r in rows}
