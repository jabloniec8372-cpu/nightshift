# NightShift morning report - example night

**4 thing(s) need you.** Everything else was handled.

_Dry run: nothing was changed in the shop. Run with --apply to let NightShift act._

Checked 10 products: 2 ok, 3 update, 1 sold out, 1 restock, 1 hold, 2 to check

## Waiting for you (price jump too big) (1)

- **Santoku knife 18 cm** (`KNIFE-004`): stock 14 -> 23; price would move 26.99 -> 40.99 (+52%); held for a human

## Please check (not in supplier feed) (2)

- **Olive wood board** (`BOARD-006`): not in the supplier feed - left untouched, please check
- **Linen tea towel** (`TOWEL-007`): supplier row is broken - left untouched rather than guessed

## Taken off sale (supplier ran low) (1)

- **Stoneware mug, sage** (`MUG-002`): stock 12 -> 0; supplier has only 1; set to 0 so nobody buys air

## Back on sale (1)

- **Kitchen pendant lamp** (`LAMP-003`): stock 0 -> 13; supplier has 15 again; back on sale

## Quietly corrected (3)

- **Matcha starter set** (`TEA-001`): stock 20 -> 38
- **Gooseneck kettle** (`KETTLE-008`): price 27.99 -> 29.99; stock 9 -> 7
- **Smoked paprika tin** (`SPICE-009`): price 4.49 -> 4.99; stock 30 -> 50

## Broken rows in the supplier file (1)

- line 7 `TOWEL-007`: cost or stock is not a number - skipped, not guessed
