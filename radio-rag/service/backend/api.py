#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Radio Mar'ef RAG service — independent backend (FastAPI), port 8003 inside
container (published to 8043 on host 53).

This is a SEPARATE, lean service. It is NOT a 4th scale of the shared
langgraph-neo4j-qa app and does not touch taghrir/mesbah/eiis/rag-portal.

Pipeline per question:
  1. Embed the question with Qwen3-Embedding-0.6B (1024-dim) via the EXISTING
     LiteLLM endpoint (http://172.20.1.52:4000/v1) — the same model/dims used
     to build the corpus. No re-embedding of the corpus happens here.
  2. KNN over the shared Neo4j server's INDEPENDENT `radio` database via
     the pre-built 1024-dim COSINE vector index (`vector_index_chunk`).
  3. Ask the generation LLM (qwen38 via the same LiteLLM gateway) to answer in
     PERSIAN, STRICTLY from the retrieved chunks, and cite each used source
     with: program name + air date (FA + Gregorian when valid, else "نامشخص")
     + time range. No fabricated dates.
  4. Return answer + real citations + score in the same contract the product
     frontends expect: /api/chat, /api/chat/stream (SSE), /api/health.

Session identity: doc_id = <stem>__s<session_id>, so two airings of a show
with similar text (simulcasts) are distinct sources and are never merged.
"""
import json
import os
import time
import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from neo4j import GraphDatabase

# ---------------------------------------------------------------------------
# Config (all via env; sane defaults for the radio instance on 53)
# ---------------------------------------------------------------------------
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j_db:7687")
NEO4J_USER = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD", "your_neo4j_password_here")
NEO4J_DB = os.getenv("NEO4J_DATABASE", "radio")
VECTOR_INDEX = os.getenv("VECTOR_INDEX", "vector_index_chunk")
TOP_K = int(os.getenv("RADIO_TOP_K", "5"))
MIN_SCORE = float(os.getenv("RADIO_MIN_SCORE", "0.25"))

LITELLM_BASE = os.getenv("LITELLM_BASE", "http://172.20.1.52:4000/v1")
LITELLM_KEY = os.getenv("LITELLM_API_KEY", "")
EMBED_MODEL = os.getenv("EMBED_MODEL", "Qwen3-Embedding-0.6B")
GEN_MODEL = os.getenv("GEN_MODEL", "qwen38")

SITE_NAME = os.getenv("SITE_NAME", "دستیار صوتی رادیو معارف")
SITE_TAGLINE = os.getenv("SITE_TAGLINE", "پاسخ مستند از آرشیو کامل رادیو")
SITE_EXAMPLES = os.getenv("SITE_EXAMPLES", "")  # JSON list, optional

app = FastAPI(title="Radio Mar'ef RAG", version="3.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared, thread-safe Neo4j driver. Each request opens its OWN transaction via
# _neo4j_tx (a shared persistent Session is not safe across uvicorn's worker
# threadpool — that was the "Session closed" 500 under concurrent requests).
_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
_driver.verify_connectivity()


def _litelLM_headers():
    h = {"Content-Type": "application/json"}
    if LITELLM_KEY:
        h["Authorization"] = f"Bearer {LITELLM_KEY}"
    return h


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------
def embed(text: str) -> list:
    """Embed one string with the corpus model via the existing LiteLLM endpoint."""
    with httpx.Client(timeout=60) as c:
        r = c.post(
            f"{LITELLM_BASE}/embeddings",
            headers=_litelLM_headers(),
            json={"model": EMBED_MODEL, "input": text},
        )
        r.raise_for_status()
        return r.json()["data"][0]["embedding"]


def _clean(v):
    """Neo4j may return metadata as None; render as empty string."""
    return "" if v is None else str(v)


RETRIEVAL_CYPHER = (
    "CALL db.index.vector.queryNodes($idx, $k, $q) "
    "YIELD node, score "
    "RETURN node.program_name AS program_name, "
    "node.citation AS citation, "
    "node.session_id AS session_id, "
    "node.chunk_id AS chunk_id, "
    "node.doc_id AS doc_id, "
    "node.chunk_type AS chunk_type, "
    "node.air_persian AS air_persian, "
    "node.air_gregorian AS air_gregorian, "
    "node.air_time AS air_time, "
    "node.start_hms AS start_hms, "
    "node.end_hms AS end_hms, "
    "node.channel AS channel, "
    "node.chunk_text AS text, "
    "score AS score "
    "ORDER BY score DESC"
)


def _neo4j_tx(func):
    """Run `func(session)` inside a fresh per-call transaction on the radio db.
    A fresh transaction per request is thread-safe (uvicorn serves sync
    endpoints on a worker threadpool); a shared persistent Session is not."""
    with _driver.session(database=NEO4J_DB) as s:
        return s.execute_read(func) if callable(func) else func(s)


def retrieve(question: str):
    """KNN over the radio vector index; return list of source dicts (best first)."""
    qv = embed(question)

    def _read(tx):
        r = tx.run(RETRIEVAL_CYPHER, idx=VECTOR_INDEX, k=TOP_K, q=qv)
        return [rec.data() for rec in r]

    rows = _neo4j_tx(_read)
    return [d for d in rows if d.get("score", 0) >= MIN_SCORE]


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
def _src_line(i, d):
    date = ""
    if d.get("air_persian"):
        date = d["air_persian"]
    if d.get("air_gregorian"):
        date = f"{d['air_persian']} ({d['air_gregorian']})"
    if not date:
        date = "نامشخص"
    times = ""
    if d.get("start_hms") or d.get("end_hms"):
        times = f" | زمان: {d.get('start_hms','؟')} تا {d.get('end_hms','؟')}"
    return (f"[منبع {i}] برنامه: {d.get('program_name','؟')} | پخش: {date}"
            f" | session_id: {d.get('session_id','؟')}{times}\n"
            f"    متن: {d.get('text','')}")


SYSTEM_PROMPT = (
    "تو دستیار صوتی رادیو معارف هستی. فقط بر اساس «منابع» که در درخواست داده "
    "شده پاسخ بده و چیزی از بیرون این منابع اختراع نکن. همیشه به فارسی و با لحنی "
    "دوستانه و روشن پاسخ بده. اگر پاسخ در منابع نیست، بگو «این موضوع در آرشیو "
    "رادیو یافت نشد.» برای هر نکته‌ای که از یک منبع گرفته‌ای، در پایان جمله همان "
    "شماره منبع را در کروشه بنویس (مثلاً [1]). هیچ تاریخ یا زمان را اختراع نکن؛ "
    "هر مقدار تاریخ/زمان را دقیقاً همان‌طور که در منبع آمده ذکر کن و اگر نبود "
    "بنویس «نامشخص». دو پخش متفاوت یک برنامه (با session_id متفاوت) را با هم "
    "نمیکس. اگر چند منبع مرتبط به یک موضوع بود، همه را به‌کار بگیر."
)


def _gen_messages(question: str, sources):
    ctx = "\n\n".join(_src_line(i + 1, d) for i, d in enumerate(sources))
    if not ctx:
        ctx = "(منبع مرتبطی یافت نشد)"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"منابع:\n{ctx}\n\nسوال: {question}"},
    ]


GEN_MAX_TOKENS = int(os.getenv("GEN_MAX_TOKENS", "2500"))

# OpenAI-compatible /api/v1 endpoint (for rag.ai.ismc.ir "rag-radio" integration).
# Guarded by its own service token; when unset the endpoint is DISABLED (403) so it
# is inert until explicitly wired into LiteLLM. Mirrors the product backends.
RAG_SERVICE_TOKEN = os.getenv("RAG_SERVICE_TOKEN", "")


def _pick_content(msg):
    """qwen38 is a reasoning model: it fills `reasoning_content` first and can
    leave `content` empty when the token budget is consumed by reasoning.
    Prefer real `content`; fall back to reasoning so the answer is never blank."""
    content = (msg.get("content") or "").strip()
    if content:
        return content
    return (msg.get("reasoning_content") or "").strip()


def _llm_chat(messages):
    """Non-streaming LLM call. Returns the assistant text."""
    with httpx.Client(timeout=180) as c:
        r = c.post(
            f"{LITELLM_BASE}/chat/completions",
            headers=_litelLM_headers(),
            json={"model": GEN_MODEL, "messages": messages,
                  "temperature": 0.2, "max_tokens": GEN_MAX_TOKENS,
                  "chat_template_kwargs": {"enable_thinking": False}},
        )
        r.raise_for_status()
        msg = r.json()["choices"][0]["message"]
        return _pick_content(msg)


def _sources_payload(sources):
    out = []
    for i, d in enumerate(sources):
        date = d.get("air_persian")
        if d.get("air_gregorian") and date:
            date = f"{date} ({d['air_gregorian']})"
        out.append({
            "index": i + 1,
            "program_name": d.get("program_name") or "؟",
            "air_date": date or "نامشخص",
            "air_gregorian": d.get("air_gregorian") or "",
            "time": (f"{d.get('start_hms','؟')} تا {d.get('end_hms','؟')}"
                     if (d.get("start_hms") or d.get("end_hms")) else ""),
            "channel": d.get("channel") or "",
            "session_id": d.get("session_id") or "",
            "chunk_id": d.get("chunk_id") or "",
            "chunk_type": d.get("chunk_type") or "",
            "citation": d.get("citation") or "",
            "score": round(float(d.get("score", 0)), 4),
            "text": (d.get("text") or "")[:400],
        })
    return out


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str = Field(..., description="The user question (Persian expected)")
    stream: bool = Field(False, description="Reserved for future SSE")


class Source(BaseModel):
    index: int
    program_name: str
    air_date: str
    air_gregorian: str = ""
    time: str = ""
    channel: str = ""
    session_id: str = ""
    chunk_id: str = ""
    chunk_type: str = ""
    citation: str = ""
    score: float
    text: str = ""


class ChatResponse(BaseModel):
    answer: str
    sources: list
    question: str
    score: float


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    t0 = time.time()
    neo4j_ok = False
    try:
        with _driver.session() as s:
            row = s.run(
                "SHOW DATABASES YIELD name, currentStatus WHERE name=$n",
                n=NEO4J_DB,
            ).single()
            neo4j_ok = bool(row) and str(row["currentStatus"]) in ("online", "standby")
    except Exception as e:  # noqa: BLE001
        neo4j_ok = False
    return {
        "status": "ok" if neo4j_ok else "degraded",
        "service": "radio",
        "neo4j_database": NEO4J_DB,
        "neo4j_online": neo4j_ok,
        "vector_index": VECTOR_INDEX,
        "embedding_model": EMBED_MODEL,
        "gen_model": GEN_MODEL,
        "litellm": LITELLM_BASE,
        "top_k": TOP_K,
        "ms": int((time.time() - t0) * 1000),
    }


@app.post("/api/chat")
def chat(req: ChatRequest):
    q = (req.message or "").strip()
    if not q:
        raise ValueError("empty question")
    try:
        sources = retrieve(q)
        messages = _gen_messages(q, sources)
        answer = _llm_chat(messages)
    except Exception as e:  # noqa: BLE001
        app.logger.exception("chat failed")
        return {
            "answer": (f"در پردازش سوال شما خطایی رخ داد: {e}. لطفاً مجدداً تلاش کنید."),
            "sources": [], "question": q, "score": 0.0, "error": str(e),
        }
    if not sources:
        answer = ("این موضوع در آرشیو رادیو معارف یافت نشد. لطفاً سوال را دقیق‌تر "
                  "بیان کنید یا موضوع دیگری بپرسید.")
    top = sources[0]["score"] if sources else 0.0
    return ChatResponse(
        answer=answer,
        sources=_sources_payload(sources),
        question=q,
        score=round(float(top), 4),
    )


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest):
    """SSE stream: emits the generated answer token-by-token, then a final
    `sources` event, then `done`. Keeps the product frontend's SSE contract."""
    q = (req.message or "").strip()

    def gen():
        try:
            if not q:
                yield f"data: {json.dumps({'type':'error','error':'empty question'}, ensure_ascii=False)}\n\n"
                return
            sources = retrieve(q)
            messages = _gen_messages(q, sources)
            if not sources:
                msg = ("این موضوع در آرشیو رادیو معارف یافت نشد. لطفاً سوال را "
                       "دقیق‌تر بیان کنید یا موضوع دیگری بپرسید.")
                yield f"data: {json.dumps({'type':'delta','content':msg}, ensure_ascii=False)}\n\n"
            else:
                with httpx.Client(timeout=180) as c:
                    # `client.stream(...)` is a context manager that yields the
                    # streaming Response; enter it, then iterate lines.
                    with c.stream(
                        "POST", f"{LITELLM_BASE}/chat/completions",
                        headers=_litelLM_headers(),
                        json={"model": GEN_MODEL, "messages": messages,
                              "temperature": 0.2, "max_tokens": GEN_MAX_TOKENS,
                              "chat_template_kwargs": {"enable_thinking": False},
                              "stream": True},
                    ) as r:
                        for line in r.iter_lines():
                            if not line or not line.startswith("data:"):
                                continue
                            payload = line[5:].strip()
                            if payload == "[DONE]":
                                break
                            try:
                                d = json.loads(payload)["choices"][0]["delta"]
                                # qwen38 streams reasoning_content before content;
                                # forward the real content, and if that never
                                # arrives, surface reasoning so the UI is not blank.
                                piece = d.get("content") or d.get("reasoning_content")
                            except Exception:  # noqa: BLE001
                                continue
                            if piece:
                                yield f"data: {json.dumps({'type':'delta','content':piece}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type':'sources','sources':_sources_payload(sources)}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type':'done'}, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001
            yield f"data: {json.dumps({'type':'error','error':str(e)}, ensure_ascii=False)}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.get("/api/site")
def site():
    """Frontend identity/profile for the radio instance."""
    examples = []
    if SITE_EXAMPLES:
        try:
            examples = json.loads(SITE_EXAMPLES)
        except Exception:  # noqa: BLE001
            examples = []
    return {
        "name": SITE_NAME,
        "tagline": SITE_TAGLINE,
        "examples": examples,
        "service": "radio",
    }


@app.get("/api/programs")
def programs():
    """Distinct program names + counts from the radio db (frontend dropdown)."""
    try:
        def _read(tx):
            r = tx.run(
                "MATCH (n:Chunk) WHERE n.program_name IS NOT NULL "
                "RETURN n.program_name AS p, count(DISTINCT n.session_id) AS sessions, "
                "count(*) AS chunks ORDER BY p"
            )
            return [{"program_name": rec["p"], "sessions": rec["sessions"],
                     "chunks": rec["chunks"]} for rec in r]
        data = _neo4j_tx(_read)
        return {"programs": data, "count": len(data)}
    except Exception as e:  # noqa: BLE001
        return {"programs": [], "count": 0, "error": str(e)}


# ---------------------------------------------------------------------------
# OpenAI-compatible endpoint (rag.ai.ismc.ir "rag-radio" integration, Section 6)
# Mirrors the product backends' POST /api/v1/chat/completions + GET /api/v1/models
# so a LiteLLM `rag-radio` alias can point straight at this service. Guarded by
# RAG_SERVICE_TOKEN; disabled (403) when unset.
# ---------------------------------------------------------------------------
def _check_v1_token(authorization: str = None):
    if not RAG_SERVICE_TOKEN:
        raise HTTPException(status_code=403, detail="RAG_SERVICE_TOKEN not configured")
    presented = (authorization or "").replace("Bearer ", "").strip()
    if presented != RAG_SERVICE_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid service token")


class _V1Message(BaseModel):
    role: str
    content: str = None


class _V1ChatRequest(BaseModel):
    model: str = "rag-radio"
    messages: list
    stream: bool = False


@app.get("/api/v1/models")
def v1_models(authorization: str = Header(default=None)):
    _check_v1_token(authorization)
    return {"object": "list",
            "data": [{"id": "rag-radio", "object": "model", "owned_by": "radio"}]}


@app.post("/api/v1/chat/completions")
def v1_chat_completions(req: _V1ChatRequest, authorization: str = Header(default=None)):
    _check_v1_token(authorization)
    question = next(
        (m["content"] for m in reversed(req.messages)
         if m.get("role") == "user" and (m.get("content") or "").strip()),
        "",
    ).strip()
    if not question:
        raise HTTPException(status_code=400, detail="No user message found")
    try:
        sources = retrieve(question)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"retrieval failed: {e}")
    answer = ""
    if sources:
        try:
            answer = _llm_chat(_gen_messages(question, sources))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"generation failed: {e}")
    else:
        answer = "این موضوع در آرشیو رادیو معارف یافت نشد."
    # citations in the shape rag-portal's call_rag expects (rag.citations list).
    citations = [
        {
            "source": s["program_name"],
            "date": s["air_date"],
            "time": s["time"],
            "session_id": s["session_id"],
            "chunk_id": s["chunk_id"],
            "score": s["score"],
            "text": s["text"],
        }
        for s in _sources_payload(sources)
    ]
    return {
        "id": f"chatcmpl-{int(time.time() * 1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "rag-radio",
        "choices": [{"index": 0,
                     "message": {"role": "assistant", "content": answer},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "rag": {"citations": citations, "answer_spans": [],
                "metadata": {"service": "radio", "top_score":
                             (sources[0]["score"] if sources else 0.0)}},
    }
