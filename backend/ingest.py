import glob
import json
import os
import sqlite3


BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "o2c.db")
DATA_DIR_CANDIDATES = [
    os.path.join(BASE_DIR, "..", "data", "sap-o2c-data"),
    os.path.join(BASE_DIR, "..", "data", "sap-order-to-cash-dataset"),
    os.path.join(BASE_DIR, "..", "data", "sap-order-to-cash-dataset", "sap-o2c-data"),
]

TABLES = {
    "sales_order_headers": "sales_order_headers",
    "sales_order_items": "sales_order_items",
    "sales_order_schedule_lines": "sales_order_schedule_lines",
    "outbound_delivery_headers": "outbound_delivery_headers",
    "outbound_delivery_items": "outbound_delivery_items",
    "billing_document_headers": "billing_document_headers",
    "billing_document_items": "billing_document_items",
    "billing_document_cancellations": "billing_document_cancellations",
    "journal_entry_items_accounts_receivable": "journal_entries",
    "payments_accounts_receivable": "payments",
    "business_partners": "business_partners",
    "business_partner_addresses": "business_partner_addresses",
    "customer_company_assignments": "customer_company_assignments",
    "customer_sales_area_assignments": "customer_sales_area_assignments",
    "products": "products",
    "product_descriptions": "product_descriptions",
    "product_plants": "product_plants",
    "plants": "plants",
    "product_storage_locations": "product_storage_locations",
}


def resolve_data_dir() -> str:
    for candidate in DATA_DIR_CANDIDATES:
        if not os.path.isdir(candidate):
            continue
        sample_folder = os.path.join(candidate, "sales_order_headers")
        if os.path.isdir(sample_folder) and glob.glob(os.path.join(sample_folder, "*.jsonl")):
            return os.path.abspath(candidate)
    raise FileNotFoundError(
        "Dataset directory not found. Expected one of: "
        + ", ".join(os.path.abspath(path) for path in DATA_DIR_CANDIDATES)
    )


def load_jsonl(data_dir: str, folder_name: str) -> list[dict]:
    records = []
    pattern = os.path.join(data_dir, folder_name, "*.jsonl")
    for filepath in sorted(glob.glob(pattern)):
        with open(filepath, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def flatten_record(record: dict) -> dict:
    flat = {}
    for key, value in record.items():
        if isinstance(value, (dict, list)):
            flat[key] = json.dumps(value)
        elif value is None:
            flat[key] = None
        else:
            flat[key] = str(value)
    return flat


def ingest() -> None:
    data_dir = resolve_data_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")

    for folder_name, table_name in TABLES.items():
        records = load_jsonl(data_dir, folder_name)
        if not records:
            print(f"WARNING: no records found for {folder_name}")
            continue

        flat_records = [flatten_record(record) for record in records]
        columns = sorted({key for record in flat_records for key in record.keys()})

        col_defs = ", ".join(f'"{column}" TEXT' for column in columns)
        conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
        conn.execute(f'CREATE TABLE "{table_name}" ({col_defs})')

        placeholders = ", ".join("?" for _ in columns)
        col_names = ", ".join(f'"{column}"' for column in columns)
        insert_sql = f'INSERT INTO "{table_name}" ({col_names}) VALUES ({placeholders})'

        for record in flat_records:
            conn.execute(insert_sql, [record.get(column) for column in columns])

        conn.commit()
        print(f"Loaded {len(records)} records into {table_name}")

    indexes = [
        ("sales_order_headers", "salesOrder"),
        ("sales_order_headers", "soldToParty"),
        ("sales_order_items", "salesOrder"),
        ("sales_order_items", "material"),
        ("outbound_delivery_items", "referenceSdDocument"),
        ("outbound_delivery_items", "deliveryDocument"),
        ("billing_document_headers", "accountingDocument"),
        ("billing_document_headers", "soldToParty"),
        ("billing_document_items", "referenceSdDocument"),
        ("billing_document_items", "billingDocument"),
        ("journal_entries", "accountingDocument"),
        ("journal_entries", "referenceDocument"),
        ("payments", "accountingDocument"),
        ("business_partners", "businessPartner"),
        ("products", "product"),
        ("product_descriptions", "product"),
        ("plants", "plant"),
    ]
    for table, column in indexes:
        try:
            conn.execute(
                f'CREATE INDEX IF NOT EXISTS idx_{table}_{column} ON "{table}" ("{column}")'
            )
        except Exception:
            continue

    conn.commit()
    conn.close()
    print("Ingestion complete.")


if __name__ == "__main__":
    ingest()
