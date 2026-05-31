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

## Current MVP Direction

The MVP is currently focused on collecting high-quality local data.

Main MVP modules:

- Chat
- Memory
- Connectors
- Settings
- Dev

Tasks are experimental/paused. The backend task routes still exist, and the frontend Tasks page still exists, but Tasks are no longer a main sidebar item.

## Current Data Sources

Implemented or partially implemented:

- Manual sample events
- File system path import
- Log file path import
- Local Git repository import
- Saved connector sources
- Import history
- VSCode extension MVP with local VSIX packaging and backend-controlled runtime polling
- Chat sessions and raw chat memory events
- Task lifecycle events
- External ingestion endpoint

Planned:

- Browser extension
- Activity tracker
- Local agent observations
- GitHub read connector
- Jira read connector
- Email read connector

The Connectors page now uses a unified connector registry pattern: each connector is represented as a card with status, toggle, configure action, event count, and last seen/sync metadata.

For VSCode, the MindOS connector toggle is the source of truth. The installed extension polls the local backend runtime endpoint and starts/stops collection without requiring an Extension Development Host.

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

## Future Task Vision

Final task architecture:

User asks task -> FastAPI retrieves context -> model drafts plan -> FastAPI validates -> user confirms -> FastAPI executes allowed tool

This is paused for now. Do not prioritize task execution until the data collection and memory layers are stable.
