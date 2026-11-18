"""A busy night, simulated: everything that can go wrong does.

    python -m nightshift.busy_night

No network: a fake supplier and a fake shop behave like the real ones,
including the bad moments.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import tempfile
from datetime import datetime, timedelta

from .orders import OrderDesk, PermanentError, TemporaryError

SECRET = "demo-webhook-secret"


class Clock:
    def __init__(self, start: datetime):
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, minutes: int) -> None:
        self.now += timedelta(minutes=minutes)


class FlakySupplier:
    """Sells the kitchen range, is down from 23:10 to 23:30, ships after ~2 hours."""

    CATALOG = {"TEA-001", "MUG-002", "LAMP-003", "KNIFE-004", "KETTLE-008", "SPICE-009"}

    def __init__(self, clock: Clock):
        self.clock = clock
        self.placed: dict[str, datetime] = {}

    def sells(self, sku: str) -> bool:
        return sku in self.CATALOG

    def place_order(self, order_id, lines, address):
        t = self.clock().time()
        if datetime(2000, 1, 1, 23, 10).time() <= t < datetime(2000, 1, 1, 23, 30).time():
            raise TemporaryError("HTTP 503 from supplier API")
        if not address.get("zip"):
            raise PermanentError("shipping address has no postcode")
        ref = f"SUP-{order_id[-3:]}"
        self.placed[ref] = self.clock()
        return ref

    def tracking(self, ref):
        placed = self.placed.get(ref)
        if placed and self.clock() - placed >= timedelta(hours=2):
            return f"DHL-00340{ref[-3:]}"
        return None


class DemoShop:
    def __init__(self):
        self.fulfilled: dict[str, str] = {}

    def fulfill(self, order_id, tracking):
        self.fulfilled[order_id] = tracking


def signed(order: dict, secret: str = SECRET) -> tuple[bytes, str]:
    body = json.dumps(order).encode()
    sig = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
    return body, sig


def order(n: int, *skus: str, zip_code: str = "10115") -> dict:
    return {"id": 5001000 + n, "line_items": [{"sku": s, "quantity": 1} for s in skus],
            "shipping_address": {"name": "Customer", "zip": zip_code, "country": "DE"}}


def run(db_path: str | None = None) -> OrderDesk:
    clock = Clock(datetime(2026, 11, 18, 22, 50))
    supplier, shop = FlakySupplier(clock), DemoShop()
    desk = OrderDesk(db_path or tempfile.mktemp(suffix=".db"), supplier, shop, SECRET, clock=clock)

    events = {
        0: [order(1, "TEA-001")],
        5: [order(2, "MUG-002", "SPICE-009")],
        10: ["duplicate:2"],
        15: ["forged"],
        25: [order(3, "KNIFE-004")],                       # lands while supplier is down
        30: [order(4, "BOARD-006")],                       # supplier doesn't sell it
        35: [order(5, "KETTLE-008", zip_code="")],         # broken address
        38: [order(6, "LAMP-003")],                        # also during the outage
    }
    sent: dict[int, dict] = {}
    for minute in range(0, 300, 2):
        for ev in events.get(minute, []) + events.get(minute - 1, []):
            if ev == "forged":
                body, _ = signed(order(99, "TEA-001"))
                desk.receive(body, "bm90LWEtcmVhbC1zaWduYXR1cmU=")
            elif isinstance(ev, str) and ev.startswith("duplicate:"):
                body, sig = signed(sent[int(ev.split(":")[1])])
                desk.receive(body, sig)
            else:
                n = ev["id"] - 5001000
                sent[n] = ev
                desk.receive(*signed(ev))
        desk.tick()
        clock.advance(2)
    return desk


def main() -> int:
    desk = run()
    print("NightShift Level 2 - a busy night\n")
    print("\n".join(desk.log))
    print("\nBy morning:", ", ".join(f"{n} {s}" for s, n in sorted(desk.summary().items())))
    for row in desk.by_status("needs_human", "failed"):
        print(f"  needs you: order {row['id']} - {row['note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
