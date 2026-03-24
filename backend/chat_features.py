import re
import sqlite3
from collections import OrderedDict

try:
    from ingest import DB_PATH
except ModuleNotFoundError:  # pragma: no cover - package import fallback
    from backend.ingest import DB_PATH


REFERENCE_PATTERNS = [
    ("SO_", ("salesOrder", "referenceSdDocument"), "Sales Order"),
    ("DEL_", ("deliveryDocument", "delivery", "referencedDelivery"), "Delivery"),
    ("BILL_", ("billingDocument", "referenceDocument"), "Billing Document"),
    ("JE_", ("accountingDocument", "journalEntry"), "Journal Entry"),
    ("CUST_", ("businessPartner", "soldToParty", "customer"), "Customer"),
    ("PROD_", ("product", "material"), "Product"),
    ("PLANT_", ("plant",), "Plant"),
]

TRACE_PATTERNS = [
    ("Billing Document", r"\bbilling document(?: number)?\s+([0-9A-Za-z]+)\b", "billingDocument"),
    ("Billing Document", r"\binvoice(?: number)?\s+([0-9A-Za-z]+)\b", "billingDocument"),
    ("Sales Order", r"\bsales order\s+([0-9A-Za-z]+)\b", "salesOrder"),
    ("Delivery", r"\bdelivery(?: document)?\s+([0-9A-Za-z]+)\b", "deliveryDocument"),
]


def build_node_lookup(graph) -> dict[str, dict]:
    return {
        node_id: {
            "id": node_id,
            "type": attrs.get("type", "Unknown"),
            "label": attrs.get("label", node_id),
        }
        for node_id, attrs in graph.nodes(data=True)
    }


def extract_references(results: list[dict], node_lookup: dict[str, dict]) -> list[dict]:
    references = []
    seen = set()

    for row in results or []:
        for prefix, keys, fallback_type in REFERENCE_PATTERNS:
            value = next((row.get(key) for key in keys if row.get(key)), None)
            if not value:
                continue

            node_id = f"{prefix}{value}"
            if node_id in seen or node_id not in node_lookup:
                continue

            node = node_lookup[node_id]
            references.append(
                {
                    "id": node_id,
                    "value": str(value),
                    "type": _humanize_type(node.get("type") or fallback_type),
                    "label": node.get("label") or str(value),
                }
            )
            seen.add(node_id)

    return references


def detect_trace_request(message: str) -> dict | None:
    if not message:
        return None

    text = message.strip()
    lowered = text.lower()
    if "trace" not in lowered and "full flow" not in lowered and "follow" not in lowered:
        return None

    for entity_type, pattern, field in TRACE_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return {
                "entityType": entity_type,
                "field": field,
                "value": match.group(1),
            }

    generic_id_match = re.search(r"\b([0-9]{6,})\b", text)
    if generic_id_match and ("billing" in lowered or "invoice" in lowered):
        return {
            "entityType": "Billing Document",
            "field": "billingDocument",
            "value": generic_id_match.group(1),
        }

    return None


def build_trace_response(trace_request: dict, node_lookup: dict[str, dict]) -> dict:
    field = trace_request["field"]
    value = trace_request["value"]

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = _fetch_trace_rows(conn, field, value)
    finally:
        conn.close()

    if not rows:
        entity_label = trace_request["entityType"].lower()
        return {
            "answer": f"No traceable {entity_label} matching {value} was found in the dataset.",
            "results": [],
            "references": [],
            "trace": None,
            "sql": None,
            "explanation": None,
            "error": None,
        }

    path = OrderedDict()
    for row in rows:
        for step_name, node_id in [
            ("Sales Order", _maybe_node_id("SO_", row.get("salesOrder"), node_lookup)),
            ("Delivery", _maybe_node_id("DEL_", row.get("deliveryDocument"), node_lookup)),
            ("Billing Document", _maybe_node_id("BILL_", row.get("billingDocument"), node_lookup)),
            ("Journal Entry", _maybe_node_id("JE_", row.get("accountingDocument"), node_lookup)),
            ("Payment", _maybe_node_id("PAY_", _compose_payment_id(row), node_lookup)),
        ]:
            if step_name in path:
                continue
            path[step_name] = _build_trace_step(step_name, node_id, node_lookup)

    trace_steps = list(path.values())
    references = [step["reference"] for step in trace_steps if step["reference"]]
    answer = _summarize_trace(trace_request, trace_steps)

    return {
        "answer": answer,
        "results": rows[:20],
        "references": references,
        "trace": {
            "requestedEntityType": trace_request["entityType"],
            "requestedValue": value,
            "steps": trace_steps,
        },
        "sql": None,
        "explanation": "Deterministic flow trace built from the O2C join chain.",
        "error": None,
    }


def _fetch_trace_rows(conn: sqlite3.Connection, field: str, value: str) -> list[dict]:
    if field == "salesOrder":
        sql = """
            SELECT DISTINCT
                soh.salesOrder,
                odh.deliveryDocument,
                bdh.billingDocument,
                je.accountingDocument,
                p.accountingDocument AS paymentAccountingDocument,
                p.accountingDocumentItem AS paymentAccountingDocumentItem
            FROM sales_order_headers soh
            LEFT JOIN outbound_delivery_items odi
              ON odi.referenceSdDocument = soh.salesOrder
            LEFT JOIN outbound_delivery_headers odh
              ON odh.deliveryDocument = odi.deliveryDocument
            LEFT JOIN billing_document_items bdi
              ON bdi.referenceSdDocument = odh.deliveryDocument
            LEFT JOIN billing_document_headers bdh
              ON bdh.billingDocument = bdi.billingDocument
            LEFT JOIN journal_entries je
              ON je.referenceDocument = bdh.billingDocument
            LEFT JOIN payments p
              ON p.accountingDocument = je.accountingDocument
            WHERE soh.salesOrder = ?
            LIMIT 20
        """
    elif field == "deliveryDocument":
        sql = """
            SELECT DISTINCT
                odi.referenceSdDocument AS salesOrder,
                odh.deliveryDocument,
                bdh.billingDocument,
                je.accountingDocument,
                p.accountingDocument AS paymentAccountingDocument,
                p.accountingDocumentItem AS paymentAccountingDocumentItem
            FROM outbound_delivery_headers odh
            LEFT JOIN outbound_delivery_items odi
              ON odi.deliveryDocument = odh.deliveryDocument
            LEFT JOIN billing_document_items bdi
              ON bdi.referenceSdDocument = odh.deliveryDocument
            LEFT JOIN billing_document_headers bdh
              ON bdh.billingDocument = bdi.billingDocument
            LEFT JOIN journal_entries je
              ON je.referenceDocument = bdh.billingDocument
            LEFT JOIN payments p
              ON p.accountingDocument = je.accountingDocument
            WHERE odh.deliveryDocument = ?
            LIMIT 20
        """
    else:
        sql = """
            SELECT DISTINCT
                soh.salesOrder,
                odh.deliveryDocument,
                bdh.billingDocument,
                je.accountingDocument,
                p.accountingDocument AS paymentAccountingDocument,
                p.accountingDocumentItem AS paymentAccountingDocumentItem
            FROM billing_document_headers bdh
            LEFT JOIN billing_document_items bdi
              ON bdi.billingDocument = bdh.billingDocument
            LEFT JOIN outbound_delivery_headers odh
              ON odh.deliveryDocument = bdi.referenceSdDocument
            LEFT JOIN outbound_delivery_items odi
              ON odi.deliveryDocument = odh.deliveryDocument
            LEFT JOIN sales_order_headers soh
              ON soh.salesOrder = odi.referenceSdDocument
            LEFT JOIN journal_entries je
              ON je.referenceDocument = bdh.billingDocument
            LEFT JOIN payments p
              ON p.accountingDocument = je.accountingDocument
            WHERE bdh.billingDocument = ?
            LIMIT 20
        """

    return [dict(row) for row in conn.execute(sql, (value,)).fetchall()]


def _build_trace_step(step_name: str, node_id: str | None, node_lookup: dict[str, dict]) -> dict:
    if not node_id:
        return {
            "name": step_name,
            "status": "missing",
            "reference": None,
        }

    node = node_lookup.get(node_id)
    if not node:
        return {
            "name": step_name,
            "status": "missing",
            "reference": None,
        }

    return {
        "name": step_name,
        "status": "found",
        "reference": {
            "id": node_id,
            "label": node.get("label") or node_id,
            "value": (node.get("label") or node_id),
            "type": _humanize_type(node.get("type") or step_name),
        },
    }


def _summarize_trace(trace_request: dict, trace_steps: list[dict]) -> str:
    found_steps = [step for step in trace_steps if step["status"] == "found"]
    missing_steps = [step["name"] for step in trace_steps if step["status"] != "found"]
    start = f"{trace_request['entityType']} {trace_request['value']}"

    if not missing_steps:
        sequence = " -> ".join(step["name"] for step in found_steps)
        return f"Traced {start} across the full flow: {sequence}."

    present = " -> ".join(step["name"] for step in found_steps) if found_steps else "no connected entities"
    missing = ", ".join(missing_steps)
    return f"Traced {start} through {present}. Missing downstream steps: {missing}."


def _maybe_node_id(prefix: str, value: str | None, node_lookup: dict[str, dict]) -> str | None:
    if not value:
        return None
    node_id = f"{prefix}{value}"
    return node_id if node_id in node_lookup else None


def _compose_payment_id(row: dict) -> str | None:
    accounting_document = row.get("paymentAccountingDocument")
    item = row.get("paymentAccountingDocumentItem")
    if accounting_document and item:
        return f"{accounting_document}_{item}"
    return None


def _humanize_type(raw_type: str) -> str:
    return re.sub(r"([A-Z])", r" \1", raw_type).strip()
