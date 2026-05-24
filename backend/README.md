# MindOS Backend

MindOS is a local-first personal AI operating system for developers. This backend is the foundation for future local ingestion, search, chat, analysis, reporting, and safe task execution.

## Current Scope

This step creates a clean FastAPI backend structure with:

- App configuration through `pydantic-settings`
- Standard Python logging setup
- CORS for the future local frontend
- Health and placeholder API routes
- Lightweight domain models and enums
- Abstract repository, LLM, vector store, tool, and connector interfaces
- In-memory placeholder repositories and vector store
- Mock tools for email, Jira, and GitHub

## Intentionally Not Implemented Yet

This backend does not include:

- Frontend UI
- PostgreSQL
- SQLite
- ChromaDB
- Ollama or real LLM providers
- Real GitHub, Jira, email, browser, VSCode, file watcher, or log integrations
- Real ingestion, search, chat, task execution, or playbook workflows

The current implementation is designed to make those additions safer later without mixing business logic into route files.

## Setup

```powershell
cd mindos/backend
uv venv
.venv\Scripts\activate
uv pip install -r requirements.txt
copy .env.example .env
```

If you use a regular Python install instead of `uv`, run:

```powershell
cd mindos/backend
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
copy .env.example .env
```

On macOS or Linux, activate the virtual environment with:

```bash
source .venv/bin/activate
```

## Run

From an activated virtual environment:

```powershell
python -m uvicorn app.main:app --reload
```

Or run directly with `uv`:

```powershell
uv run --with-requirements requirements.txt uvicorn app.main:app --reload
```

If Windows reports `[WinError 10013]` when binding the socket, use an explicit localhost host and a different port:

```powershell
uv run --with-requirements requirements.txt uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

If `uvicorn app.main:app --reload` is not recognized, it means `uvicorn` is not installed globally or your virtual environment is not activated.

```bash
uvicorn app.main:app --reload
```

## Test Endpoints

After starting the server, open:

- `GET http://127.0.0.1:8000/`
- `GET http://127.0.0.1:8000/health`
- `GET http://127.0.0.1:8000/ingest`
- `GET http://127.0.0.1:8000/events`
- `GET http://127.0.0.1:8000/search`
- `GET http://127.0.0.1:8000/chat`
- `GET http://127.0.0.1:8000/tasks`
- `GET http://127.0.0.1:8000/playbooks`
- `GET http://127.0.0.1:8000/connectors`
- `GET http://127.0.0.1:8000/dev`
- `GET http://127.0.0.1:8000/docs`
