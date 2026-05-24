from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    chat,
    connectors,
    dev,
    events,
    health,
    ingest,
    playbooks,
    search,
    tasks,
)
from app.core.config import get_settings
from app.core.logging import setup_logging


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
app.include_router(events.router)
app.include_router(search.router)
app.include_router(chat.router)
app.include_router(tasks.router)
app.include_router(playbooks.router)
app.include_router(connectors.router)
app.include_router(dev.router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "app": settings.app_name,
        "status": "running",
        "docs": "/docs",
    }
