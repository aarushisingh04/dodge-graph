# sap o2c graph query system

this repository contains my submission for the graph-based data modeling and query system assignment.

the goal of the project was to take a fragmented sap order to cash dataset, unify it into a graph, and build a natural language interface that could answer business questions with responses grounded in the underlying data.

the result is a small full-stack system with:

- a graph representation of the order to cash process
- a graph visualization ui for exploration
- an llm-powered chat interface for natural language querying
- guardrails to keep the system within the provided dataset and domain

## what i built

the system supports the main assignment requirements:

- graph construction from the dataset
- graph visualization with node inspection and relationship exploration
- relation-aware structural retraction for item-level detail
- natural language querying through a chat interface
- dynamic translation from user questions to structured sqlite queries
- grounded answers generated from real query results
- off-topic rejection and domain guardrails

in addition to the core requirements, i went deeper on a few areas that felt most valuable for this assignment:

- conversation memory for follow-up analytical questions
- deterministic flow tracing for trace-style prompts
- chat-to-graph highlighting through explicit node references

## architecture decisions

the project is split into a backend and a frontend.

### backend

the backend is built with fastapi and handles:

- dataset ingestion into sqlite
- graph construction with networkx
- graph and node detail apis
- llm prompting for sql generation and answer generation
- sql validation and execution
- trace-specific routing
- guardrails

key files:

- `backend/ingest.py`
  ingests and normalizes the dataset into sqlite
- `backend/graph.py`
  builds the networkx graph from the relational data
- `backend/main.py`
  exposes the api endpoints for graph data, node detail, stats, and chat
- `backend/llm.py`
  contains the prompting and llm integration logic
- `backend/query_engine.py`
  validates and executes read-only sql
- `backend/guardrails.py`
  enforces domain restrictions
- `backend/chat_features.py`
  handles deterministic trace requests and result-to-graph reference extraction

### frontend

the frontend is built with react and vite and handles:

- graph rendering with `react-force-graph-2d`
- chat interaction
- rendering result references from responses
- graph highlighting and node focus

key files:

- `frontend/src/App.jsx`
- `frontend/src/components/GraphCanvas.jsx`
- `frontend/src/components/ChatPanel.jsx`
- `frontend/src/components/ChatMessage.jsx`
- `frontend/src/lib/chatReferences.js`

### why i chose this architecture

i wanted a design that was easy to reason about and appropriate for the scope of a take-home assignment.

my decisions were guided by three things:

- keep the data flow clear
- keep the implementation small enough to move quickly
- separate graph concerns from analytical query concerns

the graph and the relational database serve different roles in the system:

- sqlite is the analytical execution layer
- networkx is the graph modeling and exploration layer
- the llm sits on top of sqlite and translates business questions into queries

that separation made the system easier to build, debug, and explain.

## graph modeling decisions

the graph is centered on the order to cash flow:

`sales order -> delivery -> billing document -> journal entry -> payment`

around that core flow, i modeled supporting entities such as:

- customer
- product
- plant
- line-item entities for orders, deliveries, and billing documents

### node types

- salesorder
- salesorderitem
- delivery
- deliveryitem
- billingdoc
- billingitem
- journalentry
- payment
- customer
- product
- plant

### relationships

the graph currently includes edges such as:

- `has_item`
- `sold_to`
- `uses_product`
- `fulfills`
- `ships_from`
- `stored_at`
- `from_delivery`
- `posted_to`
- `billed_to`
- `settled_by`

the edges are intentionally not all treated the same in the ui.

- structural edges such as `has_item` represent expandable item-level detail
- process-flow edges such as `posted_to` and `settled_by` represent downstream business flow
- reference edges such as `sold_to`, `billed_to`, `uses_product`, `ships_from`, and `stored_at` attach shared master data

### why i modeled it this way

the assignment was not just about loading tables into a graph. the important part was deciding what should become a node and what should become an edge.

i chose to model both document headers and item-level records because many useful business questions depend on item-level relationships, especially product-related questions.

for example:

- top products by billing documents
- tracing from order to delivery to billing
- identifying incomplete flows

if i had only modeled header-level entities, a lot of that detail would have been lost.

that distinction also affects the graph interaction model.

- the default retraction logic only collapses structural `has_item` branches
- shared reference nodes such as customers, products, and plants are not hidden when one document branch is retracted
- process-flow edges remain visible so the main order-to-cash path stays legible

this keeps retraction predictable: collapsing a document hides its item-level granularity without accidentally removing shared entities or breaking the higher-level flow view.

## database choice

i chose sqlite as the primary query store.

### why sqlite

- the dataset is local and relatively small
- the queries are analytical and read-only
- setup is simple and fast
- it is easy to inspect and debug during development
- it fits well with llm-generated sql in a constrained environment

for this assignment, sqlite gave me the best tradeoff between simplicity and usefulness.

i did not choose a larger analytical database because the scale did not justify the extra complexity.

## why i used networkx for the graph

the graph is built in memory with networkx because:

- it is straightforward for constructing entity and relationship graphs
- it keeps graph logic easy to inspect
- it is enough for the size of this dataset
- it works well for powering the frontend graph view

if this were a larger production system, i would consider a dedicated graph database or a more scalable graph-serving layer. for this assignment, networkx was the most practical choice.

## llm prompting strategy

the llm integration is intentionally constrained rather than open-ended.

there are two main llm steps:

1. generate sql from a natural language question
2. generate a final business-facing answer from the sql results

### sql generation prompt

the sql generation prompt includes:

- the allowed schema
- known relationships between tables
- explicit instructions to return a json object with `sql` and `explanation`
- constraints to use only the listed tables and columns
- instructions to stay within sqlite syntax
- recent chat history
- recent analytical context from prior turns

the analytical context includes things like:

- the previous user request
- the previous sql
- previous result columns
- recently referenced entities

this was important for follow-up prompts such as:

- `top 5 only`
- `only cancelled ones`
- `same but by customer`

without that extra context, short follow-ups were much less reliable.

### answer generation prompt

the answer generation prompt receives:

- the user question
- recent conversation
- recent analytical context
- the actual sql that was executed
- the returned rows

the answer is then generated from those results with instructions to stay concise and grounded in business meaning.

### why i separated sql generation from answer generation

this separation made the behavior easier to control.

- the first step focuses on correctness of the query
- the second step focuses on communicating the result clearly

it also made debugging easier, because i could inspect the generated sql independently from the final answer.

## deterministic tracing

one issue with relying only on llm-generated sql is that trace-style prompts should feel especially reliable.

for prompts like:

- `trace the full flow of billing document 90504259`

i added a deterministic trace path in the backend.

instead of treating this as just another free-form query, the backend detects the trace intent and builds the flow directly from the known order to cash join sequence.

this returns:

- ordered flow steps
- found and missing stages
- explicit graph references for each stage

this made tracing feel more like a first-class feature and less like a prompt that might or might not work depending on llm behavior.

## conversation memory

one bonus area i chose to deepen was conversation memory.

the system now passes more than plain text history between turns. it can also carry:

- previous sql
- previous results
- previous graph references

on the backend, this is reduced into a structured analytical context and fed back into both sql generation and answer generation.

the goal was not to create long-term memory. the goal was to make multi-turn analysis feel coherent inside a single session.

## guardrails

guardrails were one of the explicit evaluation criteria, so i treated them as a core part of the system rather than an afterthought.

the current approach is rule-based and deliberately simple.

### what the guardrails do

- reject clearly off-topic prompts
- restrict usage to the provided order to cash dataset and domain
- allow short follow-up prompts when prior turns clearly establish valid o2c context

examples of prompts the system should reject:

- `write me a poem`
- `what is the weather`
- `who is the president`

examples of prompts the system should allow:

- `show me sales orders that were delivered but not billed`
- `trace the full flow of billing document 90504259`
- `top 5 only` after a valid analytical question

### why i chose this guardrail design

for this assignment, i wanted the behavior to be easy to explain and easy to test.

a lightweight rule-based layer was enough to satisfy the requirement without overcomplicating the system.

it also makes failure cases easier to reason about compared to trying to solve everything with another llm call.

## result grounding

the system is designed so that responses are grounded in data rather than generated from the llm alone.

that grounding comes from:

- executing generated sql against sqlite
- building the final answer from real returned rows
- exposing references back to graph nodes
- using deterministic traces for flow-style requests

this is especially important because the assignment explicitly called out that the system should not behave like a static or hallucinated q&a tool.

## verification and testing

i added lightweight verification in two places.

### query verification

`backend/verify_examples.py` checks dataset-backed examples such as:

- delivered but not billed sales orders
- a traceable billing document flow

the supporting notes are in:

- `docs/query-verification.md`

### guardrail tests

`backend/tests/test_guardrails.py` covers:

- off-topic rejection
- valid domain prompt acceptance
- short follow-up acceptance with prior context
- short follow-up rejection without context

## limitations

there are still limitations in the current version.

- most analytical questions still depend on llm-generated sql
- the graph is primarily used for modeling, visualization, and navigation, not as a general-purpose graph query engine
- semantic search and hybrid retrieval are not implemented
- streaming responses are not implemented
- memory is session-level and recent-turn only
- some traces are limited by missing downstream records in the source dataset

for example, some billing records contain an `accountingDocument` value in the header table without a matching row in `journal_entries`. in those cases, the trace correctly reports the downstream step as missing because the dataset itself does not contain the required record.

## how to run locally

### backend setup

```powershell
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

create a `.env` file in the project root:

```env
GEMINI_API_KEY=your_key_here
```

### dataset ingestion

place the dataset under one of these locations:

- `data/sap-order-to-cash-dataset/sap-o2c-data/`
- `data/sap-o2c-data/`

then run:

```powershell
cd backend
python ingest.py
```

### start the backend

```powershell
cd backend
python main.py
```

### start the frontend

```powershell
cd frontend
npm install
npm.cmd run dev
```

## useful verification commands

frontend build:

```powershell
cd frontend
npm.cmd run build
```

guardrail tests:

```powershell
backend\venv\Scripts\python.exe -m unittest discover -s backend\tests -p "test*.py"
```

query verification:

```powershell
backend\venv\Scripts\python.exe backend\verify_examples.py
```

## closing note

my goal with this submission was not to add as many features as possible. it was to make the core system coherent and defensible.

the main architectural choice was to keep the graph, relational query layer, and llm responsibilities separate enough that each part stays understandable:

- sqlite for structured analytical queries
- networkx for graph modeling and exploration
- fastapi for a simple backend boundary
- react for an interactive graph-plus-chat ui
- gemini for natural language translation and grounded answer generation

that design let me move quickly while still making deliberate choices around graph modeling, database selection, prompting strategy, and guardrails, which were the main areas the assignment asked me to explain.
