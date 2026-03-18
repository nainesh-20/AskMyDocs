import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.db.qdrant import init_collection
from app.api.auth import router as auth_router
from app.api.documents import router as documents_router
from app.api.query import router as query_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting up — env=%s", settings.environment)
    await init_collection()
    logger.info("Qdrant collection ready")
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="AskMyDocs API",
    description="Production-grade private RAG with multi-tenant isolation and confidence-aware retrieval",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "type": type(exc).__name__,
        },
    )


app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(query_router)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "environment": settings.environment}
