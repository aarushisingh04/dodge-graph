# sap o2c graph query system

graph-based data exploration and natural language querying over a sap order-to-cash dataset.

live demo: https://dodge-graph.vercel.app/

## what it does

**core requirements:**
- graph construction from the dataset with typed nodes and edges
- graph visualization with node inspection, relationship exploration, and relation-aware retraction
- natural language querying through a chat interface
- dynamic sql generation from user questions, executed against real data
- grounded answers built from actual query results
- off-topic rejection and domain guardrails

**bonus depth areas:**
- conversation memory for multi-turn analytical follow-ups
- deterministic flow tracing for trace-style prompts
- chat-to-graph highlighting via explicit node references

## stack

| layer | choice |
|---|---|
| api | fastapi |
| query store | sqlite |
| graph engine | networkx |
| llm | google gemini 1.5 flash (free tier) |
| frontend | react + vite + react-force-graph-2d |

## architecture decisions

the system has four clearly separated responsibilities:

| layer | role |
|---|---|
| sqlite | analytical execution. all business questions are answered by running sql against it. |
| networkx | graph modeling and visualization. powers the frontend graph view, not used as a query engine. |
| fastapi | thin boundary exposing graph data, node detail, stats, and chat endpoints. |
| llm | translation layer. sits on top of sqlite, converts natural language to sql, then converts results to readable answers. |

keeping these responsibilities separate made each part easier to build, debug, and explain independently. it also made the system's failure modes more predictable: if a query is wrong, the problem is in the sql generation step, not tangled somewhere across layers.

## graph modeling decisions

core flow: `sales order -> delivery -> billing document -> journal entry -> payment`

### node types

| node | primary key |
|---|---|
| salesorder | salesorder |
| salesorderitem | salesorder + salesorderitem |
| delivery | deliverydocument |
| deliveryitem | deliverydocument + deliverydocumentitem |
| billingdoc | billingdocument |
| billingitem | billingdocument + billingdocumentitem |
| journalentry | accountingdocument |
| payment | accountingdocument + accountingdocumentitem |
| customer | businesspartner |
| product | product |
| plant | plant |

### edge types

| edge | type | meaning |
|---|---|---|
| `has_item` | structural | expandable item-level detail, collapsible per document |
| `posted_to` | process-flow | billing doc to journal entry |
| `settled_by` | process-flow | journal entry to payment |
| `from_delivery` | process-flow | billing item back to delivery |
| `fulfills` | process-flow | delivery item back to sales order |
| `sold_to` | reference | sales order to customer |
| `billed_to` | reference | billing doc to customer |
| `uses_product` | reference | order item to product |
| `ships_from` | reference | delivery item to plant |
| `stored_at` | reference | product to plant |

### why item-level nodes matter

modeling both document headers and item-level records was a deliberate choice. many useful business questions depend on item-level relationships:

- top products by billing documents requires item-level product linkage
- tracing order to delivery to billing requires item-level join paths
- incomplete flow detection requires item-level presence checks

header-only modeling would lose all of that.

### how retraction works

the edge type distinction also drives the ui interaction model:

- **structural edges** (`has_item`) are the only ones collapsed on retraction. collapsing a document hides its item-level detail.
- **reference nodes** (customer, product, plant) are never hidden when a branch retracts, because they are shared across multiple documents.
- **process-flow edges** stay visible so the main o2c chain remains legible at any zoom level.

this keeps retraction predictable: collapsing a billing document hides its items without accidentally removing the customer node that other documents also point to.

## database choice: sqlite

| factor | reasoning |
|---|---|
| scale | ~22k records, read-only, no concurrent writes |
| infrastructure | zero setup, runs as a file, trivial to inspect during development |
| llm compatibility | constrained query surface makes llm-generated sql more reliable and easier to validate |
| tradeoff accepted | would not scale to production volumes or concurrent users, but that was not a requirement here |

for a larger production system i would consider postgresql or a dedicated analytical store. for this assignment sqlite gave the best tradeoff between simplicity and usefulness.

## why networkx

| factor | reasoning |
|---|---|
| construction | straightforward api for typed nodes and edges |
| inspection | easy to query and debug during development |
| scale fit | sufficient for this dataset size |
| frontend fit | serializes cleanly to the node/link format react-force-graph-2d expects |
| tradeoff accepted | would not scale to millions of nodes; a dedicated graph database would be needed at production scale |

## llm prompting strategy

### two-step design

every chat turn makes two separate llm calls:

**step 1: sql generation**

| input | detail |
|---|---|
| schema | all allowed tables and columns |
| join paths | explicit relationships between tables |
| output format | must return `{"sql": "...", "explanation": "..."}` as json |
| constraints | sqlite syntax only, no invented columns |
| temperature | 0.1 to reduce hallucination on column and table names |
| chat history | recent turns passed as context |
| analytical context | previous sql, previous result columns, recently referenced entities |

the analytical context is what makes short follow-ups work reliably. prompts like `top 5 only`, `only cancelled ones`, or `same but by customer` succeed because the prior sql and result shape are available to the next generation step. without that context, short follow-ups were much less reliable.

**step 2: answer generation**

| input | detail |
|---|---|
| user question | original prompt |
| conversation | recent turns |
| analytical context | same context passed to sql generation |
| sql executed | the actual query that ran |
| returned rows | real data from sqlite |
| temperature | 0.3 for more natural phrasing |

the answer is always generated from real returned rows, not from the llm's internal knowledge.

### why two steps instead of one

separating sql generation from answer generation makes the behavior easier to control and debug. the first step focuses on query correctness. the second focuses on communicating the result clearly. it also means i can inspect the generated sql independently from the final answer, which made development much faster.

### deterministic tracing

trace-style prompts (`trace the full flow of billing document 90504259`) bypass the llm entirely. the backend detects the trace intent and builds the flow directly from the known o2c join sequence. this returns:

- ordered flow steps with found and missing stages
- explicit graph references for each stage

tracing is a first-class feature rather than a prompt that may or may not produce correct sql depending on phrasing.

### conversation memory

the system passes more than plain text history between turns. each turn also carries:

- previous sql
- previous result columns
- previous graph references

on the backend this is reduced into a structured analytical context and fed into both prompts. the goal is not long-term memory. the goal is making multi-turn analysis feel coherent inside a single session.

## guardrails

rule-based, applied before the llm is called. the design is intentionally simple so failure cases are easy to explain and test.

| prompt | decision | reason |
|---|---|---|
| `write me a poem` | rejected | no domain keywords |
| `what is the weather` | rejected | off-topic pattern match |
| `who is the president` | rejected | off-topic pattern match |
| `show me delivered but not billed orders` | allowed | domain keywords present |
| `trace the full flow of billing document 90504259` | allowed | domain keywords present |
| `top 5 only` (after valid prior turn) | allowed | prior context establishes o2c domain |
| `top 5 only` (no prior context) | rejected | no domain keywords and no prior context |

a lightweight rule-based layer was enough to satisfy the requirement without the unpredictability of routing guardrail decisions through another llm call.

`backend/tests/test_guardrails.py` covers all four cases above.

## result grounding

responses are grounded in data rather than generated from llm memory:

- sql is executed against sqlite and the returned rows are passed to the answer generation step
- the final answer is generated from those rows, not from the llm's knowledge
- node references extracted from results are highlighted in the graph
- deterministic traces resolve every flow step from actual database joins and report missing steps explicitly

## verification

| check | file | what it covers |
|---|---|---|
| query verification | `backend/verify_examples.py` | delivered-but-not-billed detection, full flow trace |
| guardrail tests | `backend/tests/test_guardrails.py` | off-topic rejection, valid acceptance, follow-up with and without context |
| query notes | `docs/query-verification.md` | supporting detail for verified examples |

## limitations

| limitation | note |
|---|---|
| most queries depend on llm-generated sql | correctness is not guaranteed for every prompt |
| graph is for modeling and visualization only | not a general-purpose graph query engine |
| memory is session-scoped and recent-turn only | no persistence across sessions |
| streaming not implemented | full response returned at once |
| semantic search not implemented | keyword and sql-based only |
| some traces have missing downstream steps | some billing records reference accounting documents absent from journal_entries. this is a dataset gap, not a code bug. the trace reports those steps as missing correctly. |

## how to run locally
```bash
# backend
cd backend
python -m venv venv
venv\Scripts\activate        # mac/linux: source venv/bin/activate
pip install -r requirements.txt
python ingest.py             # dataset must be at data/sap-o2c-data/
python main.py

# frontend
cd frontend
npm install
npm run dev                  # windows: npm.cmd run dev
```

add `GEMINI_API_KEY=your_key_here` to a `.env` file in the project root.

### verification commands
```bash
# guardrail tests
backend\venv\Scripts\python.exe -m unittest discover -s backend\tests -p "test*.py"

# query verification
backend\venv\Scripts\python.exe backend\verify_examples.py
```