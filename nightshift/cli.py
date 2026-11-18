"""Run one night shift.

    python -m nightshift.cli --feed sample/supplier_feed.csv --shop sample/shop.json          # dry run
    python -m nightshift.cli --feed sample/supplier_feed.csv --shop sample/shop.json --apply  # act
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path

from .feed import load_feed
from .report import morning_report, send_telegram, telegram_summary
from .rules import Rules, decide_all
from .shops import MockShop


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="NightShift - supplier sync for small online shops")
    p.add_argument("--feed", required=True, help="supplier CSV (sku, cost, stock)")
    p.add_argument("--shop", help="demo shop JSON file (MockShop)")
    p.add_argument("--shopify", action="store_true", help="use a real Shopify store (env SHOPIFY_STORE, SHOPIFY_TOKEN, SHOPIFY_LOCATION_ID) - experimental")
    p.add_argument("--apply", action="store_true", help="actually change the shop (default: dry run)")
    p.add_argument("--margin", type=float, default=Rules.margin)
    p.add_argument("--buffer", type=int, default=Rules.safety_buffer)
    p.add_argument("--max-jump", type=float, default=Rules.max_price_jump)
    p.add_argument("--reports", default="reports", help="folder for morning reports")
    args = p.parse_args(argv)

    if args.shopify:
        from .shops import ShopifyShop

        shop = ShopifyShop(os.environ["SHOPIFY_STORE"], os.environ["SHOPIFY_TOKEN"], os.environ["SHOPIFY_LOCATION_ID"])
    elif args.shop:
        shop = MockShop(args.shop)
    else:
        p.error("give --shop for the demo or --shopify for a real store")

    rules = Rules(margin=args.margin, safety_buffer=args.buffer, max_price_jump=args.max_jump)
    feed, bad = load_feed(args.feed)
    decisions = decide_all(shop.items(), feed, rules, broken_skus={b.sku for b in bad})
    applied = 0
    if args.apply:
        applied = shop.apply(decisions)

    now = datetime.now()
    report = morning_report(decisions, bad, applied=args.apply, when=now)
    out = Path(args.reports)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"morning-report-{now:%Y-%m-%d}.md"
    path.write_text(report, encoding="utf-8")

    print(report)
    if args.apply:
        print(f"Applied {applied} change(s) to the shop.")
    print(f"Report saved to {path}")
    if send_telegram(telegram_summary(decisions, bad)):
        print("Telegram summary sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
