const REFERENCE_PATTERNS = [
  { prefix: 'SO_', keys: ['salesOrder', 'referenceSdDocument'], type: 'Sales Order' },
  { prefix: 'DEL_', keys: ['deliveryDocument', 'delivery'], type: 'Delivery' },
  { prefix: 'BILL_', keys: ['billingDocument', 'referenceDocument'], type: 'Billing Document' },
  { prefix: 'JE_', keys: ['accountingDocument', 'journalEntry'], type: 'Journal Entry' },
  {
    prefix: 'CUST_',
    keys: ['businessPartner', 'soldToParty', 'customer'],
    type: 'Customer'
  },
  { prefix: 'PROD_', keys: ['product', 'material'], type: 'Product' }
]

export function extractNodeReferences(results, nodeLookup = new Map()) {
  const references = []
  const seen = new Set()

  for (const row of results || []) {
    for (const { prefix, keys, type } of REFERENCE_PATTERNS) {
      const value = keys.map((key) => row[key]).find(Boolean)

      if (!value) {
        continue
      }

      const id = `${prefix}${value}`

      if (seen.has(id)) {
        continue
      }

      const graphNode = nodeLookup.get(id)

      references.push({
        id,
        value: String(value),
        type: graphNode?.type?.replace(/([A-Z])/g, ' $1').trim() || type,
        label: graphNode?.label || String(value)
      })
      seen.add(id)
    }
  }

  return references
}
