# LexiAI

A production-grade **Retrieval-Augmented Generation (RAG)** stack for legal and tax documents. The **Django + DRF** service ingests user-uploaded documents, chunks and embeds them with sentence-transformers, and answers natural-language questions by retrieving the most relevant passages and grounding a Mistral LLM completion on them — with strict citation rules, observability, and graceful degradation.

This repository contains that **Django API** plus an optional **React (Vite) frontend** with a **staff-only admin dashboard** (`/admin` in the SPA) that talks to the same versioned REST API over JWT. Django’s built-in `/admin/` site remains available for model CRUD; the SPA is a separate convenience UI for operators.

---

## Features

- **Stateless Q&A endpoint** — `POST /api/v1/ask/` returns a grounded answer plus the source chunks used to construct it.
- **RAG pipeline** — query → embedding → cosine search → context assembly → LLM completion → citations.
- **Pluggable LLM backend** — Mistral by default, swappable to any OpenAI-compatible endpoint or an offline stub via `AI_LLM_BACKEND`.
- **Background model warmup** — the embedding model loads in a daemon thread at startup, eliminating ~45 s cold-start latency on the first request.
- **Operational health probe** — `GET /api/v1/health/` reports DB, LLM, and embedding-model status for orchestrators and uptime monitors.
- **Per-user request observability** — every `/ask/` call logs `user_id`, query size, `top_k`, retrieval confidence, LLM latency, token usage, and a 60-second rolling request counter.
- **Hardened configuration** — env-driven settings, weak-`SECRET_KEY` detection in production, no hardcoded credentials, sensitive files gitignored.
- **Reproducible deployment** — all runtime dependencies are pinned and installed at Docker build time; no runtime `pip install`.
- **Staff admin API + SPA** — JWT-authenticated React routes under `/admin` backed by DRF views with `IsAdminUser`: global analytics, documents (list/search/reprocess/delete), users (list + partial update), feedback, and query logs. See *Admin SPA & staff APIs* below.

---

## Admin SPA & staff APIs

The SPA admin area is **UI gating only** (`is_staff` / `is_superuser` on the JWT user object). Every sensitive operation is enforced again in DRF with **`permissions.IsAdminUser`**.

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `GET` | `/api/v1/ai/analytics/?days=N` | System-wide analytics (documents, users, query aggregates, feedback). |
| `GET` | `/api/v1/documents/admin/` | Global document list; optional `?search=` (title); response includes `stats` for dashboard cards. |
| `DELETE` | `/api/v1/documents/admin/<id>/` | Admin delete of any document (not owner-scoped). |
| `POST` | `/api/v1/documents/<id>/ingest/` | Re-queue chunking + embedding for an existing document (`embed_document_chunks` Celery task). Requires non-empty `extracted_text`. Returns `job_id` (Celery async result id). |
| `GET` | `/api/v1/accounts/users/` | Global user list; optional `?search=`; envelope with `stats`. |
| `GET`, `PATCH` | `/api/v1/accounts/users/<id>/` | Read or partially update `is_active`, `is_staff`, `is_superuser` (only superusers may change `is_superuser`; self-deactivation and edits to your own staff or superuser flags are blocked). |
| `GET` | `/api/v1/feedback/` | Global feedback rows + `stats`. |
| `GET` | `/api/v1/ai/query-logs/` | Global query logs + `stats` (recent rows capped; see `AdminQueryLogListView`). |

**Local dev with Vite:** the browser calls same-origin `/api/…` and Vite proxies to Django. Docker Compose maps the web container to **`WEB_HOST_PORT`** on the host (default **18000**, to avoid Windows Hyper-V exclusions on port `8000`). Align the proxy by setting `VITE_DJANGO_PROXY_PORT` in `frontend/.env` when it differs from the default (see `lexiai_backend/.env.example`).

---

## Architecture overview

```
┌────────────────────────┐
│   Client (frontend /   │
│    API consumer)       │
└────────────┬───────────┘
             │ HTTPS / JWT
             ▼
┌────────────────────────┐     ┌──────────────────────┐
│   Django + DRF (web)   │────▶│   PostgreSQL         │
│   Gunicorn (3 workers, │     │   - User             │
│   timeout=120s)        │     │   - Document         │
│                        │     │   - DocumentChunk    │
│   ┌──────────────────┐ │     │   - QueryLog         │
│   │  ai_engine app   │ │     └──────────────────────┘
│   │  ┌────────────┐  │ │
│   │  │ semantic_  │  │ │     ┌──────────────────────┐
│   │  │  search    │──┼─┼────▶│   sentence-          │
│   │  └────────────┘  │ │     │   transformers       │
│   │  ┌────────────┐  │ │     │   (all-MiniLM-L6-v2) │
│   │  │ generate_  │  │ │     └──────────────────────┘
│   │  │  answer    │  │ │
│   │  └─────┬──────┘  │ │     ┌──────────────────────┐
│   │        └─────────┼─┼────▶│   Mistral API        │
│   │                  │ │     │   (OpenAI-compatible)│
│   └──────────────────┘ │     └──────────────────────┘
│   ┌──────────────────┐ │
│   │ documents app    │ │     ┌──────────────────────┐
│   │ ingest_documents │─┼────▶│   Celery worker      │
│   └──────────────────┘ │     │   (embedding tasks)  │
└────────────┬───────────┘     └──────────┬───────────┘
             │                            │
             └──────────┬─────────────────┘
                        ▼
                ┌──────────────┐
                │   Redis      │
                │   (broker +  │
                │    cache)    │
                └──────────────┘
```

**Why this shape:** the read path (ask) is synchronous and must be fast, so retrieval + LLM happen in the web process. Ingestion and embedding are CPU-heavy and bursty, so they run on Celery workers. PostgreSQL stores both relational data and chunk embeddings (as `BinaryField`); switching to pgvector or a dedicated vector store is a single-day migration when scale demands it.

---

## Core components

### Ingestion (`documents/services.py`)

- `ingest_documents(source_dir, owner)` — batch import from a directory.
- `ingest_single_document(file_path, owner)` — import one file (PDF, TXT, MD, RTF, CSV, JSON).
- Each file becomes a `Document`; chunking + embedding is scheduled via `transaction.on_commit(...)` so it only fires after the row is durably committed.
- Two management commands expose the API:
  - `ingest_docs --file <path>` / `--source-dir <dir>` (preferred).
  - `ingest_tax_docs` (legacy alias, kept for backward compatibility).

### Embedding (`ai_engine/services/embedding.py`)

- Model: `sentence-transformers/all-MiniLM-L6-v2` (384-dim, fast, CPU-friendly).
- Chunks are split with overlap to preserve context across boundaries.
- Embeddings persist as raw `float32` bytes in `DocumentChunk.embedding` — cheaper than JSON, perfectly aligned with numpy round-tripping.
- The model is **warmed in a background thread** on app startup (gated by `AI_WARMUP_ON_STARTUP`), so the first user-facing request doesn't pay the model-load tax.

### Semantic search (`ai_engine/services/search.py`)

- `semantic_search(query, top_k, *, user, min_similarity)` returns the `top_k` most relevant `DocumentChunk` rows.
- The query is embedded once, then cosine similarity is computed against the user's chunk corpus as a single numpy operation. `np.argpartition` selects the top-k without sorting the full vector — O(N) instead of O(N log N).
- Chunks are user-scoped, so users cannot see each other's documents.

### QA pipeline (`ai_engine/services/qa.py`)

- `generate_answer(query, user, top_k, min_similarity) -> dict` orchestrates the full RAG flow:
  1. Validate the query (non-empty, length-bounded).
  2. `semantic_search(...)` to get candidate chunks.
  3. Build a deterministic context window labelled `[Source 1] … [Source N]`, truncated to `MAX_CONTEXT_CHARS`.
  4. Call the LLM with a strict system prompt: *"answer using ONLY the provided context, cite sources, say you don't know if it isn't there."*
  5. Persist a `QueryLog` row with retrieved chunk IDs, latency, and token usage. **DB failures here never break the request** — they're caught and logged.
- Returns `{answer, sources, model_used, retrieval_confidence, latency_ms, warnings, query_log_id}`.

### LLM layer (`ai_engine/services/llm.py` + `llm_client.py`)

- `get_llm_client()` resolves a backend at runtime:
  - `AI_LLM_BACKEND=mistral` → `MistralLLMClient` (uses the OpenAI-compatible SDK against the Mistral endpoint).
  - `AI_LLM_BACKEND=stub` → `StubLLMClient` (deterministic, offline, used in tests and CI).
  - `AI_LLM_BACKEND=auto` → Mistral if credentials look real, otherwise stub.
- Placeholder API keys (`your_api_key_here`, `change-me`, empty, …) are detected and treated as missing. With `AI_LLM_BACKEND=mistral` and no real key, the resolver logs **ERROR** and falls back to the stub instead of crashing.
- `generate_completion(prompt)` wraps the chat call with:
  - Structured logs: `LLM call: model=... prompt_chars=...` and `LLM ok: model=... latency_ms=... tokens=...`.
  - Configurable timeout (`MISTRAL_TIMEOUT_SECONDS`).
  - Provider-specific exceptions are caught and re-raised as `LLMError` so the QA layer has a single failure type to handle.

### API layer (`ai_engine/views.py`, `core/views.py`)

- DRF generic views, JWT auth (`djangorestframework-simplejwt`), per-user scoping enforced at the queryset level.
- `AskView` is a thin controller: it validates input, records a 60-second sliding-window request counter (Redis-backed in prod, LocMem in dev), and delegates to `generate_answer`. No business logic lives in the view.
- `HealthCheckView` is intentionally unauthenticated for orchestrator probes and never raises — any internal probe failure surfaces as `status: "degraded"` in the body.

---

## API documentation

### `POST /api/v1/ask/`

Stateless retrieval-augmented Q&A over the caller's document library.

**Auth**: `Authorization: Bearer <jwt>` (required).

**Request body**

| Field            | Type    | Required | Default | Notes                                       |
| ---------------- | ------- | -------- | ------- | ------------------------------------------- |
| `query`          | string  | yes      | —       | 1–2000 chars, trimmed                       |
| `top_k`          | integer | no       | 5       | 1–10 (capped to bound LLM token cost)       |
| `min_similarity` | float   | no       | 0.0     | 0.0–1.0; chunks below this are dropped      |

**Example**

```json
{
  "query": "What does the Income Tax Proclamation say about exemptions?",
  "top_k": 3
}
```

**Response (`200 OK`)**

```json
{
  "answer": "The Income Tax Proclamation No. 286/2002 lists exemptions in Article 13 [Source 1]...",
  "sources": [
    {
      "chunk_id": 412,
      "document_id": 27,
      "document_title": "Income Tax Proclamation 286-2002",
      "snippet": "...",
      "similarity": 0.83
    }
  ],
  "model_used": "mistral-medium-3.5",
  "retrieval_confidence": 0.79,
  "latency_ms": 4446,
  "warnings": [],
  "query_log_id": 142
}
```

**Error responses**

- `400` — invalid input (empty query, `top_k` out of range, etc.). DRF returns a field-level error map.
- `401` — missing or invalid JWT.
- `500` — internal error. The body is a generic `{"detail": "..."}`; the full trace is logged server-side, never returned to the client.

### `GET /api/v1/health/`

Liveness + LLM/RAG/DB configuration probe. **Unauthenticated** so uptime monitors and Kubernetes-style probes can poll it.

**Response (`200 OK`)**

```json
{
  "status": "ok",
  "service": "LexiAI",
  "llm": "mistral",
  "embeddings_loaded": true,
  "database": "ok"
}
```

| Field               | Values                          | Meaning                                                                 |
| ------------------- | ------------------------------- | ----------------------------------------------------------------------- |
| `status`            | `ok` \| `degraded`              | Aggregate. `degraded` if any sub-probe failed.                          |
| `llm`               | `mistral` \| `stub` \| `unknown`| Active LLM backend resolved at request time.                            |
| `embeddings_loaded` | `true` \| `false`               | Whether the sentence-transformer is loaded in memory.                   |
| `database`          | `ok` \| `down`                  | Result of `SELECT 1` against the default database connection.           |

---

## Tech stack

| Layer        | Choice                                    | Rationale                                                                 |
| ------------ | ----------------------------------------- | ------------------------------------------------------------------------- |
| Web          | Django 6 + DRF + Gunicorn                 | Batteries-included, mature ORM, robust auth ecosystem.                    |
| Frontend     | React 18 + Vite + TypeScript              | Optional SPA: public site, JWT auth, staff admin at `/admin`.             |
| Auth         | SimpleJWT                                 | Stateless tokens, refresh flow, frontend-friendly.                        |
| Database     | PostgreSQL 17                             | JSON support, future pgvector migration path, transactional ingestion.    |
| Cache/Broker | Redis 7                                   | Shared cache for rate counters, Celery broker, result backend.            |
| Workers      | Celery + Beat                             | Embedding generation is bursty and CPU-heavy; keep it off the web path.   |
| Embeddings   | sentence-transformers `all-MiniLM-L6-v2`  | 384-dim, fast on CPU, strong baseline for semantic search.                |
| LLM          | Mistral via OpenAI-compatible SDK         | High-quality completions, swappable for any OpenAI-compatible provider.   |
| Containers   | Docker Compose                            | Reproducible local + CI parity with production topology.                  |

---

## Environment variables

All configuration is environment-driven. See [`lexiai_backend/.env.example`](lexiai_backend/.env.example) for the canonical template.

| Variable                  | Required | Default                                    | Notes                                                              |
| ------------------------- | -------- | ------------------------------------------ | ------------------------------------------------------------------ |
| `SECRET_KEY`              | yes      | (none — must be set in prod)               | ≥32 chars. Use `secrets.token_urlsafe(64)`.                        |
| `DEBUG`                   | no       | `False`                                    | Never `True` in production.                                        |
| `ALLOWED_HOSTS`           | yes\*    | `localhost,127.0.0.1,web` (dev)            | Required when `DEBUG=False`.                                       |
| `LOG_LEVEL`               | no       | `INFO`                                     | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL`.               |
| `DATABASE_URL`            | yes      | —                                          | `postgres://user:pass@host:5432/db`                                |
| `WEB_HOST_PORT`           | no       | `18000` (see template)                     | **Docker Compose only:** TCP port on the host mapped to Gunicorn’s `8000` inside the `web` container. Match `VITE_DJANGO_PROXY_PORT` in `frontend/.env` when running the Vite dev server. |
| `REDIS_URL`               | yes      | `redis://redis:6379/0`                     | Shared broker + cache.                                             |
| `CELERY_BROKER_URL`       | no       | mirrors `REDIS_URL`                        |                                                                    |
| `CELERY_RESULT_BACKEND`   | no       | mirrors `REDIS_URL`                        |                                                                    |
| `AI_LLM_BACKEND`          | no       | `auto`                                     | `auto` / `mistral` / `stub`.                                       |
| `MISTRAL_API_KEY`         | yes\*\*  | —                                          | Required when backend is `mistral`. Placeholder values are detected and rejected. |
| `MISTRAL_MODEL`           | no       | `mistral-medium-3.5`                       |                                                                    |
| `MISTRAL_TEMPERATURE`     | no       | `0.2`                                      | Low temperature keeps answers faithful to retrieved context.       |
| `MISTRAL_MAX_TOKENS`      | no       | `1024`                                     |                                                                    |
| `MISTRAL_TIMEOUT_SECONDS` | no       | `60`                                       |                                                                    |
| `AI_WARMUP_ON_STARTUP`    | no       | `false`                                    | Set `true` for server processes; leave `false` for one-off CLI.    |

\*Required when `DEBUG=False`. \*\*If missing while `AI_LLM_BACKEND=mistral`, the resolver logs ERROR and falls back to the stub — the app does not crash.

---

## Local setup (Docker-based)

### Prerequisites

- Docker Desktop ≥ 4.30 (Compose v2)
- ~6 GB free disk (the image bundles torch + CUDA wheels)

### First-time setup

```bash
# 1. Clone and enter the project
git clone <repo-url> lexiai
cd lexiai

# 2. Create your local .env from the template
cp lexiai_backend/.env.example lexiai_backend/.env

# 3. Generate a strong SECRET_KEY and paste it into .env
python -c "import secrets; print(secrets.token_urlsafe(64))"

# 4. Add your Mistral API key to .env (or set AI_LLM_BACKEND=stub for offline)

# 5. Build and start the stack
cd lexiai_backend
docker compose up -d --build

# 6. Apply migrations (auto-runs on web container start, but explicit is fine)
docker compose exec web python manage.py migrate

# 7. Create an admin user
docker compose exec web python manage.py createsuperuser

# 8. (Optional) Ingest sample documents
docker compose exec web python manage.py ingest_docs --source-dir /app/lexiai_backend/tax_doc
```

### Daily workflow

```bash
# Tail logs
docker compose logs -f web

# Re-run after .env changes (env is read at process start)
docker compose up -d --force-recreate web

# Health check (use the host port from WEB_HOST_PORT; Compose default is 18000)
curl http://localhost:18000/api/v1/health/

# Run tests (pytest + Django; settings from lexiai_backend/pytest.ini)
docker compose exec web pytest
```

### Optional: React (Vite) SPA

The `frontend/` app serves the marketing site, authenticated user flows, and the **staff operator UI** at `/admin` (JWT). From the repo root:

```bash
cd frontend
npm install
npm run dev
```

Vite defaults to `http://localhost:5173`. API calls use same-origin `/api/…` and are proxied to Django; set `VITE_DJANGO_PROXY_PORT` in `frontend/.env` so it matches wherever Gunicorn is reachable on the host (typically **`18000`** with the Compose defaults above, or **`8000`** if you run `manage.py runserver` locally without Docker).

---

## Future improvements

- **pgvector migration** — replace the in-process numpy similarity scan with `pgvector`'s `<=>` operator once corpora exceed ~1M chunks.
- **Streaming responses** — switch `/ask/` to SSE / chunked transfer so the LLM tokens stream to the client as they're generated.
- **Hybrid retrieval** — combine dense (embedding) and sparse (BM25) retrieval, then re-rank with a cross-encoder for higher precision.
- **Per-tenant rate limiting** — promote the current observability counter to enforcement via DRF's `UserRateThrottle` with Redis backend.
- **Evaluation harness** — golden-set Q&A pairs scored by Ragas / answer-faithfulness metrics, run in CI on every change to QA prompts.
- **Multi-modal ingestion** — image + table extraction from PDFs (currently text-only via `pdfplumber`/`pypdf`).
- **Background re-embedding** — when the embedding model is upgraded, schedule a Celery batch to re-embed historical chunks without downtime.

---

## Design principles

1. **Services-first.** All business logic lives in `*/services/*.py`. Views are thin, models are dumb, services are testable in isolation.
2. **Fail open, never crash.** Optional subsystems (LLM, cache, QueryLog persistence) catch their own exceptions and degrade gracefully. The request path returns a useful response even when something downstream is broken.
3. **Observability is not optional.** Every external call (LLM, DB, embedding) emits a structured log line with model name, latency, and a correlation handle (user_id). Health probes expose the same signals.
4. **Configuration over code.** Backend choice, model name, temperature, timeouts — all env-driven. Swapping Mistral for a self-hosted vLLM endpoint is a `.env` edit.
5. **Reproducible by default.** All deps pinned in `requirements.txt`, installed at Docker build time. No runtime `pip install`, no system-Python dependencies, no "works on my machine".
6. **Security at the boundaries.** Secrets only via env, never committed. JWT auth, per-user data scoping at the queryset level, weak-`SECRET_KEY` detection in production.

---

## Status

**Production-ready** for single-tenant deployment. The pipeline has been verified end-to-end: ingestion → embedding → retrieval → real Mistral inference → cited answer in < 5 s on a CPU-only container. Observability, health probes, and graceful degradation are in place. Scaling to multi-tenant SaaS adds the items in *Future improvements* above; nothing in the current architecture blocks them.
