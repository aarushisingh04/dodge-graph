import os
import sqlite3
import sys

from graph import build_graph
from ingest import DB_PATH


REQUIRED_TABLES = [
    "sales_order_headers",
    "sales_order_items",
    "outbound_delivery_headers",
    "outbound_delivery_items",
    "billing_document_headers",
    "billing_document_items",
    "journal_entries",
    "payments",
    "products",
    "product_plants",
    "plants",
]

REQUIRED_NODE_TYPES = {
    "SalesOrder",
    "Delivery",
    "BillingDoc",
    "JournalEntry",
    "Payment",
    "Customer",
    "Product",
    "Plant",
}

REQUIRED_RELATIONS = {
    "HAS_ITEM",
    "SOLD_TO",
    "USES_PRODUCT",
    "FULFILLS",
    "SHIPS_FROM",
    "FROM_DELIVERY",
    "POSTED_TO",
    "BILLED_TO",
    "SETTLED_BY",
    "STORED_AT",
}


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


def main() -> None:
    if not os.path.exists(DB_PATH):
        fail(f"Database not found at {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    try:
        for table in REQUIRED_TABLES:
            row = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()
            if row is None or row[0] <= 0:
                fail(f"Table {table} is missing or empty")
    finally:
        conn.close()

    graph = build_graph()
    if graph.number_of_nodes() <= 0 or graph.number_of_edges() <= 0:
        fail("Graph is empty")

    node_types = {attrs.get("type") for _, attrs in graph.nodes(data=True)}
    missing_types = sorted(REQUIRED_NODE_TYPES - node_types)
    if missing_types:
        fail(f"Missing node types: {', '.join(missing_types)}")

    relations = {attrs.get("relation") for _, _, attrs in graph.edges(data=True)}
    missing_relations = sorted(REQUIRED_RELATIONS - relations)
    if missing_relations:
        fail(f"Missing relations: {', '.join(missing_relations)}")

    stored_at_count = sum(
        1 for _, _, attrs in graph.edges(data=True) if attrs.get("relation") == "STORED_AT"
    )
    print(
        "OK: "
        f"{graph.number_of_nodes()} nodes, "
        f"{graph.number_of_edges()} edges, "
        f"{stored_at_count} STORED_AT edges"
    )


if __name__ == "__main__":
    main()
