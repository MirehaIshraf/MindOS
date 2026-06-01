# MindOS Agent Instructions

## Product Summary

MindOS is a local-first personal AI workspace for developers. It collects local work activity from files, logs, Git repositories, editor extensions, browser extension, activity tracker, and future local agents. It stores this data locally, builds searchable memory, creates relationships, supports semantic search, and lets users chat with their own work context.

## Current Priority

The current priority is data collection and memory quality:

1. Connectors
2. External ingestion API
3. VSCode extension
4. Browser extension
5. Activity tracker
6. Clean memory/indexing policy
7. Stable local memory and retrieval

Tasks and agentic execution are currently paused/experimental.

## Non-Negotiable Rules

- Do not add real external task execution unless explicitly requested.
- Do not send real email.
- Do not call real Jira/GitHub write APIs.
- Do not run destructive Git commands.
- Do not auto-start Ollama.
- Do not auto-pull models.
- Do not auto-scan folders.
- Do not add cloud embeddings.
- Do not treat provider failure as backend failure.
- Do not index raw chat messages by default.
- Do not create relationships for raw chat messages.
- Do not put business logic inside route files.
- Do not duplicate existing services, repositories, routes, or connector cards.
- Do not rebuild a working feature from scratch unless explicitly requested.

## Architecture Rules

Backend layers:

- routes = request/response only
- schemas = Pydantic contracts
- services = business logic
- repositories = persistence
- integrations = external systems like Ollama, ChromaDB, providers, tools
- domain = core models/enums

Frontend layers:

- pages = route-level UI composition
- components = reusable UI
- services/api.ts = API client only
- types = shared frontend types
- store = global UI state only

## Before Adding Code

Before adding a new feature:

1. Read PROJECT_CONTEXT.md.
2. Read docs/CURRENT_STATE.md.
3. Check existing routes/services/repositories first.
4. Do not duplicate existing connector or model logic.
5. Update docs/CURRENT_STATE.md if the implementation changes.
6. Update docs/API_CONTRACTS.md if API behavior changes.
7. Update docs/MEMORY_POLICY.md if ingestion/indexing/retrieval behavior changes.
8. Keep APIs backward-compatible where reasonable.
9. Add graceful fallback for optional systems.

## Backend Stability Rules

- /status must be fast, stable, and non-invasive.
- /status must not call model generation.
- /status must not start Ollama.
- /status must not pull models.
- /status must not reindex embeddings.
- Optional systems failing should return unavailable flags, not crash backend.
- Every endpoint should return JSON errors, not HTML stack traces.
- Provider failure does not mean backend failure.

## Memory Rules

- SQLite is source of truth.
- ChromaDB is only a vector index and can be rebuilt.
- Not every event is indexable.
- Not every event is relationship eligible.
- Not every event is context eligible.
- Raw chat_message/chat_response events are stored but excluded from normal indexing, relationships, and chat context.
- Activity tracker raw events are noisy and should be hidden/non-indexable by default.
- Summaries are preferred over raw noisy streams.
- Chat retrieval should route through query intent first; precision memory lookups should avoid weak relationship expansion and noisy event types.

## Model Rules

- Chat model registry and embedding model registry are separate.
- Chat models must not appear in embedding dropdown unless they are explicitly embedding-capable.
- Embedding models must not appear in chat dropdown.
- Local chat models are discovered from Ollama.
- FakeLLM must always remain available as fallback.
- Cloud models require explicit user configuration and privacy warning.
- Changing embedding model requires reindexing.
- No cloud embeddings for now.

## Connector Rules

- Connectors must be explicit user action.
- Connector UX must use the same toggle/config/status pattern across connector types.
- Do not put "upcoming" marketing text in product UI; unsupported connectors should appear as off or needing setup.
- No automatic folder scanning.
- No automatic browser tracking without extension/user permission.
- Browser connector supports manual save and privacy-first smart capture. Do not add full browser history scraping.
- Do not request browser history permission without explicit instruction.
- Browser data must stay user-controlled. Smart capture must avoid private/login/payment pages and noisy feeds.
- Do not capture full browser page text automatically by default.
- Browser smart capture must include readable context for important pages; do not store only URL/title unless extraction fails.
- Browser extraction failure placeholders must not be counted as captured context. If readable text is missing, mark page context as missing instead of claiming an excerpt exists.
- Debug browser extraction from the DOM pipeline first. Prove `chrome.scripting.executeScript` can read `document.body.innerText` before adding site-specific extractors.
- Browser captured pages must be idempotent: repeat visits update/upsert one visible memory item by normalized URL instead of creating duplicate visible events.
- Do not call an LLM automatically for every browser page. Browser capture should preserve readable text and diagnostics first; summarization is a later step.
- Raw `browser_page_seen` events should stay hidden and non-indexable.
- No live watching unless explicitly implemented later.
- File/log/git imports must be local-only.
- Git connector must be read-only.
- External collectors should use the external ingestion API.
- VSCode connector is an implemented MVP connector and should stay user-controlled.
- VSCode connector should behave like an installed extension, not only a debug Extension Development Host.
- MindOS connector toggle is the source of truth for collection; VSCode local settings are only local/emergency controls.
- Browser connector is an implemented MVP connector for manually saved pages/selections, not passive tracking.
- Update docs alongside connector, ingestion, memory, or API changes.

## Current Known Direction

Tasks are paused. Future direction may include OpenClaw/Hermes-style agentic execution, but only after the data collection and memory layers are stable.
