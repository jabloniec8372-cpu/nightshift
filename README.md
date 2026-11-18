# NightShift

**The supplier sync that works the night shift, so a small shop owner doesn't have to.**

Lotte runs a small online kitchen shop. She doesn't keep a warehouse: her supplier ships every order straight to the customer. It works beautifully, until the night the supplier sells out of the sage mug she still shows as "12 in stock". By morning she has three orders she can't fill, three refunds to send and one angry review.

NightShift is the colleague who would have caught that. Every night it reads the supplier's file, compares it with the shop, quietly fixes what is safe to fix, and leaves a short, honest morning report about the rest.

> This is a portfolio demo. It runs on a demo shop (a JSON file) and a sample supplier file. The Shopify connection is included but has not yet been run against a live store.

## What it does in one night

| Situation | What NightShift does |
|---|---|
| Supplier is almost out | Takes the product off sale before anyone buys "air" |
| Supplier has it again | Puts it back on sale |
| Supplier cost changed a little | Recalculates the price (cost + margin, ending in .99) |
| Supplier cost jumped a lot | **Does not touch the price.** Holds it and asks you |
| Product isn't in the supplier file | Leaves it alone and asks you to check |
| A row in the supplier file is broken | Skips it and says so, instead of guessing a zero |

The full example is in [`docs/example-morning-report.md`](docs/example-morning-report.md). The short version that lands on Telegram looks like this:

```
NightShift: night done. | 1 taken off sale | 1 back on sale | 4 need you
```

## Why it is built this way

Most sync tools are proud of how much they change. NightShift is proud of what it refuses to change:

- **A big price jump waits for a human.** If a supplier typo turns 30.00 into 300.00, your shop doesn't follow.
- **Silence is not zero.** A product missing from the feed, or a broken row, is reported, never treated as "sold out" or "free".
- **A safety buffer.** It keeps a couple of units back at the supplier, because supplier stock numbers are always a little optimistic.
- **Dry run by default.** Nothing in the shop changes until you add `--apply`.

## Try it

```bash
pip install -r requirements.txt
cp sample/shop.json /tmp/shop.json

# look first (dry run)
python -m nightshift.cli --feed sample/supplier_feed.csv --shop /tmp/shop.json

# then let it act
python -m nightshift.cli --feed sample/supplier_feed.csv --shop /tmp/shop.json --apply
```

Run it twice: the second night only the things that really need a person are left.

Rules you can change: `--margin 0.35`, `--buffer 2`, `--max-jump 0.30`.

Telegram summary (optional): set `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID`.

## Supplier files as they really are

Suppliers rarely send clean English CSVs. NightShift reads comma, semicolon or tab separated files, German and Polish column names (`Artikelnummer`, `EK`, `Bestand`, `stan`, ...) and decimal commas (`18,50`). The sample file is deliberately written that way, including one broken row.

## Connecting a real shop

- **Demo:** `MockShop` keeps the shop in a JSON file.
- **Shopify (experimental):** `ShopifyShop` uses the Admin GraphQL API (`productVariants`, `productVariantsBulkUpdate`, `inventorySetQuantities`). Set `SHOPIFY_STORE`, `SHOPIFY_TOKEN`, `SHOPIFY_LOCATION_ID` and run with `--shopify`. Written to Shopify's documentation; test on a development store first.
- WooCommerce or Amazon would be another small adapter with the same two methods: `items()` and `apply()`.

## Running it every night

Any scheduler works: cron on a small server, Windows Task Scheduler, or a scheduled GitHub Action.

## Level 2: forwarding orders, live

The night sync compares two files. Real dropshipping also needs every new order passed to the supplier and the tracking number passed back to the customer. That is where things really break, so Level 2 is built around the bad moments:

| What goes wrong | What NightShift does |
|---|---|
| The shop sends the same order twice (webhooks are "at least once") | Recognises it and ignores the copy, so the customer isn't shipped two kettles |
| Someone posts a fake order to the webhook | Checks Shopify's HMAC signature and rejects it |
| Supplier API is down | Retries with growing pauses (2, 4, 8 ... min), gives up after 5 tries and tells you |
| Order has something this supplier doesn't sell | Sends nothing, flags it for you |
| Address is broken | Supplier refuses, NightShift stops retrying and flags it |
| The program restarts in the middle of the night | Every order lives in SQLite with its status, nothing is lost |

See it on a simulated busy night (no network needed):

```bash
python -m nightshift.busy_night
```

```
23:00 order 5001002 arrived again - duplicate ignored
23:06 rejected a webhook with a wrong signature (not from the shop)
23:16 order 5001003: supplier down (HTTP 503 from supplier API), try 1, next in 2 min
23:20 order 5001004: supplier doesn't sell BOARD-006 - nothing sent, needs you
23:30 order 5001003 forwarded to supplier as SUP-003
01:30 order 5001003 shipped, tracking DHL-00340003 sent to the customer

By morning: 2 needs_human, 4 shipped
```

## Tests

```bash
python -m pytest -q
```

---

Built by Tomasz Dembinski, Python automation and Telegram bots. Need NightShift for your own supplier and shop? It's usually a few days of work: a new feed format, your shop's API and your own rules.
