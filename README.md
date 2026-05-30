# MindOS

MindOS is a local-first personal AI workspace for developers. It collects local work context, stores it in local memory, supports search and semantic retrieval, and lets users chat with their own work history.

## Project Guide for AI Agents

Before modifying this repo, read:

- [AGENTS.md](AGENTS.md)
- [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)
- [docs/CURRENT_STATE.md](docs/CURRENT_STATE.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/MEMORY_POLICY.md](docs/MEMORY_POLICY.md)
- [docs/API_CONTRACTS.md](docs/API_CONTRACTS.md)

Rules:

- Keep routes thin.
- Do not duplicate existing modules.
- Do not auto-start Ollama.
- Do not index raw chat messages.
- Tasks are paused until data collection is stable.

## Main Workspaces

- `backend/`: FastAPI backend, SQLite persistence, memory/search/model services, connectors, and integrations.
- `frontend/`: React frontend for Chat, Memory, Connectors, Settings, Dev, and experimental Tasks.
