# API Contracts

This document reflects the currently mounted route modules in `backend/app/api/routes`.

## System

- `GET /health`: lightweight backend health and basic counts.
- `GET /status`: detailed but non-invasive status. Must remain fast and must not start Ollama, pull models, generate text, or reindex embeddings.

## Ingestion

- `POST /ingest`: create one manual event.
- `POST /ingest/bulk`: create multiple manual events, currently limited to 50.
- `POST /ingest/external`: create one event from a local external collector.
- `POST /ingest/external/bulk`: create up to 100 external collector events; each event is processed independently.
- `GET /ingest/status`: returns supported external collector sources, preferred event types, recent external event count, and derived collector clients.

If the VSCode or Browser connector is disabled in MindOS, `POST /ingest/external` for `source=vscode_extension` or `source=browser_extension` returns `403` with a JSON detail message.

Browser connector config fields include:

- `capture_mode`: `manual`, `smart`, or `off`.
- `capture_search_queries`: whether smart capture can store hidden search query evidence.
- `capture_important_pages`: whether smart capture can store visible important page memory.
- `capture_page_context`: whether safe page description/text excerpts may be included.
- `capture_full_page_text`: off by default; do not enable broad full-text capture casually.
- `max_page_text_chars`, `minimum_active_seconds`, `ignored_domains`, `important_domains`, `history_retention_days`.

Preferred browser event types:

- Hidden/lightweight: `browser_page_seen`, `browser_search_query`.
- Visible/important: `browser_page_captured`, `browser_page_summary`, `browser_page_saved`, `browser_selection_saved`, `browser_research_note`.

`browser_page_captured` content should preserve the readable page context sent by the extension. Expected content shape includes page title, URL, domain, optional description, headings, readable context excerpt, and selected text when present. Metadata should include `url`, `normalized_url`, `normalized_url_hash`, `domain`, `page_title`, `page_type`, `category`, `importance_reason`, `text_excerpt_included`, `captured_text_chars`, `page_context_missing`, `extractor`, `extraction_diagnostics`, `capture_mode`, `visit_count`, `first_seen_at`, and `last_seen_at`. Extraction diagnostics should include hard DOM access fields such as `hardDomOk`, `bodyTextLength`, `documentElementTextLength`, `readyState`, `usedSelector`, `candidateLengths`, and `error` when available. Repeat captured pages are upserted by normalized URL hash. Placeholder failure text such as `No readable page text was extracted.` must not count as captured context; the backend validates this and marks the event as `page_context_missing=true`.

## Memory / Events

- `GET /events/recent`: list recent events with optional source/category/hidden filters. Supports `limit`, `offset`, `include_hidden`, `source`, and `category`; response includes `events`, `total`, `limit`, `offset`, and `has_more`.
- `GET /events/{event_id}`: fetch event detail.
- `GET /events/{event_id}/related`: fetch related memory for an event.
- `GET /search/event/{event_id}`: legacy/detail lookup through the search route.

## Search

- `POST /search`: keyword, semantic, hybrid, or auto search depending request and embedding availability.
- `GET /search/stats`: memory/search counts and grouping.

## Context

- `POST /context/build`: build a structured context package for chat/task debugging.
- `POST /context/intent`: classify a query into an intent and retrieval profile for debugging.
- `GET /context/event/{event_id}`: build context around one event and related memory.

## Chat

- `GET /chat`: placeholder readiness response.
- `POST /chat`: chat with local memory context and selected model.
- `GET /chat/sessions`: list chat sessions.
- `GET /chat/sessions/{session_id}/messages`: list messages in a chat session.
- `DELETE /chat/sessions/{session_id}`: delete one chat session.
- `DELETE /chat/sessions`: clear all chat sessions.

## Models

- `GET /models/settings`: full model settings for Settings UI.
- `GET /models/chat`: enabled/configured/available chat models plus FakeLLM fallback.
- `POST /models/select`: select default chat model.
- `POST /models/provider-config`: save provider configuration locally.
- `POST /models/{model_id}/enabled`: enable/disable one model.
- `GET /models/providers/health`: provider health summary.
- `GET /models/embeddings`: embedding model settings.
- `POST /models/embeddings/select`: select embedding model; reindexing remains manual.

## Embeddings

- `GET /embeddings/status`: embedding and Chroma status.
- `POST /embeddings/reindex`: rebuild vector index from eligible events.
- `POST /embeddings/clear`: clear vector index and update event embedding statuses.

## Connectors

- `GET /connectors`: unified connector registry cards/status.
- `GET /connectors/vscode/runtime`: runtime settings for the installed VSCode extension to poll.
- `POST /connectors/vscode/heartbeat`: updates VSCode connector last-seen status; does not create a memory event.
- `GET /connectors/browser/runtime`: runtime settings for the browser extension popup/background script.
- `GET /connectors/browser/rules`: browser smart-capture rule summary, including important patterns, noisy/private patterns, and current ignored/important domain config.
- `POST /connectors/browser/heartbeat`: updates Browser connector last-seen status; does not create a memory event.
- `GET /connectors/{connector_id}`: one connector status response.
- `POST /connectors/{connector_id}/toggle`: enable/disable a connector with `{ "enabled": true }`.
- `GET /connectors/{connector_id}/config`: read placeholder/stored connector config.
- `POST /connectors/{connector_id}/config`: save placeholder/stored connector config.
- `GET /connectors/collectors`: derived external collector clients.
- `POST /connectors/file-system/preview`: preview folder import.
- `POST /connectors/file-system/import`: import folder by path.
- `DELETE /connectors/file-system/events`: clear only file system events.
- `POST /connectors/logs/preview`: preview log file import.
- `POST /connectors/logs/import`: import log file by path.
- `DELETE /connectors/logs/events`: clear only log events.
- `POST /connectors/git/preview`: preview local Git repository.
- `POST /connectors/git/import`: import local Git repository with read-only commands.
- `DELETE /connectors/git/events`: clear only Git events.
- `GET /connectors/sources`: list saved connector sources.
- `POST /connectors/sources`: create saved connector source.
- `PUT /connectors/sources/{source_id}`: update saved connector source.
- `DELETE /connectors/sources/{source_id}`: delete saved connector source.
- `POST /connectors/sources/{source_id}/import`: run import for a saved source.
- `DELETE /connectors/sources/{source_id}/events`: clear events for one saved source.
- `GET /connectors/import-runs`: list import history.

## Tasks

Tasks are experimental/paused but routes still exist:

- `GET /tasks`
- `POST /tasks/execute`
- `POST /tasks/plan`
- `POST /tasks/confirm`
- `POST /tasks/cancel`
- `GET /tasks/pending`
- `GET /tasks/history`

Do not prioritize Tasks unless explicitly requested.

## Playbooks

- `GET /playbooks`: placeholder route.

## Dev

- `POST /dev/sample-events`
- `DELETE /dev/clear-events`
- `DELETE /dev/clear-tasks`
- `DELETE /dev/clear-chats`
- `POST /dev/rebuild-relationships`
- `DELETE /dev/clear-relationships`
- `POST /dev/apply-memory-policy`
- `POST /dev/clean-memory-indexes`
- `DELETE /dev/clear-all`
- `POST /dev/test-llm`
- `GET /dev/state`
- `POST /dev/dedupe-browser-pages`: merge duplicate visible browser page captures by normalized URL hash and remove duplicate relationships/vectors.
- `POST /dev/fix-browser-content-quality`: correct existing browser captured-page metadata when placeholder extraction failure text was previously counted as real context.

## Error Rule

All endpoints should return JSON errors. Frontend should only show "backend offline" when a network request receives no backend response.
