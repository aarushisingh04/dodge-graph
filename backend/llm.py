import json
import os
import re

import httpx
from dotenv import load_dotenv


load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)

DB_SCHEMA = """
You have access to a SQLite database with the following tables:

TABLE sales_order_headers:
  salesOrder, salesOrderType, salesOrganization, distributionChannel,
  soldToParty, creationDate, totalNetAmount, overallDeliveryStatus,
  overallOrdReltdBillgStatus, transactionCurrency, requestedDeliveryDate,
  headerBillingBlockReason, deliveryBlockReason, customerPaymentTerms

TABLE sales_order_items:
  salesOrder, salesOrderItem, salesOrderItemCategory, material,
  requestedQuantity, requestedQuantityUnit, netAmount, transactionCurrency,
  materialGroup, productionPlant, storageLocation, itemBillingBlockReason

TABLE outbound_delivery_headers:
  deliveryDocument, creationDate, overallGoodsMovementStatus,
  overallPickingStatus, shippingPoint, deliveryBlockReason

TABLE outbound_delivery_items:
  deliveryDocument, deliveryDocumentItem, plant, actualDeliveryQuantity,
  referenceSdDocument, referenceSdDocumentItem, storageLocation
  -- referenceSdDocument = salesOrder

TABLE billing_document_headers:
  billingDocument, billingDocumentType, totalNetAmount, transactionCurrency,
  billingDocumentIsCancelled, accountingDocument, soldToParty,
  companyCode, fiscalYear, creationDate, billingDocumentDate

TABLE billing_document_items:
  billingDocument, billingDocumentItem, material, billingQuantity,
  netAmount, transactionCurrency, referenceSdDocument, referenceSdDocumentItem
  -- referenceSdDocument = deliveryDocument

TABLE journal_entries:
  accountingDocument, companyCode, fiscalYear, glAccount, referenceDocument,
  profitCenter, amountInTransactionCurrency, transactionCurrency,
  amountInCompanyCodeCurrency, postingDate, documentDate, customer,
  accountingDocumentType, clearingDate, clearingAccountingDocument
  -- referenceDocument = billingDocument

TABLE payments:
  accountingDocument, accountingDocumentItem, clearingDate,
  clearingAccountingDocument, amountInTransactionCurrency, transactionCurrency,
  customer, postingDate, glAccount, profitCenter

TABLE business_partners:
  businessPartner, customer, businessPartnerFullName, businessPartnerName,
  organizationBpName1, businessPartnerIsBlocked, creationDate

TABLE business_partner_addresses:
  businessPartner, cityName, country, region, postalCode, streetName

TABLE products:
  product, productType, productGroup, grossWeight, netWeight, baseUnit,
  division, isMarkedForDeletion, productOldId

TABLE product_descriptions:
  product, language, productDescription

TABLE plants:
  plant, plantName, salesOrganization, distributionChannel

TABLE billing_document_cancellations:
  billingDocument, billingDocumentType, billingDocumentIsCancelled,
  totalNetAmount, accountingDocument, soldToParty, companyCode, fiscalYear

KEY RELATIONSHIPS:
- Sales Order -> Delivery: outbound_delivery_items.referenceSdDocument = sales_order_headers.salesOrder
- Delivery -> Billing: billing_document_items.referenceSdDocument = outbound_delivery_headers.deliveryDocument
- Billing -> Journal: journal_entries.referenceDocument = billing_document_headers.billingDocument
- Journal -> Payment: payments.accountingDocument = journal_entries.accountingDocument
- Sales Order -> Customer: sales_order_headers.soldToParty = business_partners.businessPartner
- Billing -> Customer: billing_document_headers.soldToParty = business_partners.businessPartner
- Product descriptions: products.product = product_descriptions.product AND language = 'EN'
"""

SYSTEM_PROMPT = f"""You are a data analyst assistant for an SAP Order-to-Cash system. You answer questions strictly about the dataset.

{DB_SCHEMA}

INSTRUCTIONS:
1. Translate the user's question into a SQLite SQL query.
2. Return valid JSON in this exact format:
{{
  "sql": "SELECT ...",
  "explanation": "Brief explanation of what the query does"
}}
3. Use only tables and columns listed above.
4. All values are stored as TEXT.
5. For the full O2C flow trace of a sales order, join: sales_order_headers -> outbound_delivery_items -> outbound_delivery_headers -> billing_document_items -> billing_document_headers -> journal_entries -> payments
6. To find broken flows: a sales order is delivered-but-not-billed if it appears in outbound_delivery_items but not in billing_document_items via the delivery document.
7. Follow-up questions depend on prior context. Reuse the latest relevant entities, filters, grouping, and sort order when the user says things like "those", "them", "that customer", "only cancelled ones", "top 5", "same but by customer", or "trace it".
8. Prefer returning entity identifiers needed by the graph when possible, such as salesOrder, deliveryDocument, billingDocument, accountingDocument, businessPartner/customer, or product/material.
9. Unless the user asks for a full export, keep result sets reasonably bounded, typically with LIMIT 20.
10. Use explicit JOIN conditions; do not invent columns or tables.
11. Return only the JSON object.
"""


def _format_history(history: list[dict] | None) -> str:
    if not history:
        return "No prior conversation."

    lines = []
    for message in history[-6:]:
        role = message.get("role", "user").strip().lower()
        content = str(message.get("content", "")).strip()
        if not content:
            continue
        speaker = "User" if role == "user" else "Assistant"
        lines.append(f"{speaker}: {content}")
    return "\n".join(lines) if lines else "No prior conversation."


def _extract_recent_context(history: list[dict] | None) -> str:
    if not history:
        return "No structured analytical context."

    last_user_message = None
    last_assistant_message = None
    referenced_entities = []
    seen_entities = set()

    for message in reversed(history):
        if last_user_message is None and message.get("role") == "user":
            content = str(message.get("content", "")).strip()
            if content:
                last_user_message = content

        if last_assistant_message is None and message.get("role") == "assistant":
            last_assistant_message = message

        for reference in message.get("references") or []:
            ref_id = reference.get("id")
            if not ref_id or ref_id in seen_entities:
                continue

            label = str(reference.get("label") or reference.get("value") or ref_id).strip()
            ref_type = str(reference.get("type") or "Entity").strip()
            referenced_entities.append(f"{ref_type}: {label} [{ref_id}]")
            seen_entities.add(ref_id)

        if len(referenced_entities) >= 8 and last_user_message and last_assistant_message:
            break

    lines = []

    if last_user_message:
        lines.append(f"Most recent user request: {last_user_message}")

    if last_assistant_message:
        sql = str(last_assistant_message.get("sql") or "").strip()
        results = last_assistant_message.get("results") or []
        explanation = str(last_assistant_message.get("explanation") or "").strip()

        if explanation:
            lines.append(f"Previous analytical intent: {explanation}")

        if sql:
            compact_sql = re.sub(r"\s+", " ", sql).strip()
            lines.append(f"Previous SQL: {compact_sql}")

        if results:
            sample_row = results[0] if isinstance(results[0], dict) else {}
            if sample_row:
                result_columns = ", ".join(sample_row.keys())
                lines.append(f"Previous result columns: {result_columns}")
            lines.append(f"Previous result count available to memory: {len(results)}")

    if referenced_entities:
        lines.append("Recent referenced entities: " + "; ".join(referenced_entities[:8]))

    return "\n".join(lines) if lines else "No structured analytical context."


async def generate_sql(user_question: str, history: list[dict] | None = None) -> dict:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is missing in .env")

    history_context = _format_history(history)
    structured_context = _extract_recent_context(history)
    user_prompt = f"""Conversation so far:
{history_context}

Structured analytical context:
{structured_context}

Current user question:
{user_question}"""

    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": SYSTEM_PROMPT}]},
            {"role": "model", "parts": [{"text": '{"sql": "SELECT 1", "explanation": "Ready"}'}]},
            {"role": "user", "parts": [{"text": user_prompt}]},
        ],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1024},
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(f"{GEMINI_URL}?key={GEMINI_API_KEY}", json=payload)
        response.raise_for_status()
        data = response.json()

    raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    return _parse_sql_response(raw)


async def generate_answer(
    user_question: str,
    sql: str,
    results: list[dict],
    history: list[dict] | None = None,
) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is missing in .env")

    prompt = f"""Recent conversation:
{_format_history(history)}

Structured analytical context:
{_extract_recent_context(history)}

The user asked: "{user_question}"

We ran this SQL query:
{sql}

The results are:
{json.dumps(results[:50], indent=2)}

Write a clear, concise answer to the user's question based on these results.
- If results are empty, say no matching records were found and suggest why.
- Be specific and use actual values from the results.
- Keep it under 150 words.
- Do not mention SQL or technical details.
- Stay focused on the business meaning."""

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 512},
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(f"{GEMINI_URL}?key={GEMINI_API_KEY}", json=payload)
        response.raise_for_status()
        data = response.json()

    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def _parse_sql_response(raw: str) -> dict:
    cleaned = raw.strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", maxsplit=2)[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    json_match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if json_match:
        try:
            parsed = json.loads(json_match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    sql_match = re.search(r'"sql"\s*:\s*"((?:[^"\\]|\\.)*)"', cleaned, flags=re.DOTALL)
    explanation_match = re.search(
        r'"explanation"\s*:\s*"((?:[^"\\]|\\.)*)"',
        cleaned,
        flags=re.DOTALL,
    )
    if sql_match:
        sql = bytes(sql_match.group(1), "utf-8").decode("unicode_escape")
        explanation = ""
        if explanation_match:
            explanation = bytes(explanation_match.group(1), "utf-8").decode("unicode_escape")
        return {"sql": sql, "explanation": explanation}

    sql_line_match = re.search(r"(SELECT|WITH)\s.+", cleaned, flags=re.IGNORECASE | re.DOTALL)
    if sql_line_match:
        sql = sql_line_match.group(0).strip()
        return {"sql": sql, "explanation": "Recovered from non-JSON model output."}

    raise ValueError("The model returned malformed query JSON. Please try rephrasing.")
