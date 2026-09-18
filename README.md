# DocMind - Smart RAG Chatbot

An end-to-end **Retrieval-Augmented Generation** chatbot. Create knowledge
bases, upload documents (PDF / DOCX / TXT / MD), watch them move through a live
processing pipeline, then ask questions that are answered **only from your
documents** — with **page-level citations**, a source viewer, streaming
answers, feedback, and a metrics dashboard.

Built with **FastAPI · LangChain · Google Gemini · ChromaDB · SQLite** — a
modular, provider-abstracted, observable architecture that runs as a single
process with **one command** and no external services.

---

## Features

| Area | What's implemented |
|------|--------------------|
| **Ingestion** | Upload → validate → parse → clean → chunk → embed → index, in a background worker |
| **State machine** | Live `UPLOADED → PARSED → CHUNKED → EMBEDDING → INDEXED → READY` (or `FAILED`) shown in the UI |
| **File security** | Extension + size + magic-byte signature validation; generated storage paths |
| **Page-aware parsing** | PyMuPDF keeps real PDF page numbers for accurate citations |
| **Retrieval** | Vector search filtered per knowledge base, confidence threshold (hallucination guard) |
| **Grounded generation** | Answers only from context; refuses with a clear message when unsure |
| **Citations** | Inline `[1]` markers + source cards with document, **page**, %-match, and a **source viewer** |
| **Streaming** | Tokens stream to the UI via Server-Sent Events |
| **Conversations** | Multi-turn memory per conversation |
| **Feedback** | 👍 / 👎 stored per answer |
| **Suggested questions** | Auto-generated after a document becomes ready |
| **Observability** | Structured logs w/ request IDs, retrieval + latency logs, AI usage, metrics dashboard |
| **Provider abstraction** | `LLMProvider` / `EmbeddingProvider` interfaces — swap vendors without touching app code |
| **Health** | `/health` and `/ready` endpoints |

## Architecture

```
Browser (KB sidebar · upload+status · streaming chat · source viewer · metrics)
        │  REST + Server-Sent Events
        ▼
FastAPI (app/main.py)
        │
        ├── api/            knowledge_bases · documents · chat · feedback/admin
        ├── services/       validation · parser · cleaner · chunker
        │                   ingestion(state machine) · vector_store
        │                   retrieval · context_builder · chat(orchestrator)
        ├── providers/      base interfaces  →  gemini implementation
        ├── db/             SQLite (metadata, conversations, logs)
        └── core/           config · logging · state
                     │
        Storage:  SQLite (metadata)  +  Chroma (vectors)  +  uploads/
```

## Project structure

```
.
├── app/
│   ├── main.py                     # FastAPI app, health checks, static serving
│   ├── core/  config.py · logging.py · state.py
│   ├── db/    database.py          # SQLite schema + queries + metrics
│   ├── providers/  base.py · gemini.py · __init__.py (factory)
│   ├── services/
│   │   ├── validation.py           # file security checks
│   │   ├── parser.py               # PDF(PyMuPDF)/DOCX/TXT/MD → page-structured text
│   │   ├── cleaner.py              # whitespace/hyphenation normalization
│   │   ├── chunker.py              # page-aware overlapping chunks + token estimate
│   │   ├── vector_store.py         # Chroma wrapper (metadata-filtered search)
│   │   ├── ingestion.py            # background pipeline + state machine
│   │   ├── retrieval.py            # vector search + confidence gate
│   │   ├── context_builder.py      # source formatting + prompt
│   │   └── chat.py                 # retrieval→generation→citations→logging
│   └── api/   schemas.py · knowledge_bases.py · documents.py · chat.py · feedback.py
├── frontend/  index.html · style.css · app.js
├── storage/                        # SQLite + Chroma + uploads (auto-created, git-ignored)
├── .env                            # GOOGLE_API_KEY=...
├── .env.example
├── requirements.txt
└── run.sh
```

## Setup

1. Put your Gemini key in a `.env` at the project root (see `.env.example`):
   ```
   GOOGLE_API_KEY=your_key_here
   ```
2. Install dependencies:
   ```bash
   python3 -m pip install -r requirements.txt
   ```

## Run

```bash
bash run.sh
# open http://127.0.0.1:8000
```

## Demo flow

1. A default knowledge base is created for you on first launch.
2. Drag a **PDF/DOCX/TXT/MD** into the sidebar (or click to browse).
3. Watch the processing pipeline fill in until the document is **Ready**.
4. Try a suggested question, or ask your own.
5. Read the answer — click any `[1]` citation or source card to open the **source viewer** (document + page + exact chunk).
6. Ask something **not** in the documents → get the grounded "couldn't find this" response.
7. Rate answers with 👍 / 👎.
8. Open **Metrics & Logs** to see query latencies, retrieval scores, and usage.

## API (v1)

```
GET    /health   /ready
GET    /api/v1/knowledge-bases
POST   /api/v1/knowledge-bases
GET    /api/v1/knowledge-bases/{id}
DELETE /api/v1/knowledge-bases/{id}
POST   /api/v1/knowledge-bases/{id}/documents        # upload (queued)
GET    /api/v1/documents/{id}                         # status / state machine
DELETE /api/v1/documents/{id}
POST   /api/v1/documents/{id}/reprocess
POST   /api/v1/documents/{id}/suggest                 # suggested questions
GET    /api/v1/chunks/{chunk_id}                      # source viewer
POST   /api/v1/conversations
GET    /api/v1/conversations/{id}/messages
POST   /api/v1/chat                                   # streamed (SSE) answer + citations
POST   /api/v1/feedback
GET    /api/v1/admin/metrics
GET    /api/v1/admin/logs
```

## Configuration (env vars)

| Variable | Default | Meaning |
|----------|---------|---------|
| `GOOGLE_API_KEY` | — | Gemini API key (required) |
| `GEMINI_MODEL` | `gemini-3.1-flash-lite` | Chat model |
| `UPLOAD_MAX_SIZE_MB` | `25` | Max upload size |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `900` / `150` | Chunking (chars) |
| `VECTOR_TOP_K` / `CONTEXT_TOP_K` | `8` / `4` | Retrieved vs. used chunks |
| `MIN_SIMILARITY` | `0.35` | Confidence gate for grounded answers |

## Design decisions (kept intentionally simple)

- **SQLite + Chroma instead of PostgreSQL/pgvector**: zero external services, single-command startup, no error-prone infra — while still demonstrating relational metadata + a real vector index. The data layer is isolated in `app/db` so moving to Postgres+pgvector is a contained change.
- **In-process background worker instead of Celery/Redis**: same async-ingestion behavior (fast upload response + a visible state machine) without a broker.
- **Provider interfaces**: `app/providers/base.py` defines vendor-neutral contracts; Gemini is one implementation.

## Known limitations / future work

- Single-tenant (no auth/multi-tenancy) — the schema is structured to add it.
- Semantic (vector) retrieval only; hybrid search + a dedicated reranker are natural next steps.
- Move persistence to Postgres+pgvector and the worker to Celery/Redis for horizontal scale.
- Add an automated RAG evaluation suite (Recall@K, groundedness, citation correctness).
