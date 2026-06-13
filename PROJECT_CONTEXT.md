# MindOS Project Context

## What MindOS Is

MindOS is a local-first AI workspace for developers. It runs on the user's machine and builds a private memory of their work. Users can ask questions about past work, debug issues, summarize activity, generate reports, and later safely execute tasks.

## Product Philosophy

- Local-first
- User-controlled
- Privacy-aware
- Connector-first
- Memory before agents
- Safe execution only after confirmation
- Simple UI, powerful backend
- Retrieval and context are controlled by FastAPI, not directly by the model
- Query intent and retrieval precision are decided by FastAPI before model calls

## Current MVP Direction

The MVP is currently focused on collecting high-quality local data.

Main MVP modules:

- Chat
- Memory
- Connectors
- Settings
- Dev

Tasks are experimental, but several safe POC task flows are active after explicit user request:

- File organization with scan, plan, preview, confirmation, and browser-selected-folder execution.
- Document summary with selected file reading, LLM summary preview, and non-overwriting summary save.
- Gmail draft/send through the dedicated Gmail connector, including editable previews, explicit send confirmation, and attachment preview/selection.

Other task adapters remain paused/mock-only unless explicitly implemented.

## Current Data Sources

Implemented or partially implemented:

- Manual sample events
- File system path import
- Log file path import
- Local Git repository import
- Saved connector sources
- Import history
- VSCode extension MVP with local VSIX packaging and backend-controlled runtime polling
- Browser extension MVP for manually saved pages, selected text, research notes, and privacy-first smart capture
- Chat sessions and raw chat memory events
- Task lifecycle events
- External ingestion endpoint

Planned:

- Activity tracker
- Local agent observations
- GitHub read connector
- Jira read connector
- Email read connector

The Connectors page now uses a unified connector registry pattern: each connector is represented as a card with status, toggle, configure action, event count, and last seen/sync metadata.

For VSCode, the MindOS connector toggle is the source of truth. The installed extension polls the local backend runtime endpoint and starts/stops collection without requiring an Extension Development Host.

For Browser, the MVP supports manual save and smart capture modes. Manual save is explicit through the popup. Smart capture is developer/research oriented: it can record search queries and important work/research pages with readable context while avoiding private, login, payment, and noisy entertainment/social pages.

## Current Storage

The actual current code supports SQLite and in-memory repositories, with SQLite as the default configured storage backend.

- SQLite stores source-of-truth data: events, relationships, chats, tasks, connector sources, import runs, model settings, and other local app data.
- ChromaDB stores semantic vector index data through a persistent local Chroma path.
- Ollama generates local embeddings.
- Relationships are stored in SQLite through the relationship repository.
- Memory policy controls what gets indexed, related, hidden, and used as context.

SQLite remains the source of truth. ChromaDB can be cleared and rebuilt.

## Current AI

- Local Ollama chat models are supported.
- Local Ollama models are auto-discovered from `/api/tags`.
- Chat model registry supports local Ollama models and optional cloud providers.
- FakeLLM remains fallback.
- Embedding model registry is separate from chat model registry.
- Semantic search uses local embedding models with Ollama and ChromaDB.
- Cloud chat models are optional and require explicit API key setup.
- Cloud embedding models are not used.

## Important Memory Principle

Raw chat messages should not pollute the main memory graph:

- stored: yes
- visible in Chats category: yes
- indexed by default: no
- relationship eligible by default: no
- used in normal RAG context: no

Small memory lookup questions should use precise retrieval. For example, "Did I search about happiness ever?" should search for `happiness`, prefer manually saved browser/file/log/git memory, avoid weak relationship expansion, and answer from exact local memory rather than generic model knowledge.

Follow-up questions reuse active chat-session context. If a previous answer found a memory source, later prompts such as "summarize this model" or "what is this patent about?" should resolve "this" to the previous primary source without indexing raw chat messages into the main memory graph.

Captured browser pages can be summarized manually with deterministic local logic. This updates the existing page memory item with a Summary and Key points section without calling an LLM automatically. Entity/detail questions about models, datasets, patents, pages, or documents should prefer captured browser memory and should not be routed as root-cause analysis unless failure/debug language is present.

## Future Task Vision

Final task architecture:

User asks task -> FastAPI retrieves context -> model drafts plan -> FastAPI validates -> user confirms -> FastAPI executes allowed tool

Current active task POCs are file organization, document summary, Gmail draft/send with confirmation, and Gmail attachment preview/selection. These flows are not production-grade autonomous agents; they are gated preview-confirm-execute slices.

Gmail has a dedicated local Gmail connector for OAuth, recent metadata, drafts, sends, and attachments. Gmail tasks route to that connector by default. The generic Email MCP connector remains separate for custom, internal, corporate, or managed MCP providers and should be used only when explicitly selected.

The File System Task Adapter allows local `create_folder`, `move_file`, `copy_file`, and `rename_file` style planning inside a selected root folder after confirmation. Browser-selected file execution is a POC path and must remain non-destructive: no overwrite, delete, shell, or silent scan.

Future task direction:

- GitHub API tasks: create issues and pull requests only after preview and confirmation.
- Local Git tasks: status, diff, commit, and push only after preview and confirmation.
- GitHub push is a local Git remote operation, not only a GitHub API operation.

Do not extend task execution to new external providers until explicitly requested and routed through preview, capability checks, confirmation, and allowlisted execution.
