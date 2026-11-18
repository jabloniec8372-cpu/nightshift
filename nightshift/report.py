"""The morning report: what the night shift did, in words a shop owner reads with coffee."""

from __future__ import annotations

import os
from collections import Counter
from datetime import datetime

from .feed import BadRow
from .rules import Action, Decision

HEADLINES = {
    Action.SOLD_OUT: "Taken off sale (supplier ran low)",
    Action.RESTOCK: "Back on sale",
    Action.HOLD: "Waiting for you (price jump too big)",
    Action.TO_CHECK: "Please check (not in supplier feed)",
    Action.UPDATE: "Quietly corrected",
}


def morning_report(decisions: list[Decision], bad_rows: list[BadRow], applied: bool, when: datetime | None = None) -> str:
    when = when or datetime.now()
    counts = Counter(d.action for d in decisions)
    needs_you = counts[Action.HOLD] + counts[Action.TO_CHECK] + len(bad_rows)

    lines = [f"# NightShift morning report - {when:%A %d %B %Y, %H:%M}", ""]
    if needs_you == 0:
        lines.append("Quiet night. Everything matches the supplier - nothing needs you today.")
    else:
        lines.append(f"**{needs_you} thing(s) need you.** Everything else was handled.")
    if not applied:
        lines.append("")
        lines.append("_Dry run: nothing was changed in the shop. Run with --apply to let NightShift act._")
    lines.append("")
    lines.append(f"Checked {len(decisions)} products: " + ", ".join(
        f"{counts[a]} {a.value.replace('_', ' ')}" for a in Action if counts[a]))

    for action in (Action.HOLD, Action.TO_CHECK, Action.SOLD_OUT, Action.RESTOCK, Action.UPDATE):
        group = [d for d in decisions if d.action == action]
        if not group:
            continue
        lines += ["", f"## {HEADLINES[action]} ({len(group)})", ""]
        for d in group:
            change = []
            if d.new_price != d.old_price:
                change.append(f"price {d.old_price:.2f} -> {d.new_price:.2f}")
            if d.new_stock != d.old_stock:
                change.append(f"stock {d.old_stock} -> {d.new_stock}")
            detail = "; ".join(change + d.notes) or "no change"
            lines.append(f"- **{d.title}** (`{d.sku}`): {detail}")

    if bad_rows:
        lines += ["", f"## Broken rows in the supplier file ({len(bad_rows)})", ""]
        lines += [f"- line {b.line} `{b.sku or '?'}`: {b.reason} - skipped, not guessed" for b in bad_rows]
    return "\n".join(lines) + "\n"


def telegram_summary(decisions: list[Decision], bad_rows: list[BadRow]) -> str:
    counts = Counter(d.action for d in decisions)
    parts = ["NightShift: night done."]
    if counts[Action.SOLD_OUT]:
        parts.append(f"{counts[Action.SOLD_OUT]} taken off sale")
    if counts[Action.RESTOCK]:
        parts.append(f"{counts[Action.RESTOCK]} back on sale")
    waiting = counts[Action.HOLD] + counts[Action.TO_CHECK] + len(bad_rows)
    parts.append(f"{waiting} need you" if waiting else "nothing needs you")
    return " | ".join(parts)


def send_telegram(text: str) -> bool:  # pragma: no cover - network
    token, chat = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return False
    import requests

    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat, "text": text}, timeout=15)
    return r.ok
