# AskMyDocs

A production-grade Retrieval-Augmented Generation system with multi-tenant vector isolation, async PDF ingestion, confidence-aware retrieval that gracefully degrades instead of hallucinating, and a responsive Next.js frontend for document management and querying. Free tier limits users to 3 documents to keep costs manageable on the prototype.

## Architecture

```
CLIENT
  │
  │  Bearer JWT (issued by Supabase Auth)
  ▼
FASTAPI
  │
  ├── Verify JWT via JWKS (ES256 public key, cached after first fetch)
  │   Extract user_id from token sub claim
  │
  ├── POST /documents/upload
  │     ├── Check user document count against free tier limit (3)
  │     ├── Upload raw PDF → Supabase Storage (private bucket)
  │     ├── Insert Document record → PostgreSQL (status=pending)
  │     ├── Return 202 immediately
  │     └── BackgroundTask: process_pdf_and_index()
  │           ├── Download PDF from Supabase Storage
  │           ├── Extract text + page numbers (PyMuPDF)
  │           ├── Chunk text (RecursiveCharacterTextSplitter 512/50)
  │           ├── Embed all chunks (FastEmbed bge-small-en)
  │           ├── Upsert points to Qdrant with full payload
  │           └── Update Document status → indexed / failed
  │
  ├── GET /documents         → list user's documents + status
  ├── GET /documents/{id}/status → poll processing state
  │
  └── POST /query
        ├── Embed query (FastEmbed, same model as ingestion)
        ├── Search Qdrant (top_k=5, filter: user_id=current_user)
        ├── Check top similarity score against thresholds
        │
        ├── score >= 0.75  → mode: "answer"
        │     └── Build prompt → Groq LLM → answer + sources
        ├── score >= 0.45  → mode: "low_confidence"
        │     └── Build prompt → Groq LLM → answer + warning
        └── score < 0.45   → mode: "no_match"
              └── Skip LLM → return message + closest chunks

DATA LAYER
  ├── Supabase Storage    raw PDF files (private bucket)
  ├── PostgreSQL          document registry + status tracking
  └── Qdrant Cloud        vectors + payload (filtered by user_id)
```

## Tech Stack

| Layer | Tool | Why |
|-------|------|-----|
| API Framework | FastAPI | Async-native, Pydantic validation, auto docs |
| Auth | Supabase Auth + PyJWT (JWKS) | Production auth offloaded, ES256 public key verification |
| Database | PostgreSQL via SQLAlchemy async | Portable, industry standard |
| Migrations | Alembic | Version-controlled schema changes |
| Vector DB | Qdrant Cloud | Local filtering, HNSW, private-first |
| PDF Extraction | PyMuPDF | Fastest Python PDF library, page numbers |
| Chunking | LangChain TextSplitter | Recursive splitting, respects sentence boundaries |
| Embeddings | FastEmbed bge-small-en | Local, no data egress, ONNX-optimized |
| LLM | Groq (llama-3.1-8b-instant) | Fastest inference, free tier |
| File Storage | Supabase Storage | S3-compatible, same platform as auth/DB |
| Background Jobs | FastAPI BackgroundTasks | Zero infrastructure, upgradeable to Celery |
| Frontend | Next.js 16 + Tailwind CSS | App Router, TypeScript, SSR-ready |
| Frontend Auth | Supabase SSR | Cookie-based sessions, middleware protection |
| Deployment (API) | Render.com | Free tier, permanent URL |
| Deployment (UI) | Vercel | Zero-config Next.js hosting |

## Key Engineering Decisions

### Why Qdrant over pgvector
Qdrant provides native payload filtering (mandatory `user_id` filter on every search), HNSW indexing optimized for high-dimensional vectors, and a clean separation between document metadata (PostgreSQL) and vector embeddings. pgvector couples both into one system, making tenant isolation harder to enforce.

### Why FastEmbed over OpenAI Embeddings
FastEmbed runs locally via ONNX runtime — zero API costs, zero data egress, no network latency on embedding. The `bge-small-en-v1.5` model produces 384-dimensional vectors that perform competitively on MTEB benchmarks while being 3x smaller than `text-embedding-ada-002` output.

### Why BackgroundTasks over Celery for V1
FastAPI's built-in `BackgroundTasks` requires zero additional infrastructure (no Redis, no worker processes). The ingestion function signature is designed so that swapping to Celery later requires only changing the task decorator — no logic changes needed.

### Confidence-Aware Retrieval
Instead of blindly passing low-relevance chunks to the LLM (which causes hallucination), the API checks the top cosine similarity score against two thresholds:
- **>= 0.75**: High confidence — full LLM answer with source citations
- **>= 0.45**: Low confidence — LLM answer with explicit uncertainty warning
- **< 0.45**: No match — LLM is skipped entirely, returning only the closest chunks found

This prevents the most common RAG failure mode: confidently wrong answers from irrelevant context.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/auth/register` | Register a new user via Supabase Auth |
| `POST` | `/auth/login` | Log in and receive access token |
| `GET` | `/auth/me` | Get current user info |
| `POST` | `/documents/upload` | Upload a PDF for ingestion (returns 202, 429 if limit reached) |
| `GET` | `/documents` | List documents + usage limits for current user |
| `GET` | `/documents/{id}/status` | Poll processing status |
| `POST` | `/query` | Query documents with confidence-aware retrieval |
| `GET` | `/health` | Health check |

## Query Response Modes

### Mode: `answer` (score >= 0.75)
```json
{
  "mode": "answer",
  "answer": "According to the document, the company's revenue grew by 23% in Q3...",
  "sources": [
    {"filename": "annual-report.pdf", "page": 12, "score": 0.82, "text": "Revenue growth..."}
  ],
  "warning": null
}
```

### Mode: `low_confidence` (score >= 0.45)
```json
{
  "mode": "low_confidence",
  "answer": "Based on the available context, it appears that...",
  "sources": [...],
  "warning": "The best matching context has a relevance score of 0.52, which is below the confidence threshold."
}
```

### Mode: `no_match` (score < 0.45)
```json
{
  "mode": "no_match",
  "answer": "I couldn't find sufficiently relevant information in your documents to answer this question.",
  "sources": [...],
  "warning": null
}
```

## Local Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- Supabase project (Auth + Storage + PostgreSQL)
- Qdrant Cloud cluster
- Groq API key

### Backend

```bash
git clone https://github.com/your-username/askmydocs.git
cd askmydocs

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# Fill in your credentials

PYTHONPATH=. alembic upgrade head
uvicorn app.main:app --reload
```

API docs at `http://localhost:8000/docs` (Swagger UI).

### Frontend

```bash
cd frontend
npm install

cp .env.example .env.local
# Fill in Supabase URL, anon key, and API URL

npm run dev
```

Open `http://localhost:3000` in your browser.

### Demo Flow
1. Open `http://localhost:3000` and sign up
2. Upload a PDF on the Dashboard page
3. Watch the status badge change: Queued → Processing → Ready
4. Go to the Query page and ask a question about your document
5. See confidence-aware results: green (high), yellow (low), or red (no match)

## Deployment

### Backend (Render)
This project includes a `render.yaml` for one-click deployment:
1. Push to GitHub
2. Connect repo to Render
3. Set environment variables in the Render dashboard
4. Deploy — the API will be live at your Render URL

### Frontend (Vercel)
1. Import repo on Vercel, set Root Directory to `frontend`
2. Add environment variables: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_URL` (your Render URL)
3. Deploy
4. Add the Vercel URL to `ALLOWED_ORIGINS` in your Render env vars

## Project Structure

```
├── app/
│   ├── main.py              # FastAPI app, lifespan, middleware, routers
│   ├── config.py            # Pydantic Settings (env vars)
│   ├── api/
│   │   ├── auth.py          # /auth/* — register, login, me
│   │   ├── documents.py     # /documents/* — upload, list, status
│   │   └── query.py         # /query — confidence-aware RAG
│   ├── core/
│   │   ├── security.py      # JWKS-based JWT verification (ES256)
│   │   └── dependencies.py  # get_current_user dependency
│   ├── db/
│   │   ├── postgres.py      # SQLAlchemy async engine + session
│   │   ├── models.py        # Document ORM model
│   │   └── qdrant.py        # Qdrant client + collection init
│   ├── schemas/
│   │   ├── auth.py          # Auth request/response models
│   │   ├── documents.py     # Document schemas
│   │   └── query.py         # Query/response schemas
│   └── services/
│       ├── ingestion.py     # PDF → chunks → embeddings → Qdrant
│       ├── retrieval.py     # Query embedding + Qdrant search
│       └── llm.py           # Groq LLM prompt + completion
├── alembic/                 # Database migrations
├── frontend/
│   └── src/
│       ├── app/             # Next.js App Router pages
│       ├── components/      # React components
│       └── lib/             # Supabase client + API functions
├── requirements.txt
├── render.yaml              # Render.com deployment config
└── .env.example
```

## V2 Roadmap

- [ ] Celery + Redis for true async workers
- [ ] Hybrid search (BM25 + dense vectors)
- [ ] Table and chart extraction (OCR)
- [ ] Per-tenant Qdrant collections
- [ ] CrossEncoder re-ranking
- [ ] Response caching
- [ ] Rate limiting
- [ ] Document deletion
- [ ] Query history

## License

MIT
