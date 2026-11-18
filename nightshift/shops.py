"""Where the shop lives.

MockShop keeps the shop in a JSON file - that is what the demo runs on.
ShopifyShop talks to the Shopify Admin GraphQL API. It is written against
Shopify's documentation but has NOT yet been run against a live store, so the
CLI only uses it when you ask for it explicitly.
"""

from __future__ import annotations

import json
from pathlib import Path

from .rules import Decision, ShopItem


class MockShop:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.data = json.loads(self.path.read_text(encoding="utf-8"))

    def items(self) -> list[ShopItem]:
        return [ShopItem(p["sku"], p["title"], float(p["price"]), int(p["stock"])) for p in self.data["products"]]

    def apply(self, decisions: list[Decision]) -> int:
        by_sku = {d.sku: d for d in decisions if d.changes_shop}
        for p in self.data["products"]:
            d = by_sku.get(p["sku"])
            if d:
                p["price"], p["stock"] = d.new_price, d.new_stock
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return len(by_sku)


class ShopifyShop:  # pragma: no cover - needs a real store
    API_VERSION = "2025-10"

    def __init__(self, store: str, token: str, location_id: str):
        import requests

        self._requests = requests
        self.url = f"https://{store}/admin/api/{self.API_VERSION}/graphql.json"
        self.headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
        self.location_id = location_id
        self._variants: dict[str, dict] = {}

    def _gql(self, query: str, variables: dict | None = None) -> dict:
        r = self._requests.post(self.url, headers=self.headers, json={"query": query, "variables": variables or {}}, timeout=30)
        r.raise_for_status()
        body = r.json()
        if body.get("errors"):
            raise RuntimeError(body["errors"])
        return body["data"]

    def items(self) -> list[ShopItem]:
        query = """
        query($cursor: String) {
          productVariants(first: 100, after: $cursor) {
            pageInfo { hasNextPage endCursor }
            nodes { id sku price inventoryQuantity displayName product { id } inventoryItem { id } }
          }
        }"""
        out, cursor = [], None
        while True:
            page = self._gql(query, {"cursor": cursor})["productVariants"]
            for v in page["nodes"]:
                if not v["sku"]:
                    continue
                self._variants[v["sku"]] = v
                out.append(ShopItem(v["sku"], v["displayName"], float(v["price"]), int(v["inventoryQuantity"] or 0)))
            if not page["pageInfo"]["hasNextPage"]:
                return out
            cursor = page["pageInfo"]["endCursor"]

    def apply(self, decisions: list[Decision]) -> int:
        changed = 0
        for d in decisions:
            if not d.changes_shop:
                continue
            v = self._variants[d.sku]
            if d.new_price != d.old_price:
                self._gql(
                    """mutation($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
                      productVariantsBulkUpdate(productId: $productId, variants: $variants) { userErrors { message } }
                    }""",
                    {"productId": v["product"]["id"], "variants": [{"id": v["id"], "price": f"{d.new_price:.2f}"}]},
                )
            if d.new_stock != d.old_stock:
                self._gql(
                    """mutation($input: InventorySetQuantitiesInput!) {
                      inventorySetQuantities(input: $input) { userErrors { message } }
                    }""",
                    {"input": {"name": "available", "reason": "correction", "ignoreCompareQuantity": True,
                               "quantities": [{"inventoryItemId": v["inventoryItem"]["id"],
                                               "locationId": self.location_id, "quantity": d.new_stock}]}},
                )
            changed += 1
        return changed
