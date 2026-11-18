from datetime import datetime

from nightshift.busy_night import SECRET, Clock, DemoShop, FlakySupplier, order, run, signed
from nightshift.orders import FAILED, FORWARDED, NEEDS_HUMAN, RETRY, OrderDesk, Policy, TemporaryError


def desk_at(tmp_path, hour=22, minute=0, supplier=None, policy=Policy()):
    clock = Clock(datetime(2026, 11, 18, hour, minute))
    sup = supplier or FlakySupplier(clock)
    return OrderDesk(str(tmp_path / "o.db"), sup, DemoShop(), SECRET, policy=policy, clock=clock), clock


def test_duplicate_webhook_is_ignored(tmp_path):
    desk, _ = desk_at(tmp_path)
    body, sig = signed(order(1, "TEA-001"))
    assert desk.receive(body, sig) == "accepted"
    assert desk.receive(body, sig) == "duplicate"


def test_forged_webhook_is_rejected(tmp_path):
    desk, _ = desk_at(tmp_path)
    body, _ = signed(order(1, "TEA-001"))
    _, wrong = signed(order(1, "TEA-001"), secret="someone-else")
    assert desk.receive(body, wrong) == "rejected"
    assert desk.status("5001001") is None


def test_supplier_outage_retries_then_succeeds(tmp_path):
    desk, clock = desk_at(tmp_path, 23, 12)                  # supplier is down until 23:30
    desk.receive(*signed(order(3, "KNIFE-004")))
    desk.tick()
    assert desk.status("5001003")["status"] == RETRY
    clock.advance(20)
    desk.tick()
    assert desk.status("5001003")["status"] == FORWARDED


def test_gives_up_after_max_attempts(tmp_path):
    class Dead(FlakySupplier):
        def place_order(self, *a):
            raise TemporaryError("timeout")

    clock = Clock(datetime(2026, 11, 18, 22, 0))
    desk = OrderDesk(str(tmp_path / "o.db"), Dead(clock), DemoShop(), SECRET, Policy(max_attempts=3), clock=clock)
    desk.receive(*signed(order(1, "TEA-001")))
    for _ in range(30):
        desk.tick()
        clock.advance(2)
    row = desk.status("5001001")
    assert row["status"] == FAILED and row["attempts"] == 3


def test_unknown_sku_is_never_sent(tmp_path):
    desk, _ = desk_at(tmp_path)
    desk.receive(*signed(order(4, "BOARD-006")))
    desk.tick()
    assert desk.status("5001004")["status"] == NEEDS_HUMAN
    assert desk.supplier.placed == {}


def test_restart_loses_nothing(tmp_path):
    desk, clock = desk_at(tmp_path, 23, 12)
    desk.receive(*signed(order(3, "KNIFE-004")))
    desk.tick()                                              # RETRY, waiting
    clock.advance(30)
    reborn = OrderDesk(str(tmp_path / "o.db"), FlakySupplier(clock), DemoShop(), SECRET, clock=clock)
    reborn.tick()
    assert reborn.status("5001003")["status"] == FORWARDED


def test_busy_night_ends_with_only_human_decisions_left(tmp_path):
    desk = run(str(tmp_path / "night.db"))
    assert desk.summary() == {"needs_human": 2, "shipped": 4}
