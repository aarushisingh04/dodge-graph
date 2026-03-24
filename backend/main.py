import os
from collections import Counter
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from chat_features import build_node_lookup, build_trace_response, detect_trace_request, extract_references
from graph import build_graph, graph_to_json
from guardrails import is_allowed
from ingest import DB_PATH, ingest
from llm import generate_answer, generate_sql
from query_engine import run_sql, validate_sql


_graph = None
_graph_json = None
_node_lookup = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _graph, _graph_json, _node_lookup
    if not os.path.exists(DB_PATH):
        print("Database not found, running ingestion...")
        ingest()
    else:
        print("Database found, skipping ingestion.")

    _graph = build_graph()
    _graph_json = graph_to_json(_graph)
    _node_lookup = build_node_lookup(_graph)
    yield


app = FastAPI(title="O2C Graph API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/graph")
def get_graph():
    return _graph_json


@app.get("/api/node/{node_id:path}")
def get_node(node_id: str):
    if _graph is None or not _graph.has_node(node_id):
        raise HTTPException(status_code=404, detail="Node not found")

    attrs = dict(_graph.nodes[node_id])
    neighbors = []
    for neighbor in _graph.successors(node_id):
        edge_data = _graph.edges[node_id, neighbor]
        neighbors.append(
            {
                "id": neighbor,
                "type": _graph.nodes[neighbor].get("type"),
                "label": _graph.nodes[neighbor].get("label"),
                "relation": edge_data.get("relation"),
                "direction": "outgoing",
            }
        )
    for neighbor in _graph.predecessors(node_id):
        edge_data = _graph.edges[neighbor, node_id]
        neighbors.append(
            {
                "id": neighbor,
                "type": _graph.nodes[neighbor].get("type"),
                "label": _graph.nodes[neighbor].get("label"),
                "relation": edge_data.get("relation"),
                "direction": "incoming",
            }
        )

    return {"id": node_id, "properties": attrs, "connections": neighbors}


@app.get("/api/stats")
def get_stats():
    if _graph is None:
        return {}
    type_counts = Counter(_graph.nodes[node].get("type") for node in _graph.nodes)
    return {
        "total_nodes": _graph.number_of_nodes(),
        "total_edges": _graph.number_of_edges(),
        "node_types": dict(type_counts),
    }


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


@app.post("/api/chat")
async def chat(req: ChatRequest):
    allowed, reason = is_allowed(req.message, req.history)
    if not allowed:
        return {"answer": reason, "sql": None, "results": [], "references": [], "trace": None, "error": None}

    try:
        trace_request = detect_trace_request(req.message)
        if trace_request:
            return build_trace_response(trace_request, _node_lookup or {})

        llm_response = await generate_sql(req.message, req.history)
        sql = validate_sql(llm_response.get("sql", ""))
        explanation = llm_response.get("explanation", "")

        if not sql or sql.strip().upper() == "SELECT 1":
            return {
                "answer": "I couldn't generate a valid query for that question. Please try rephrasing.",
                "sql": sql,
                "results": [],
                "references": [],
                "trace": None,
                "error": None,
            }

        results = run_sql(sql)
        answer = await generate_answer(req.message, sql, results, req.history)
        visible_results = results[:20]
        return {
            "answer": answer,
            "sql": sql,
            "results": visible_results,
            "explanation": explanation,
            "references": extract_references(visible_results, _node_lookup or {}),
            "trace": None,
            "error": None,
        }
    except ValueError as exc:
        return {
            "answer": f"Query error: {exc}",
            "sql": None,
            "results": [],
            "references": [],
            "trace": None,
            "error": str(exc),
        }
    except Exception as exc:
        return {
            "answer": "An error occurred while processing your question. Please try again.",
            "sql": None,
            "results": [],
            "references": [],
            "trace": None,
            "error": str(exc),
        }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
