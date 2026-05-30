# Decisions

## 001 SQLite before PostgreSQL

Decision: Use SQLite for the desktop MVP.

Reason: Desktop MVP should not require a separate database service. SQLite is simpler for local installer packaging.

## 002 ChromaDB is an index, SQLite is source of truth

Decision: SQLite stores raw events and metadata. ChromaDB stores vectors only.

Reason: Vector indexes can be rebuilt. Raw data must remain stable.

## 003 Raw chats are stored but not indexed

Decision: Store chat messages/responses for history, but exclude them from default indexing, relationships, and chat context.

Reason: Raw chats create noisy relationships and context explosion.

## 004 Tasks are paused

Decision: Tasks remain experimental/paused.

Reason: Data collection and memory quality must be stable first.

## 005 Ollama must not auto-start

Decision: The app must not start Ollama automatically from status/dev/model checks.

Reason: The user should control local runtimes and resource usage.

## 006 Model registry separates chat and embedding models

Decision: Chat model registry and embedding model registry are separate.

Reason: They serve different purposes and should not pollute each other's UI.

## 007 Connectors are explicit user action

Decision: No automatic folder scanning or tracking without explicit connector/user action.

Reason: Privacy and predictability.

## 008 Provider failure is not backend failure

Decision: If Ollama/Chroma/cloud provider fails, backend should remain online.

Reason: Optional subsystems should degrade gracefully.
