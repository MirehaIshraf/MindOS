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
- `POST /events/{event_id}/summarize`: summarize a `browser_page_captured` event with deterministic local logic. Request may include `{ "method": "deterministic" }`; LLM summarization is not implemented. Returns the updated event. Title-only captures return `400`.
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
- `POST /chat/runs`: start a chat response in the background. Request includes `session_id`, `message`, `model_id`, and `use_memory`. Returns `run_id`, `session_id`, and `status`. If the same session already has a queued/running run, returns `409`.
- `GET /chat/runs/{run_id}`: poll a background chat run. Returns status, user message, assistant result when completed, error when failed, timestamps, model/provider, answer style, intent metadata, and UI-only progress fields: `current_step`, `progress_message`, `progress_percent`, and `progress_events`. Stale queued/running runs older than 30 minutes are marked failed before status is returned.
- `GET /chat/sessions/{session_id}/active-run`: returns only the active queued/running chat run for that exact session, or `active_run: null`.
- `POST /chat/runs/{run_id}/cancel`: requests cancellation. Queued runs are marked cancelled; running model calls may finish before cancellation takes effect.
- `GET /chat/runs/debug/active`: debug list of queued/running chat runs with session ids and age.
- `POST /chat/resolve-context`: debug endpoint for resolving follow-up references in a chat session. Request includes `session_id` and `query`; response includes `is_follow_up`, `resolved_query`, source ids, source URLs, entities, and reason.
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

File System Task Adapter routes:

- `POST /tasks/file/scan`: read-only scan of a selected folder without reading file contents or modifying files. Request:
  `{ "root_path": "D:\\Downloads", "max_depth": 2, "max_files": 500, "include_hidden": false }`.
  Response includes `root_path`, `files`, `folders`, `total_files`, `total_folders`, `total_size_bytes`, `max_depth`, `max_files`, `truncated`, and `warnings`.
  Protected/system roots, drive roots, network paths, files, and missing folders return JSON `400` errors.
- `POST /tasks/file/prepare`: create a deterministic preview-only file organization plan. It scans metadata, classifies files by extension, validates planned paths, and returns planned operations without creating folders or moving files. It does not call an LLM and does not create memory events.
  Request example:
  `{ "root_path": "D:\\Downloads", "instruction": "Organize this folder by file type", "max_depth": 2, "max_files": 500, "include_hidden": false, "mode": "organize", "dry_run": true }`.
  Response includes `task_id`, `task_type`, `root_path`, `instruction`, `summary`, `risk_level`, `requires_confirmation`, `status`, `total_operations`, per-operation counts, `operations`, `folders_to_create`, `files_to_move`, `skipped`, `warnings`, `blocked_reasons`, `category_counts`, and `preview_only: true`.
  Operation records include `id`, `type`, `tool`, absolute paths, relative display paths, reason, and `status`. `create_folder` operations use `path`; `move_file` operations use `from_path` and `to_path`.
  Unknown file types are skipped unless the instruction explicitly asks to include other/unknown files. Existing destinations are skipped or blocked; no overwrite operation is proposed.
- `POST /tasks/file/plan-with-llm`: create a preview-only AI-assisted plan for a browser-selected folder. It accepts metadata only; no file contents, browser handles, or absolute Windows paths are sent. The LLM only proposes JSON operations and the backend validates the result before returning a `FileTaskPlan`.
  Request example:
  `{ "instruction": "Move AI-related PDFs into AI Research", "root_name": "Downloads", "files": [{ "name": "transformer.pdf", "relative_path": "transformer.pdf", "extension": ".pdf", "size_bytes": 1234, "category": "PDFs" }], "folders": [], "allowed_operations": ["create_folder", "move_file"], "max_operations": 500 }`.
  Allowed output operations are `create_folder` and `move_file` with relative paths only. Delete, overwrite, shell, edit, execute, folder moves, absolute paths, and path traversal are blocked. If the selected model is unavailable or returns invalid JSON, the endpoint returns a safe deterministic fallback for the same detected intent; it must not broaden a category move into a whole-folder organize plan.
- `POST /tasks/document/summary/prepare`: create a document summary preview from browser-extracted text. Request:
  `{ "instruction": "Summarize these documents", "folder_name": "Notes", "files": [{ "relative_path": "notes.md", "extension": ".md", "text": "..." }], "files_skipped": [], "output_format": "markdown", "output_filename": "mindos-summary.md", "summary_style": "detailed" }`.
  Response includes `task_id`, `status`, `summary_title`, `summary_markdown`, `files_used`, `files_skipped`, `warnings`, `output_filename_suggestion`, `output_format`, `summary_style`, `topic`, `naming_confidence`, `naming_method`, `model`, `provider`, and `model_display_name`.
  The backend does not read files from disk for this endpoint. Browser-selected file text is extracted in the frontend with limits, then sent to the selected model for a preview. Frontend extraction supports `.txt`, `.md`, `.log`, `.json`, `.csv`, selectable-text `.pdf`, and `.docx`; no OCR is performed. Saving the summary file is a separate user-confirmed browser File System Access API action.
- `POST /tasks/document/summary/complete`: record a completed document summary after the browser saves the output file. Request:
  `{ "task_id": "...", "folder_name": "Notes", "output_file_name": "capsule-networks-summary.md", "files_used_count": 3, "files_skipped_count": 1, "summary_style": "detailed", "output_format": "markdown", "file_types_used": ["pdf", "docx", "md"], "summary_title": "Summarized Capsule Networks documents", "topic": "Capsule Networks", "naming_confidence": "high" }`.
  Response includes `status`, `task_type`, optional `memory_event_id`, and optional `warning`.
  This endpoint creates the only task-related Memory event for the File Task POC: `mindos/document_summary_created`. It stores lightweight dynamic title/topic plus filename/folder/count/style/format/file-type metadata only, not full source document text.
- `POST /tasks/file/{task_id}/execute`: execute a prepared plan only when `{ "confirmation": true }` is provided.
- `POST /tasks/file/{task_id}/undo`: run safe undo operations when available.
- `GET /tasks/file/{task_id}`: fetch file task plan, execution result, and undo state.
- `GET /tasks/file/recent`: list recent file tasks.

Only File System tasks are active. Other task adapters remain paused/mock-only unless explicitly requested.

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
