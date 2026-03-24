# Query Verification

These examples are grounded in the current dataset in `backend/o2c.db` and can be reproduced with:

```powershell
backend\venv\Scripts\python.exe backend\verify_examples.py
```

## Delivered But Not Billed

Verified sample rows:

- Sales order `740506` with delivery `80737721`
- Sales order `740507` with delivery `80737722`
- Sales order `740508` with delivery `80737723`

Business meaning:

- The delivery exists in `outbound_delivery_items`
- No linked billing document exists in `billing_document_items` for that delivery

## Billed Without Delivery

Current dataset result:

- No sample rows returned by the verification query

Business meaning:

- The verification query checks for billing items whose referenced delivery does not exist in `outbound_delivery_headers`
- In the current dataset, the first pass did not surface such examples

## Flow Trace Example

Verified sample row for billing document `90504259`:

- Sales order `740560`
- Delivery `80738080`
- Billing document `90504259`
- Journal entry `9400000260`

Business meaning:

- This billing document can be used in the demo to show the deterministic trace flow
- The trace chain is built from the known O2C join sequence instead of relying only on generic SQL generation
