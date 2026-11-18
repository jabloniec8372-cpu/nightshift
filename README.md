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

## Tests

```bash
python -m pytest -q
```

---

Built by Tomasz Dembinski, Python automation and Telegram bots. Need NightShift for your own supplier and shop? It's usually a few days of work: a new feed format, your shop's API and your own rules.
