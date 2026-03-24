DOMAIN_KEYWORDS = [
    "sales order",
    "delivery",
    "billing",
    "invoice",
    "payment",
    "customer",
    "product",
    "plant",
    "journal",
    "shipment",
    "material",
    "order",
    "dispatch",
    "warehouse",
    "quantity",
    "amount",
    "currency",
    "inr",
    "sap",
    "o2c",
    "outbound",
    "accounts receivable",
    "fiscal",
    "accounting",
    "document",
    "stock",
    "item",
    "schedule",
    "flow",
    "status",
    "cancelled",
    "billed",
    "delivered",
    "pending",
    "incomplete",
]

OFF_TOPIC_PATTERNS = [
    "write a poem",
    "tell me a joke",
    "who is the president",
    "weather",
    "recipe",
    "movie",
    "stock price",
    "sports",
    "news",
    "history of",
    "explain quantum",
    "write code",
    "help me with",
    "what is your name",
    "are you",
    "can you be",
    "creative writing",
    "essay",
]


FOLLOW_UP_PATTERNS = [
    "same",
    "those",
    "them",
    "that one",
    "that customer",
    "that product",
    "that order",
    "those invoices",
    "only",
    "now",
    "what about",
    "top ",
    "bottom ",
    "trace it",
]


def _history_has_o2c_context(history: list[dict] | None) -> bool:
    if not history:
        return False

    for message in reversed(history[-8:]):
        content = str(message.get("content", "")).lower()
        if any(keyword in content for keyword in DOMAIN_KEYWORDS):
            return True

        if message.get("sql") or message.get("references") or message.get("results"):
            return True

    return False


def is_allowed(query: str, history: list[dict] | None = None) -> tuple[bool, str]:
    q = query.lower().strip()

    for pattern in OFF_TOPIC_PATTERNS:
        if pattern in q:
            return (
                False,
            "This system is designed to answer questions related to the provided SAP Order-to-Cash dataset only.",
            )

    if _history_has_o2c_context(history) and any(pattern in q for pattern in FOLLOW_UP_PATTERNS):
        return True, ""

    if not any(keyword in q for keyword in DOMAIN_KEYWORDS):
        return (
            False,
            "This system is designed to answer questions related to the provided SAP Order-to-Cash dataset only. Please ask about sales orders, deliveries, billing, payments, customers, or products.",
        )

    return True, ""
