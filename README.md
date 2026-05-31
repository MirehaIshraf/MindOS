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
- `extensions/vscode/`: VSCode extension MVP for sending local editor/workspace events to MindOS.
- `extensions/browser/`: Browser extension MVP for manually saving pages and selected research context.

## VSCode Extension MVP

The VSCode connector lives in [extensions/vscode/README.md](extensions/vscode/README.md). It sends local editor/workspace events to the existing `/ingest/external` API. Install the packaged VSIX into normal VSCode, then use the MindOS Connectors page toggle to control collection. It does not send full file contents unless explicitly configured, and it filters sensitive files/content.

## Browser Extension MVP

The Browser connector lives in [extensions/browser/README.md](extensions/browser/README.md). It manually saves the current page, optional selected text, and an optional note to `/ingest/external`. It does not track browsing history, tabs, or full page content automatically.
