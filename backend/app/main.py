from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    chat,
    connectors,
    context,
    dev,
    embeddings,
    events,
    health,
    ingest,
    models,
    playbooks,
    search,
    tasks,
)
from app.core.config import get_settings
from app.core.database import get_database_path, initialize_database
from app.core.logging import setup_logging
import logging


setup_logging()
settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(ingest.router)
app.include_router(models.router)
app.include_router(embeddings.router)
app.include_router(events.router)
app.include_router(search.router)
app.include_router(chat.router)
app.include_router(tasks.router)
app.include_router(playbooks.router)
app.include_router(connectors.router)
app.include_router(context.router)
app.include_router(dev.router)


@app.on_event("startup")
def startup() -> None:
    logger = logging.getLogger(__name__)
    if settings.storage_backend.lower() == "sqlite":
        initialize_database()
        logger.info("MindOS storage initialized", extra={"storage": "sqlite", "database_path": str(get_database_path())})
    else:
        logger.info("MindOS storage initialized", extra={"storage": "memory"})


@app.get("/")
def root() -> dict[str, str]:
    return {
        "app": settings.app_name,
        "status": "running",
        "docs": "/docs",
    }
