# AskMyDocs — The Full Engineering Story

> *From a blank directory to a live, production-deployed RAG system. Every architectural decision, every bug, every fix — told from the perspective of the engineer who built it.*

---

## The Problem Statement

The goal was to build a portfolio-quality AI engineering project that demonstrates real-world system design, not just a Jupyter notebook that calls the OpenAI API. The requirement was specific: a **multi-tenant, private RAG (Retrieval-Augmented Generation) system** where each user's documents are completely isolated from other users. Upload a PDF, ask questions about it, get cited answers.

The name: **AskMyDocs**.

The constraint that shaped every decision: this had to be production-grade, not a demo. That means auth, data isolation, async processing, graceful error handling, deployable infrastructure, and a real frontend.

---

## Architecture: The Decisions That Mattered

Before writing a single line of code, the architecture needed to be locked in. The choices here compound — a bad foundation means paying the cost forever.

### Why FastAPI, not Flask or Django?

Flask is synchronous by default. Django carries too much convention for an API-only service. FastAPI gives you:

1. **Native async/await** — critical because every I/O operation in this system (database, storage, vector DB, LLM) is a network call. Blocking any of them blocks the entire process.
2. **Pydantic validation built in** — request bodies are validated and typed automatically. No manual `request.json.get("field")` with `None` checks.
3. **Automatic OpenAPI docs** — the Swagger UI at `/docs` was free, which mattered for debugging and demonstrating the API.
4. **Dependency injection** — the `Depends()` pattern made auth clean. Every protected endpoint gets `current_user: dict = Depends(get_current_user)` injected automatically. No middleware spaghetti.

### Why Qdrant over pgvector?

This was the most scrutinized decision. pgvector is the obvious answer — you already have PostgreSQL, so why add another database?

The answer is **multi-tenant filtering**. Every Qdrant search in this system includes a mandatory filter:

```python
query_filter=Filter(
    must=[
        FieldCondition(
            key="user_id",
            match=MatchValue(value=user_id),
        )
    ]
)
```

With pgvector, this would be a SQL `WHERE` clause joining vector similarity with a user_id condition. That's fine at small scale, but it means your vector index is shared — you're relying on the query planner to efficiently combine vector ANN search with row-level filtering. Qdrant indexes payload fields separately and filters *before* ANN search, meaning the search space is already narrowed to the current user's vectors before cosine similarity is computed. It's a fundamental architectural difference.

The second reason: keeping vector data and relational data separated is cleaner. PostgreSQL stores document metadata (status, filename, timestamps). Qdrant stores embeddings. Each system does what it's designed for.

### Why FastEmbed over OpenAI Embeddings?

Three reasons:

1. **No data egress.** For a system called "private RAG," sending user documents to OpenAI's API is a contradiction. FastEmbed runs the ONNX-optimized `bge-small-en-v1.5` model locally — the data never leaves your server.
2. **Zero API cost.** At scale, embedding costs add up. Local inference is free after the initial model download.
3. **Determinism.** The same text always produces the same embedding. OpenAI can silently change their models.

The tradeoff: the model (~130MB) has to live in memory. This became the biggest production problem we'll cover later.

### Why BackgroundTasks over Celery?

Celery requires Redis or RabbitMQ as a message broker, plus a separate worker process. That's three services instead of one. FastAPI's built-in `BackgroundTasks` runs the ingestion function in the same process after the response is sent. The upload endpoint returns `202 Accepted` immediately:

```python
background_tasks.add_task(
    process_pdf_and_index,
    doc_id=str(doc_id),
    storage_path=storage_path,
    user_id=user_id,
    filename=file.filename,
)

return UploadResponse(
    id=doc_id,
    filename=file.filename,
    status="pending",
    message="Document uploaded. Processing started in background.",
)
```

The UI polls `/documents/{id}/status` every 3 seconds until the status changes from `pending` → `processing` → `indexed`. The function signature was designed deliberately so that swapping to Celery later is a decorator change, not a logic rewrite.

### The Confidence-Aware Retrieval Design

This is the detail that separates this project from "just another RAG demo." The most common RAG failure mode is **confident hallucination from irrelevant context** — the LLM receives low-relevance chunks and fabricates a plausible-sounding answer.

The solution: check the cosine similarity score before deciding what to do with the LLM:

```python
top_score = chunks[0]["score"]

if top_score >= settings.confidence_threshold:      # 0.75
    answer = call_groq(body.question, chunks)
    return QueryResponse(mode="answer", answer=answer, sources=sources)

if top_score >= settings.no_match_threshold:        # 0.45
    answer = call_groq(body.question, chunks)
    return QueryResponse(mode="low_confidence", answer=answer, sources=sources, warning=...)

# Below 0.45 — skip the LLM entirely
return QueryResponse(mode="no_match", ...)
```

Three modes. The UI renders them differently: green card for high confidence, yellow with a warning for low confidence, red with "no relevant information found" when the LLM is skipped entirely. The LLM is only called when there's meaningful context to work with.

---

## The Data Model

One table. One collection. That's it.

**PostgreSQL `documents` table** (via SQLAlchemy ORM + Alembic migrations):

```python
class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID]           # primary key
    user_id: Mapped[str]            # Supabase auth user ID, indexed
    filename: Mapped[str]
    storage_path: Mapped[str]       # path in Supabase Storage
    status: Mapped[str]             # pending / processing / indexed / failed
    chunk_count: Mapped[int]        # how many vectors were created
    error_message: Mapped[str|None] # populated if status=failed
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
```

**Qdrant collection `rag_documents`** — each point represents one text chunk:

```json
{
  "id": "uuid",
  "vector": [384 floats],
  "payload": {
    "user_id": "...",
    "doc_id": "...",
    "filename": "report.pdf",
    "page": 3,
    "chunk_text": "The company revenue grew by..."
  }
}
```

The `user_id` in Qdrant's payload is what enforces tenant isolation at the vector layer. Even if there were a bug in the API layer, a user could never retrieve another user's chunks because the filter is applied at the database level.

---

## The Ingestion Pipeline

This is the core of the system. A 5-stage pipeline that runs asynchronously after every upload:

```
PDF bytes → Text extraction (PyMuPDF) → Chunking (LangChain) → Embedding (FastEmbed) → Upsert (Qdrant) → Status update (PostgreSQL)
```

### Why PyMuPDF for extraction?

It's the fastest Python PDF library available, handles complex layouts, and crucially — it gives you **page numbers**. Every chunk preserves its source page, which powers the citation feature. When the LLM answers a question, the UI shows "Page 12 of annual-report.pdf" next to every source. That's only possible because the ingestion pipeline tracks provenance at every step.

### Chunking strategy

`RecursiveCharacterTextSplitter` with `chunk_size=512` and `chunk_overlap=50`. The separator hierarchy `["\n\n", "\n", ". ", " ", ""]` means it tries to split on paragraph boundaries first, then sentences, then words. The overlap ensures context isn't lost at chunk boundaries — the last 50 characters of one chunk appear at the start of the next, so a sentence split across a boundary isn't semantically broken.

### Batched upserts

Qdrant upserts are batched at 100 points per request. A long document might produce 300+ chunks. Sending them all in one HTTP request risks timeouts and wastes memory holding the entire list in the response buffer.

---

## The Auth System — And Where It Broke

This was the first major debugging session. The setup: Supabase Auth issues JWTs, the backend verifies them locally without a network round-trip on every request.

### The assumption that broke everything

The initial implementation assumed Supabase signs JWTs with HMAC-SHA256 (HS256) using the `SUPABASE_JWT_SECRET` as a symmetric key:

```python
# What we assumed
payload = jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"])
```

Every request returned `"Invalid authentication token"`. The JWT secret was correct. The tokens were fresh. What was wrong?

**The diagnosis method:** Decode the JWT header without verifying it to inspect the algorithm:

```python
import base64, json
header = json.loads(base64.b64decode(token.split('.')[0] + '=='))
print(header)
# {"alg": "ES256", "kid": "6ea025e6-7bf9-44cc-8b60-743676 72b4ea", "typ": "JWT"}
```

`ES256`. Not `HS256`. Supabase was using **ECDSA asymmetric signing** (Elliptic Curve Digital Signature Algorithm with P-256). The `SUPABASE_JWT_SECRET` is irrelevant for ES256 — you verify with the public key, not a shared secret.

### The fix: JWKS

Supabase publishes its public keys at a well-known endpoint:
`https://<project>.supabase.co/auth/v1/.well-known/jwks.json`

The fix was to use `PyJWKClient` to fetch and cache the public key, then verify with it:

```python
_jwks_url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
_jwks_client = PyJWKClient(_jwks_url, cache_keys=True)

def decode_jwt(token: str) -> dict:
    signing_key = _jwks_client.get_signing_key_from_jwt(token)
    payload = jwt.decode(
        token,
        signing_key.key,
        algorithms=["ES256"],
        audience="authenticated",
    )
    return payload
```

The `kid` (key ID) in the JWT header matches the key in the JWKS response — the client handles this matching automatically. The keys are cached after the first fetch, so there's no network overhead per request.

**The lesson:** Never assume the JWT signing algorithm. Always inspect the token header first. HS256 and ES256 are fundamentally different — one uses a shared secret, the other uses a public/private key pair.

---

## Storage Authentication: The RLS Trap

After auth was fixed, file uploads returned `403 Forbidden` from Supabase Storage. The bucket existed. The credentials were correct. What was wrong?

**Supabase Row Level Security (RLS).** By default, Supabase Storage buckets enforce RLS policies. Our storage client was initialized with the `SUPABASE_ANON_KEY` — the public, unprivileged key intended for browser clients. It has no storage write permission unless you explicitly create RLS policies.

The wrong approach would be to create complex RLS policies. The right approach for a backend service: use the `SUPABASE_SERVICE_ROLE_KEY`, which bypasses RLS entirely.

```python
def get_storage():
    """Create Supabase storage client with service_role key (bypasses RLS)."""
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
```

The service role key is kept server-side only — it never touches the frontend. The anon key is what the browser uses for auth. Two keys, two different privilege levels, each used where appropriate.

**Important:** We also moved the Supabase client initialization *inside* the function (lazy initialization) rather than at module level. Module-level initialization means any import of the module tries to create a Supabase client immediately — which crashes if the environment variables aren't loaded yet (a problem encountered when running Alembic migrations before the full `.env` was populated).

---

## Database Migrations: The `%` Problem

Alembic reads database configuration through Python's `configparser`. The `DATABASE_URL` contained URL-encoded characters — the password `Nash@dev@20` becomes `Nash%40dev%4020` when `@` is percent-encoded.

`configparser` uses `%` as an interpolation character (for `%(variable)s` style substitution). A literal `%40` in the URL caused:

```
ValueError: invalid interpolation syntax in 'postgresql+asyncpg://postgres:Nash%40dev%4020@...' at position 34
```

The fix is mechanical but non-obvious:

```python
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
```

Double `%%` escapes the percent sign for `configparser`. The actual SQLAlchemy connection (in `run_async_migrations`) receives the original unescaped URL — `configparser` interpolation doesn't apply there.

---

## Qdrant Client Version Mismatch: Two Bugs for the Price of One

After the full system was running locally, queries returned 500 errors. Checking the logs:

```
AttributeError: 'QdrantClient' object has no attribute 'search'
```

**Root cause:** We had upgraded the `qdrant-client` package from `1.13.2` to `1.17.1` to match the server version. In the 1.17 release, Qdrant removed the legacy `.search()` method and replaced it with the more powerful `.query_points()`:

```python
# Old API (removed in 1.17)
results = qdrant_client.search(
    collection_name=...,
    query_vector=embedding,
    ...
)
for hit in results:  # results was a flat list

# New API (1.17+)
response = qdrant_client.query_points(
    collection_name=...,
    query=embedding,      # parameter renamed too
    ...
)
for hit in response.points:  # now wrapped in a response object
```

Two changes: method name and result structure. Straightforward to fix once identified.

**The second bug that came with it:** After switching to `query_points`, a new error appeared:

```
400 Bad Request: Index required but not found for "user_id" of one of the following types: [keyword, uuid].
Help: Create an index for this key or use a different filter.
```

Qdrant 1.17 made **payload indexes mandatory for filtered search**. Previously you could filter on any payload field without an index — Qdrant would do a brute-force scan. In 1.17, filtered searches on unindexed fields are rejected outright.

The fix: create keyword indexes on `user_id` and `doc_id` during application startup, in the `init_collection()` lifespan function:

```python
for field, schema_type in [
    ("user_id", PayloadSchemaType.KEYWORD),
    ("doc_id", PayloadSchemaType.KEYWORD),
]:
    try:
        qdrant_client.create_payload_index(
            collection_name=settings.qdrant_collection_name,
            field_name=field,
            field_schema=schema_type,
        )
    except Exception:
        pass  # index already exists on subsequent startups
```

This is idempotent — calling `create_payload_index` on an existing index is a no-op (or throws a benign exception we swallow). The indexes are created on first start and silently skipped on every subsequent start.

**The lesson:** When upgrading a client library to match a server version, read the changelog. Breaking API changes in data infrastructure clients are common and silent.

---

## Deployment: Every Problem, In Order

### Problem 1: Python 3.14 on Render

Render defaulted to Python 3.14 (the latest available). The build failed:

```
py-rust-stemmers-0.1.5.tar.gz — building from source...
error: failed to create directory /usr/local/cargo/registry/cache/...
Caused by: Read-only file system (os error 30)
```

`py-rust-stemmers` is a dependency of `fastembed` that's written in Rust. Pre-built wheels only exist for Python up to 3.13. On Python 3.14, pip falls back to building from source — which requires Cargo (Rust's build tool) — which tries to write to a read-only filesystem on Render.

Fix: a `.python-version` file in the repo root:

```
3.11.9
```

Render respects this file and uses Python 3.11, for which all pre-built wheels exist.

### Problem 2: Wrong start command + Out of Memory

The first successful build still failed at runtime:

```
==> Running 'uvicorn app.main:app --reload'
==> No open ports detected, continuing to scan...
==> Out of memory (used over 512Mi)
```

Two problems:

**Wrong start command:** Render wasn't reading `render.yaml` because the service had been configured manually through the dashboard first. The manual configuration defaulted to `--reload` (development mode), which binds to `127.0.0.1` — invisible to Render's port scanner. Fixed by updating the start command in the Render dashboard to `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

**Out of memory:** The embedding model was being instantiated at module-level in *two separate files*:

```python
# ingestion.py — loaded on startup
embedding_model = TextEmbedding("BAAI/bge-small-en-v1.5")

# retrieval.py — also loaded on startup
embedding_model = TextEmbedding("BAAI/bge-small-en-v1.5")
```

Each `TextEmbedding(...)` call downloads the model, initializes onnxruntime, and loads ~130MB of weights into memory. Two instances = ~260MB of model memory alone, before accounting for Python runtime (~50MB), onnxruntime libraries (~200MB), and all other dependencies.

Total startup memory on Render's 512MB free tier: **~550MB → crash.**

### The Singleton Fix

The solution: a dedicated `app/services/embeddings.py` module with a single lazy-loaded instance:

```python
from functools import lru_cache
from fastembed import TextEmbedding

MODEL_NAME = "BAAI/bge-small-en-v1.5"

@lru_cache(maxsize=1)
def get_embedding_model() -> TextEmbedding:
    """Return the shared TextEmbedding singleton, loading it on first call."""
    logger.info("Loading embedding model: %s", MODEL_NAME)
    return TextEmbedding(MODEL_NAME)
```

`@lru_cache(maxsize=1)` is Python's standard library memoization decorator. The first call to `get_embedding_model()` constructs and caches the `TextEmbedding` instance. Every subsequent call returns the same cached object — no new allocation.

The critical word is **lazy**: the model is *not* loaded at import time. It's loaded on the first actual embed call — which only happens when a user uploads a document or runs a query. Server startup memory dropped from ~550MB to ~270MB, well within the 512MB limit.

Both `ingestion.py` and `retrieval.py` now import `get_embedding_model` from this shared module, ensuring there's only ever one model instance in memory regardless of which code path triggers it first.

### Problem 3: Database Unreachable from Render

After fixing memory and the start command, uploads returned 500 errors with:

```
OSError: [Errno 101] Network is unreachable
```

The `DATABASE_URL` was `postgresql+asyncpg://postgres:...@db.qbfhyjivlaxxfognwdni.supabase.co:5432/postgres`.

The direct Supabase database hostname (`db.<project>.supabase.co`) uses infrastructure-level routing that only resolves correctly from certain network environments. From Render's AWS infrastructure, the DNS resolution fails.

The fix: Supabase's **connection pooler**, which is designed for external services and resolves from anywhere:

```
postgresql+asyncpg://postgres.qbfhyjivlaxxfognwdni:[PASSWORD]@aws-0-us-east-1.pooler.supabase.com:5432/postgres
```

Note the changed username format: `postgres.qbfhyjivlaxxfognwdni` (project ref appended) and hostname `aws-0-<region>.pooler.supabase.com`. This is Supabase's session pooler, which maintains persistent connections and handles routing correctly from external cloud providers.

### Problem 4: CORS

After deploying the frontend to Vercel (`askmydocsbynainesh.vercel.app`), all API calls failed. A CORS preflight check confirmed the issue — `Access-Control-Allow-Origin` was absent in the response.

The FastAPI CORS middleware reads from `ALLOWED_ORIGINS`, which was set to `http://localhost:3000` during development. The Vercel URL wasn't there.

Fix: updating the Render environment variable:

```
ALLOWED_ORIGINS=https://askmydocsbynainesh.vercel.app,http://localhost:3000
```

After the Render redeploy, verification showed all required CORS headers:

```
access-control-allow-origin: https://askmydocsbynainesh.vercel.app
access-control-allow-credentials: true
access-control-allow-methods: DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT
access-control-allow-headers: Authorization, Content-Type
```

---

## The Frontend Architecture

Next.js App Router with TypeScript and Tailwind. The decision to use Next.js over a plain React SPA came down to Supabase's SSR helpers — the `@supabase/ssr` package is designed for Next.js and handles session persistence in server components and middleware correctly.

### Route protection

A `middleware.ts` intercepts every request before the page renders. It reads the Supabase session from cookies (not localStorage — SSR-compatible) and redirects unauthenticated users to `/login` before any protected page even begins loading. This is the correct pattern for Next.js Auth — not a client-side `useEffect` check that flashes the protected page before redirecting.

### The polling pattern

The dashboard polls document status every 3 seconds for any document in `pending` or `processing` state:

```typescript
useEffect(() => {
    const pendingDocs = documents.filter(
      (d) => d.status === "pending" || d.status === "processing"
    );
    if (pendingDocs.length === 0) return;

    const interval = setInterval(async () => {
      for (const doc of pendingDocs) {
        const updated = await getDocumentStatus(doc.id);
        if (updated.status !== doc.status) {
          setDocuments((prev) =>
            prev.map((d) => d.id === doc.id ? { ...d, ...updated } : d)
          );
        }
      }
    }, 3000);

    return () => clearInterval(interval);  // cleanup on unmount
  }, [documents]);
```

The cleanup function is critical — if the component unmounts (user navigates away) while polling is active, the interval is cleared. Without this, you get a memory leak and `setState` calls on unmounted components.

### The four document statuses

`pending` → `processing` → `indexed` / `failed`

`pending` means the upload succeeded and the background task is queued. `processing` means the background task has started (download + extract phase). This distinction matters for the UI — a spinner with "Queued" vs "Processing..." communicates different things to the user. The `StatusBadge` component handles all four states with distinct visual treatments.

---

## Free Tier Limit: A Product Decision Encoded in Code

The 3-document limit isn't just a business rule — it's a safety valve for the infrastructure. A single user uploading 50 large PDFs would exhaust Qdrant's 1GB free cluster, fill Supabase Storage, and spike Groq API usage.

The limit is enforced at two levels:

**Backend (authoritative):** The upload endpoint counts existing documents before accepting new ones:

```python
doc_count = await db.scalar(
    select(func.count()).where(Document.user_id == user_id)
)
if doc_count >= settings.max_documents_per_user:
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Free tier limit reached ({settings.max_documents_per_user} documents). Check back when we scale up!",
    )
```

`429 Too Many Requests` is the correct HTTP status for rate/quota limits.

**Frontend (UX):** The `GET /documents` response includes `max_documents` and `remaining` fields. The dashboard renders a progress bar and, when the limit is reached, replaces the upload zone with a locked state message. This prevents the round trip of attempting an upload that will fail — better UX, fewer unnecessary API calls.

The limit is configured via `MAX_DOCUMENTS_PER_USER` env var, defaulting to 3. Increasing it in production is a one-line environment variable change, no code deployment needed.

---

## The git Problem Nobody Talks About

When initializing the git repo, `git add .` warned about an embedded git repository in `frontend/`. This is because `create-next-app` initializes its own `.git` directory. Pushing this as a submodule means GitHub would show the frontend directory as a linked repo with no contents — the source files would be invisible.

Fix:

```bash
git rm --cached -f frontend  # remove from staging
rm -rf frontend/.git         # delete the embedded git history
git add frontend             # re-add as regular directory
```

A subtle trap that would have resulted in an empty frontend directory on GitHub.

---

## The Numbers

| Metric | Value |
|--------|-------|
| Total files | 62 |
| Backend Python files | 19 |
| Frontend TypeScript/TSX files | 15 |
| API endpoints | 8 |
| Database tables | 1 |
| Vector collection | 1 |
| Embedding dimensions | 384 |
| Chunk size | 512 tokens |
| Chunk overlap | 50 tokens |
| Confidence threshold | 0.75 cosine similarity |
| No-match threshold | 0.45 cosine similarity |
| Free tier document limit | 3 |
| Monthly infrastructure cost | $0 (all free tiers) |

---

## What I'd Do Differently in V2

**Celery + Redis for ingestion.** FastAPI `BackgroundTasks` runs in the same process and shares the same memory limit. A large PDF ingestion eating 300MB during processing on Render's 512MB instance will cause OOM. A separate Celery worker process has its own memory budget.

**Qdrant per-tenant collections.** Currently all users share one collection, with `user_id` filtering enforcing isolation. True isolation would give each user their own collection — making deletion trivial, making per-user memory usage trackable, and eliminating any risk of filter bugs leaking cross-tenant data.

**Hybrid search.** Dense vector search (what we have) is excellent for semantic similarity. BM25 keyword search (what we don't have) is better for exact terms, names, and codes. A weighted combination of both — hybrid search — consistently outperforms either alone on real-world document QA tasks.

**Streaming responses.** The query endpoint currently waits for the full Groq completion before returning. With streaming, the frontend could display tokens as they arrive. On slower connections this is the difference between "is it broken?" and "it's thinking."

---

## Key Interview Talking Points

- **Why 202 instead of 200 on upload?** Because the work isn't done. `200 OK` means the request completed successfully. `202 Accepted` means "I received it, I'll process it, but I'm not done yet." Using the wrong status code would be semantically incorrect and would mislead any client about the actual system state.

- **How does tenant isolation work?** Two layers. The API layer extracts `user_id` from the verified JWT and passes it to every query. The Qdrant layer enforces a mandatory filter on `user_id` in every vector search — so even if there were an API bug, a user could never retrieve another user's vectors.

- **Why not just use one big LLM call instead of RAG?** Context window cost and staleness. You can't fit 100 PDFs into a context window economically, and you'd have to re-upload everything when new documents arrive. RAG lets you retrieve the relevant 5 chunks from thousands of documents in milliseconds.

- **What's the failure mode when the LLM is unavailable?** The `call_groq` function raises an exception that propagates up to the query endpoint's try/except, which returns a 500. This could be improved with a fallback — but the confidence-aware design means the `no_match` mode already skips the LLM for low-relevance queries, reducing the blast radius of LLM outages.

- **Why `lru_cache` for the embedding model singleton?** `lru_cache(maxsize=1)` is Python's standard memoization decorator. It wraps the function and caches the return value after the first call. `maxsize=1` means it caches exactly one result (the first call's return value). It's thread-safe and requires no external dependencies. The alternative — a global variable — achieves the same thing but is more fragile and harder to test.

---

*Built entirely in Cursor. Deployed on Render (backend) and Vercel (frontend). Live at [askmydocsbynainesh.vercel.app](https://askmydocsbynainesh.vercel.app).*

*GitHub: [github.com/nainesh-20/AskMyDocs](https://github.com/nainesh-20/AskMyDocs)*
