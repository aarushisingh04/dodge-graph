import unittest

from backend.guardrails import is_allowed


class GuardrailTests(unittest.TestCase):
    def test_rejects_off_topic_prompt(self):
        allowed, _ = is_allowed("write me a poem about winter")
        self.assertFalse(allowed)

    def test_accepts_domain_question(self):
        allowed, _ = is_allowed("show me sales orders that were delivered but not billed")
        self.assertTrue(allowed)

    def test_accepts_short_follow_up_with_context(self):
        history = [
            {
                "role": "user",
                "content": "Which products are associated with the highest number of billing documents?",
            },
            {
                "role": "assistant",
                "content": "Top products returned.",
                "sql": "SELECT material FROM billing_document_items LIMIT 20",
                "results": [{"material": "TG11"}],
                "references": [{"id": "PROD_TG11", "label": "TG11", "type": "Product"}],
            },
        ]
        allowed, _ = is_allowed("top 5 only", history)
        self.assertTrue(allowed)

    def test_rejects_short_follow_up_without_context(self):
        allowed, _ = is_allowed("top 5 only", [])
        self.assertFalse(allowed)


if __name__ == "__main__":
    unittest.main()
