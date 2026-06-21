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
    mcp,
    models,
    playbooks,
    search,
    tasks,
)
from app.core.config import get_settings
from app.core.database import get_database_path, initialize_database
from app.core.logging import setup_logging
from app.services.file_index_scheduler_service import file_index_scheduler_service
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
app.include_router(mcp.router)


@app.on_event("startup")
def startup() -> None:
    logger = logging.getLogger(__name__)
    if settings.storage_backend.lower() == "sqlite":
        initialize_database()
        logger.info("MindOS storage initialized", extra={"storage": "sqlite", "database_path": str(get_database_path())})
    else:
        logger.info("MindOS storage initialized", extra={"storage": "memory"})
    file_index_scheduler_service.start()

    from app.services.page_summary_worker_service import page_summary_worker_service
    page_summary_worker_service.start()

    # Register MCP servers
    from app.integrations.mcp.client import mcp_client
    from app.integrations.mcp.file_system_server import file_system_mcp_server
    from app.services.mcp_config_service import mcp_config_service
    from app.services.mcp_file_watch_service import mcp_file_watch_service

    mcp_client.register_server(file_system_mcp_server.SERVER_ID, file_system_mcp_server)
    filesystem_config = mcp_config_service.get_filesystem_config()
    mcp_client.update_server_config(file_system_mcp_server.SERVER_ID, filesystem_config)
    # File System MCP starts enabled by default
    mcp_client.enable_server(file_system_mcp_server.SERVER_ID)
    logger.info("MCP File System server registered and enabled", extra={"mcp_server": "filesystem", "tools": len(file_system_mcp_server.list_tools())})
    if filesystem_config.get("root_path"):
        mcp_file_watch_service.start_for_config()

    from app.integrations.mcp.gmail_server import gmail_mcp_server
    mcp_client.register_server(gmail_mcp_server.SERVER_ID, gmail_mcp_server)
    mcp_client.enable_server(gmail_mcp_server.SERVER_ID)
    logger.info("MCP Gmail server registered and enabled", extra={"mcp_server": "gmail", "tools": len(gmail_mcp_server.list_tools())})


@app.on_event("shutdown")
def shutdown() -> None:
    from app.services.mcp_file_watch_service import mcp_file_watch_service

    mcp_file_watch_service.stop()


@app.get("/")
def root() -> dict[str, str]:
    return {
        "app": settings.app_name,
        "status": "running",
        "docs": "/docs",
    }
