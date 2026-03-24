import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

from backend.chat_features import build_node_lookup
from backend.graph import build_graph, graph_to_json


BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import main as app_main


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph = build_graph()
        cls.graph_json = graph_to_json(cls.graph)
        cls.node_lookup = build_node_lookup(cls.graph)

    def setUp(self):
        app_main._graph = self.graph
        app_main._graph_json = self.graph_json
        app_main._node_lookup = self.node_lookup

    def test_get_graph_returns_graph_json(self):
        result = app_main.get_graph()
        self.assertIn("nodes", result)
        self.assertIn("links", result)

    def test_get_node_returns_both_directions(self):
        node_id = next(iter(self.graph.nodes))
        result = app_main.get_node(node_id)
        self.assertEqual(result["id"], node_id)
        self.assertIn("properties", result)
        self.assertIn("connections", result)
        for connection in result["connections"]:
            self.assertIn(connection["direction"], {"incoming", "outgoing"})

    def test_get_stats_matches_graph(self):
        result = app_main.get_stats()
        self.assertEqual(result["total_nodes"], self.graph.number_of_nodes())
        self.assertEqual(result["total_edges"], self.graph.number_of_edges())


class ChatEndpointTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph = build_graph()
        cls.graph_json = graph_to_json(cls.graph)
        cls.node_lookup = build_node_lookup(cls.graph)

    def setUp(self):
        app_main._graph = self.graph
        app_main._graph_json = self.graph_json
        app_main._node_lookup = self.node_lookup

    async def test_chat_rejects_off_topic_prompt(self):
        response = await app_main.chat(app_main.ChatRequest(message="write me a poem", history=[]))
        self.assertIn("SAP Order-to-Cash dataset only", response["answer"])
        self.assertEqual(response["results"], [])

    async def test_chat_returns_trace_without_llm_call(self):
        response = await app_main.chat(
            app_main.ChatRequest(message="trace the full flow of billing document 90504259", history=[])
        )
        self.assertIsNotNone(response["trace"])
        self.assertIsNone(response["sql"])
        self.assertEqual(response["error"], None)

    async def test_chat_returns_grounded_answer_for_analytical_query(self):
        with (
            patch.object(
                app_main,
                "generate_sql",
                AsyncMock(return_value={"sql": "SELECT salesOrder FROM sales_order_headers LIMIT 1", "explanation": "Fetch one sales order"}),
            ),
            patch.object(app_main, "generate_answer", AsyncMock(return_value="Found one sales order.")),
        ):
            response = await app_main.chat(
                app_main.ChatRequest(message="show one sales order", history=[])
            )

        self.assertEqual(response["answer"], "Found one sales order.")
        self.assertEqual(response["explanation"], "Fetch one sales order")
        self.assertLessEqual(len(response["results"]), 1)
        self.assertIsNone(response["error"])

    async def test_chat_handles_invalid_generated_sql(self):
        with patch.object(
            app_main,
            "generate_sql",
            AsyncMock(return_value={"sql": "DELETE FROM sales_order_headers", "explanation": "bad"}),
        ):
            response = await app_main.chat(
                app_main.ChatRequest(message="show one sales order", history=[])
            )

        self.assertIn("Query error:", response["answer"])
        self.assertIsNotNone(response["error"])
