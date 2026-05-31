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

If the VSCode connector is disabled in MindOS, `POST /ingest/external` for `source=vscode_extension` returns `403` with a JSON detail message.

## Memory / Events

- `GET /events/recent`: list recent events with optional source/category/hidden filters.
- `GET /events/{event_id}`: fetch event detail.
- `GET /events/{event_id}/related`: fetch related memory for an event.
- `GET /search/event/{event_id}`: legacy/detail lookup through the search route.

## Search

- `POST /search`: keyword, semantic, hybrid, or auto search depending request and embedding availability.
- `GET /search/stats`: memory/search counts and grouping.

## Context

- `POST /context/build`: build a structured context package for chat/task debugging.
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

## Error Rule

All endpoints should return JSON errors. Frontend should only show "backend offline" when a network request receives no backend response.
