import sqlite3
import unittest

from backend.chat_features import (
    build_node_lookup,
    build_trace_response,
    detect_trace_request,
    extract_references,
)
from backend.graph import build_graph
from backend.ingest import DB_PATH


class ChatFeatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph = build_graph()
        cls.node_lookup = build_node_lookup(cls.graph)
        cls.conn = sqlite3.connect(DB_PATH)
        cls.conn.row_factory = sqlite3.Row

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_build_node_lookup_contains_graph_node(self):
        node_id, attrs = next(iter(self.graph.nodes(data=True)))
        self.assertIn(node_id, self.node_lookup)
        self.assertEqual(self.node_lookup[node_id]["type"], attrs.get("type"))

    def test_extract_references_maps_known_entities(self):
        row = self.conn.execute(
            """
            SELECT soh.salesOrder, soh.soldToParty, soi.material
            FROM sales_order_headers soh
            JOIN sales_order_items soi
              ON soi.salesOrder = soh.salesOrder
            WHERE soh.soldToParty IS NOT NULL
              AND soi.material IS NOT NULL
            LIMIT 1
            """
        ).fetchone()
        self.assertIsNotNone(row)
        references = extract_references([dict(row)], self.node_lookup)
        reference_ids = {reference["id"] for reference in references}
        self.assertIn(f"SO_{row['salesOrder']}", reference_ids)
        self.assertIn(f"CUST_{row['soldToParty']}", reference_ids)
        self.assertIn(f"PROD_{row['material']}", reference_ids)

    def test_detect_trace_request_identifies_billing_document(self):
        trace_request = detect_trace_request("trace the full flow of billing document 90504259")
        self.assertEqual(
            trace_request,
            {
                "entityType": "Billing Document",
                "field": "billingDocument",
                "value": "90504259",
            },
        )

    def test_build_trace_response_returns_steps_for_existing_billing_document(self):
        row = self.conn.execute(
            "SELECT billingDocument FROM billing_document_headers ORDER BY billingDocument LIMIT 1"
        ).fetchone()
        self.assertIsNotNone(row)
        response = build_trace_response(
            {
                "entityType": "Billing Document",
                "field": "billingDocument",
                "value": row["billingDocument"],
            },
            self.node_lookup,
        )
        self.assertIsNone(response["error"])
        self.assertIsNotNone(response["trace"])
        self.assertEqual(response["trace"]["requestedValue"], row["billingDocument"])
        self.assertGreater(len(response["trace"]["steps"]), 0)
        self.assertTrue(any(step["status"] == "found" for step in response["trace"]["steps"]))
