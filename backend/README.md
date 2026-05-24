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
- SQLite and in-memory repository implementations
- In-memory placeholder vector store
- Mock tools for email, Jira, and GitHub

## Intentionally Not Implemented Yet

This backend does not include:

- Frontend UI
- PostgreSQL
- ChromaDB
- Ollama or real LLM providers
- Real GitHub, Jira, email, browser, VSCode, file watcher, or log integrations
- Real semantic search, LLM chat, external task execution, or playbook workflows

The current implementation is designed to make those additions safer later without mixing business logic into route files.

## SQLite Storage

The default storage backend is SQLite:

```env
STORAGE_BACKEND=sqlite
SQLITE_PATH=data/mindos.db
```

The backend creates the `data/` directory and database tables automatically. SQLite persists events, chat sessions, chat messages, tasks, and playbook-ready records across backend restarts.

To switch back to volatile in-memory storage:

```env
STORAGE_BACKEND=memory
```

To reset SQLite data, use the Dev page clear buttons for events, chats, and tasks. You can also delete `data/mindos.db` manually while the backend is stopped.

## File System Manual Import

MindOS can manually import local text and code files from a folder path you provide through the Connectors page or API:

- `POST /connectors/file-system/preview`
- `POST /connectors/file-system/import`

The import is local-only. The backend reads files from the selected folder on your machine and stores the file contents in your local MindOS database as Memory events.

Supported by default:

- Text/docs: `.txt`, `.md`, `.markdown`, `.rst`, `.csv`, `.json`, `.yaml`, `.yml`, `.xml`
- Code: `.py`, `.js`, `.jsx`, `.ts`, `.tsx`, `.java`, `.kt`, `.go`, `.rs`, `.c`, `.cpp`, `.h`, `.hpp`, `.cs`, `.php`, `.rb`, `.swift`, `.dart`, `.scala`, `.sql`, `.html`, `.css`, `.scss`
- Config/build files: `.env.example`, `.gitignore`, `Dockerfile`, `docker-compose.yml`, `package.json`, `requirements.txt`, `pyproject.toml`, `pom.xml`, `build.gradle`, `settings.gradle`

The importer skips noisy or unsafe folders such as `.git`, `node_modules`, `.venv`, `venv`, `__pycache__`, `dist`, `build`, `target`, `.idea`, `.vscode`, `.next`, `coverage`, and `logs/archive`.

It also skips binary files, files above the configured size limit, `.env`, and files containing obvious private key or secret markers. Live file watching is not implemented yet.

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
