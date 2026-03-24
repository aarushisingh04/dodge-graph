import unittest

from backend.query_engine import run_sql, validate_sql


class QueryEngineTests(unittest.TestCase):
    def test_validate_sql_accepts_select(self):
        self.assertEqual(validate_sql("SELECT 1;"), "SELECT 1")

    def test_validate_sql_rejects_empty_query(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            validate_sql("   ")

    def test_validate_sql_rejects_multiple_statements(self):
        with self.assertRaisesRegex(ValueError, "single query"):
            validate_sql("SELECT 1; SELECT 2")

    def test_validate_sql_rejects_mutation(self):
        with self.assertRaisesRegex(ValueError, "Only SELECT queries are allowed"):
            validate_sql("DELETE FROM sales_order_headers")

    def test_run_sql_returns_rows(self):
        rows = run_sql("SELECT salesOrder FROM sales_order_headers LIMIT 2")
        self.assertLessEqual(len(rows), 2)
        self.assertTrue(all("salesOrder" in row for row in rows))
