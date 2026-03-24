import os
import sqlite3

import networkx as nx


DB_PATH = os.path.join(os.path.dirname(__file__), "o2c.db")


def build_graph() -> nx.DiGraph:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    graph = nx.DiGraph()

    def query(sql: str, params=()):
        return [dict(row) for row in conn.execute(sql, params).fetchall()]

    for row in query("SELECT * FROM sales_order_headers"):
        graph.add_node(
            f"SO_{row['salesOrder']}",
            type="SalesOrder",
            label=row["salesOrder"],
            **{key: value for key, value in row.items() if value},
        )

    for row in query("SELECT * FROM sales_order_items"):
        graph.add_node(
            f"SOI_{row['salesOrder']}_{row['salesOrderItem']}",
            type="SalesOrderItem",
            label=f"Item {row['salesOrderItem']}",
            **{key: value for key, value in row.items() if value},
        )

    for row in query("SELECT * FROM outbound_delivery_headers"):
        graph.add_node(
            f"DEL_{row['deliveryDocument']}",
            type="Delivery",
            label=row["deliveryDocument"],
            **{key: value for key, value in row.items() if value},
        )

    for row in query("SELECT * FROM outbound_delivery_items"):
        graph.add_node(
            f"DELI_{row['deliveryDocument']}_{row['deliveryDocumentItem']}",
            type="DeliveryItem",
            label=f"DI {row['deliveryDocumentItem']}",
            **{key: value for key, value in row.items() if value},
        )

    for row in query("SELECT * FROM billing_document_headers"):
        graph.add_node(
            f"BILL_{row['billingDocument']}",
            type="BillingDoc",
            label=row["billingDocument"],
            **{key: value for key, value in row.items() if value},
        )

    for row in query("SELECT * FROM billing_document_items"):
        graph.add_node(
            f"BILLI_{row['billingDocument']}_{row['billingDocumentItem']}",
            type="BillingItem",
            label=f"BI {row['billingDocumentItem']}",
            **{key: value for key, value in row.items() if value},
        )

    seen_journal_entries = set()
    for row in query("SELECT * FROM journal_entries"):
        node_id = f"JE_{row['accountingDocument']}"
        if node_id in seen_journal_entries:
            continue
        seen_journal_entries.add(node_id)
        graph.add_node(
            node_id,
            type="JournalEntry",
            label=row["accountingDocument"],
            **{key: value for key, value in row.items() if value},
        )

    for row in query("SELECT * FROM payments"):
        graph.add_node(
            f"PAY_{row['accountingDocument']}_{row['accountingDocumentItem']}",
            type="Payment",
            label=f"Payment {row['accountingDocumentItem']}",
            **{key: value for key, value in row.items() if value},
        )

    for row in query(
        """
        SELECT bp.*, bpa.cityName, bpa.country, bpa.region
        FROM business_partners bp
        LEFT JOIN business_partner_addresses bpa
          ON bp.businessPartner = bpa.businessPartner
        """
    ):
        graph.add_node(
            f"CUST_{row['businessPartner']}",
            type="Customer",
            label=row.get("businessPartnerFullName") or row["businessPartner"],
            **{key: value for key, value in row.items() if value},
        )

    for row in query(
        """
        SELECT p.*, pd.productDescription
        FROM products p
        LEFT JOIN product_descriptions pd
          ON p.product = pd.product AND pd.language = 'EN'
        """
    ):
        graph.add_node(
            f"PROD_{row['product']}",
            type="Product",
            label=row.get("productDescription") or row["product"],
            **{key: value for key, value in row.items() if value},
        )

    for row in query("SELECT * FROM plants"):
        graph.add_node(
            f"PLANT_{row['plant']}",
            type="Plant",
            label=row.get("plantName") or row["plant"],
            **{key: value for key, value in row.items() if value},
        )

    for row in query("SELECT salesOrder, salesOrderItem FROM sales_order_items"):
        src = f"SO_{row['salesOrder']}"
        dst = f"SOI_{row['salesOrder']}_{row['salesOrderItem']}"
        if graph.has_node(src) and graph.has_node(dst):
            graph.add_edge(src, dst, relation="HAS_ITEM")

    for row in query(
        "SELECT salesOrder, soldToParty FROM sales_order_headers WHERE soldToParty IS NOT NULL"
    ):
        src = f"SO_{row['salesOrder']}"
        dst = f"CUST_{row['soldToParty']}"
        if graph.has_node(src) and graph.has_node(dst):
            graph.add_edge(src, dst, relation="SOLD_TO")

    for row in query(
        "SELECT salesOrder, salesOrderItem, material FROM sales_order_items WHERE material IS NOT NULL"
    ):
        src = f"SOI_{row['salesOrder']}_{row['salesOrderItem']}"
        dst = f"PROD_{row['material']}"
        if graph.has_node(src) and graph.has_node(dst):
            graph.add_edge(src, dst, relation="USES_PRODUCT")

    for row in query("SELECT deliveryDocument, deliveryDocumentItem FROM outbound_delivery_items"):
        src = f"DEL_{row['deliveryDocument']}"
        dst = f"DELI_{row['deliveryDocument']}_{row['deliveryDocumentItem']}"
        if graph.has_node(src) and graph.has_node(dst):
            graph.add_edge(src, dst, relation="HAS_ITEM")

    for row in query(
        """
        SELECT deliveryDocument, deliveryDocumentItem, referenceSdDocument
        FROM outbound_delivery_items
        WHERE referenceSdDocument IS NOT NULL
        """
    ):
        src = f"DELI_{row['deliveryDocument']}_{row['deliveryDocumentItem']}"
        dst = f"SO_{row['referenceSdDocument']}"
        if graph.has_node(src) and graph.has_node(dst):
            graph.add_edge(src, dst, relation="FULFILLS")

    for row in query(
        """
        SELECT deliveryDocument, deliveryDocumentItem, plant
        FROM outbound_delivery_items
        WHERE plant IS NOT NULL
        """
    ):
        src = f"DELI_{row['deliveryDocument']}_{row['deliveryDocumentItem']}"
        dst = f"PLANT_{row['plant']}"
        if graph.has_node(src) and graph.has_node(dst):
            graph.add_edge(src, dst, relation="SHIPS_FROM")

    for row in query(
        """
        SELECT DISTINCT pp.product, pp.plant
        FROM product_plants pp
        WHERE pp.product IS NOT NULL
          AND pp.plant IS NOT NULL
          AND pp.plant IN (
              SELECT DISTINCT plant
              FROM outbound_delivery_items
              WHERE plant IS NOT NULL
          )
        """
    ):
        src = f"PROD_{row['product']}"
        dst = f"PLANT_{row['plant']}"
        if graph.has_node(src) and graph.has_node(dst):
            graph.add_edge(src, dst, relation="STORED_AT")

    for row in query("SELECT billingDocument, billingDocumentItem FROM billing_document_items"):
        src = f"BILL_{row['billingDocument']}"
        dst = f"BILLI_{row['billingDocument']}_{row['billingDocumentItem']}"
        if graph.has_node(src) and graph.has_node(dst):
            graph.add_edge(src, dst, relation="HAS_ITEM")

    for row in query(
        """
        SELECT billingDocument, billingDocumentItem, referenceSdDocument
        FROM billing_document_items
        WHERE referenceSdDocument IS NOT NULL
        """
    ):
        src = f"BILLI_{row['billingDocument']}_{row['billingDocumentItem']}"
        dst = f"DEL_{row['referenceSdDocument']}"
        if graph.has_node(src) and graph.has_node(dst):
            graph.add_edge(src, dst, relation="FROM_DELIVERY")

    for row in query(
        """
        SELECT accountingDocument, referenceDocument
        FROM journal_entries
        WHERE referenceDocument IS NOT NULL
        """
    ):
        src = f"BILL_{row['referenceDocument']}"
        dst = f"JE_{row['accountingDocument']}"
        if graph.has_node(src) and graph.has_node(dst):
            graph.add_edge(src, dst, relation="POSTED_TO")

    for row in query(
        "SELECT billingDocument, soldToParty FROM billing_document_headers WHERE soldToParty IS NOT NULL"
    ):
        src = f"BILL_{row['billingDocument']}"
        dst = f"CUST_{row['soldToParty']}"
        if graph.has_node(src) and graph.has_node(dst):
            graph.add_edge(src, dst, relation="BILLED_TO")

    for row in query("SELECT accountingDocument, accountingDocumentItem FROM payments"):
        src = f"JE_{row['accountingDocument']}"
        dst = f"PAY_{row['accountingDocument']}_{row['accountingDocumentItem']}"
        if graph.has_node(src) and graph.has_node(dst):
            graph.add_edge(src, dst, relation="SETTLED_BY")

    conn.close()
    print(f"Graph built: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
    return graph


def graph_to_json(graph: nx.DiGraph) -> dict:
    type_colors = {
        "SalesOrder": "#2563eb",
        "SalesOrderItem": "#7dd3fc",
        "Delivery": "#16a34a",
        "DeliveryItem": "#86efac",
        "BillingDoc": "#111827",
        "BillingItem": "#94a3b8",
        "JournalEntry": "#f97316",
        "Payment": "#facc15",
        "Customer": "#dc2626",
        "Product": "#7c3aed",
        "Plant": "#0f766e",
    }

    nodes = []
    for node_id, attrs in graph.nodes(data=True):
        node_type = attrs.get("type", "Unknown")
        nodes.append(
            {
                "id": node_id,
                "type": node_type,
                "label": attrs.get("label", node_id),
                "color": type_colors.get(node_type, "#888780"),
                "properties": {
                    key: value
                    for key, value in attrs.items()
                    if key not in ("type", "label") and value
                },
            }
        )

    links = []
    for source, target, attrs in graph.edges(data=True):
        links.append(
            {
                "source": source,
                "target": target,
                "relation": attrs.get("relation", "RELATED"),
            }
        )

    return {"nodes": nodes, "links": links}
