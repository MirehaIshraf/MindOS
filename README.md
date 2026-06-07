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

## File System Task Adapter

MindOS includes a File System Task Adapter MVP for local folder organization. It scans a user-selected folder, prepares a safe plan, shows a preview, requires confirmation, executes only allowed file operations, and stores an undo log. It does not delete files, overwrite destinations, execute shell commands, read file contents, or move files outside the selected root folder.

## Main Workspaces

- `backend/`: FastAPI backend, SQLite persistence, memory/search/model services, connectors, and integrations.
- `frontend/`: React frontend for Chat, Memory, Connectors, Settings, Dev, and experimental Tasks.
- `extensions/vscode/`: VSCode extension MVP for sending local editor/workspace events to MindOS.
- `extensions/browser/`: Browser extension MVP for manually saving pages and selected research context.

## VSCode Extension MVP

The VSCode connector lives in [extensions/vscode/README.md](extensions/vscode/README.md). It sends local editor/workspace events to the existing `/ingest/external` API. Install the packaged VSIX into normal VSCode, then use the MindOS Connectors page toggle to control collection. It does not send full file contents unless explicitly configured, and it filters sensitive files/content.

## Browser Extension MVP

The Browser connector lives in [extensions/browser/README.md](extensions/browser/README.md). It manually saves the current page, optional selected text, and an optional note to `/ingest/external`. It does not track browsing history, tabs, or full page content automatically.

## Gmail Connector POC

MindOS can connect Gmail locally using your own Google OAuth desktop credentials. In Google Cloud Console, create an OAuth client for a desktop app, enable the Gmail API, and download the `credentials.json` file. In MindOS, open Connectors -> Gmail, upload that file, then click Connect Gmail.

Required scopes are:

- `https://www.googleapis.com/auth/gmail.compose`
- `https://www.googleapis.com/auth/gmail.readonly`

MindOS stores `credentials.json` and `token.json` locally under `~/.mindos/connectors/gmail/`. It can test the Gmail profile, read recent message metadata, and create drafts. Sending a draft requires explicit confirmation in the UI.
