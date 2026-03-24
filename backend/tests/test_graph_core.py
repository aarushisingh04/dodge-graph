import sqlite3
import unittest

from backend.graph import build_graph, graph_to_json
from backend.ingest import DB_PATH


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


RELATION_SAMPLE_QUERIES = {
    "HAS_ITEM": """
        SELECT 'SO_' || salesOrder AS src, 'SOI_' || salesOrder || '_' || salesOrderItem AS dst
        FROM sales_order_items
        LIMIT 1
    """,
    "SOLD_TO": """
        SELECT 'SO_' || salesOrder AS src, 'CUST_' || soldToParty AS dst
        FROM sales_order_headers
        WHERE soldToParty IS NOT NULL
        LIMIT 1
    """,
    "USES_PRODUCT": """
        SELECT 'SOI_' || salesOrder || '_' || salesOrderItem AS src, 'PROD_' || material AS dst
        FROM sales_order_items
        WHERE material IS NOT NULL
        LIMIT 1
    """,
    "FULFILLS": """
        SELECT 'DELI_' || deliveryDocument || '_' || deliveryDocumentItem AS src, 'SO_' || referenceSdDocument AS dst
        FROM outbound_delivery_items
        WHERE referenceSdDocument IS NOT NULL
        LIMIT 1
    """,
    "SHIPS_FROM": """
        SELECT 'DELI_' || deliveryDocument || '_' || deliveryDocumentItem AS src, 'PLANT_' || plant AS dst
        FROM outbound_delivery_items
        WHERE plant IS NOT NULL
        LIMIT 1
    """,
    "STORED_AT": """
        SELECT DISTINCT 'PROD_' || pp.product AS src, 'PLANT_' || pp.plant AS dst
        FROM product_plants pp
        WHERE pp.product IS NOT NULL
          AND pp.plant IS NOT NULL
          AND pp.plant IN (
              SELECT DISTINCT plant
              FROM outbound_delivery_items
              WHERE plant IS NOT NULL
          )
        LIMIT 1
    """,
    "FROM_DELIVERY": """
        SELECT 'BILLI_' || billingDocument || '_' || billingDocumentItem AS src, 'DEL_' || referenceSdDocument AS dst
        FROM billing_document_items
        WHERE referenceSdDocument IS NOT NULL
        LIMIT 1
    """,
    "POSTED_TO": """
        SELECT 'BILL_' || referenceDocument AS src, 'JE_' || accountingDocument AS dst
        FROM journal_entries
        WHERE referenceDocument IS NOT NULL
        LIMIT 1
    """,
    "BILLED_TO": """
        SELECT 'BILL_' || billingDocument AS src, 'CUST_' || soldToParty AS dst
        FROM billing_document_headers
        WHERE soldToParty IS NOT NULL
        LIMIT 1
    """,
    "SETTLED_BY": """
        SELECT 'JE_' || accountingDocument AS src, 'PAY_' || accountingDocument || '_' || accountingDocumentItem AS dst
        FROM payments
        LIMIT 1
    """,
}


class GraphCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph = build_graph()
        cls.graph_json = graph_to_json(cls.graph)
        cls.conn = sqlite3.connect(DB_PATH)
        cls.conn.row_factory = sqlite3.Row

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_graph_contains_required_node_types(self):
        node_types = {attrs.get("type") for _, attrs in self.graph.nodes(data=True)}
        self.assertFalse(REQUIRED_NODE_TYPES - node_types)

    def test_graph_contains_required_relations(self):
        relations = {attrs.get("relation") for _, _, attrs in self.graph.edges(data=True)}
        self.assertFalse(REQUIRED_RELATIONS - relations)

    def test_graph_json_contains_nodes_and_links(self):
        self.assertIn("nodes", self.graph_json)
        self.assertIn("links", self.graph_json)
        self.assertGreater(len(self.graph_json["nodes"]), 0)
        self.assertGreater(len(self.graph_json["links"]), 0)
        sample_node = self.graph_json["nodes"][0]
        self.assertIn("id", sample_node)
        self.assertIn("type", sample_node)
        self.assertIn("label", sample_node)
        self.assertIn("properties", sample_node)
        sample_link = self.graph_json["links"][0]
        self.assertIn("source", sample_link)
        self.assertIn("target", sample_link)
        self.assertIn("relation", sample_link)

    def test_each_relation_has_a_valid_sample_edge(self):
        for relation, sql in RELATION_SAMPLE_QUERIES.items():
            with self.subTest(relation=relation):
                row = self.conn.execute(sql).fetchone()
                self.assertIsNotNone(row, f"No sample row found for relation {relation}")
                src = row["src"]
                dst = row["dst"]
                self.assertTrue(self.graph.has_node(src), f"Missing source node {src}")
                self.assertTrue(self.graph.has_node(dst), f"Missing target node {dst}")
                self.assertTrue(self.graph.has_edge(src, dst), f"Missing edge {src} -> {dst}")
                self.assertEqual(self.graph.edges[src, dst].get("relation"), relation)
