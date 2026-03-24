import sqlite3

from ingest import DB_PATH


QUERIES = {
    "delivered_not_billed": """
        SELECT DISTINCT
            odi.referenceSdDocument AS salesOrder,
            odi.deliveryDocument
        FROM outbound_delivery_items odi
        LEFT JOIN billing_document_items bdi
          ON bdi.referenceSdDocument = odi.deliveryDocument
        WHERE odi.referenceSdDocument IS NOT NULL
          AND bdi.billingDocument IS NULL
        ORDER BY odi.referenceSdDocument
        LIMIT 3
    """,
    "billed_without_delivery": """
        SELECT DISTINCT
            bdi.billingDocument,
            bdi.referenceSdDocument AS referencedDelivery
        FROM billing_document_items bdi
        LEFT JOIN outbound_delivery_headers odh
          ON odh.deliveryDocument = bdi.referenceSdDocument
        WHERE bdi.referenceSdDocument IS NOT NULL
          AND odh.deliveryDocument IS NULL
        ORDER BY bdi.billingDocument
        LIMIT 3
    """,
    "billing_trace_example": """
        SELECT DISTINCT
            bdh.billingDocument,
            bdi.referenceSdDocument AS deliveryDocument,
            odi.referenceSdDocument AS salesOrder,
            bdh.accountingDocument
        FROM billing_document_headers bdh
        LEFT JOIN billing_document_items bdi
          ON bdi.billingDocument = bdh.billingDocument
        LEFT JOIN outbound_delivery_items odi
          ON odi.deliveryDocument = bdi.referenceSdDocument
        WHERE bdh.billingDocument = '90504259'
    """,
}


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        for name, sql in QUERIES.items():
            rows = [dict(row) for row in conn.execute(sql).fetchall()]
            print(name)
            if not rows:
                print("  no rows")
            for row in rows:
                print(f"  {row}")
            print()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
