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
- `GET /connectors/github/status`: returns read-only GitHub connector status, configured/connected flags, username, last sync/error, selected repos, repo count, and event count. It never returns the token.
- `POST /connectors/github/config`: save or clear local GitHub token configuration. Request:
  `{ "token": "github_pat_...", "api_base_url": "https://api.github.com" }`.
  Passing an empty token clears the saved token. The token is not returned.
- `POST /connectors/github/test`: tests the saved token with `GET /user`. Returns connected status and username. Invalid/expired tokens return a clean JSON error.
- `GET /connectors/github/repos`: lists accessible repositories for the saved token using GitHub REST API metadata only. Returns `400` with `GitHub connector is not connected.` when GitHub is Off or has not been successfully tested.
- `POST /connectors/github/selection`: saves selected repositories without syncing. Request:
  `{ "repo_full_names": ["owner/repo"], "sync_settings": { "commits": true, "issues": true, "pull_requests": true, "max_items_per_type": 30 } }`.
  Selection is limited to 5 repositories. Returns GitHub connector status and does not create Memory events.
- `POST /connectors/github/sync`: sync selected repositories read-only. Request:
  `{ "repo_full_names": ["owner/repo"], "include_commits": true, "include_issues": true, "include_pull_requests": true, "max_items_per_type": 30 }`.
  Sync is limited to 5 repositories per request and up to 100 items per type. It requires GitHub to be connected, creates or updates `github_commit`, `github_issue`, and `github_pull_request` memory events with dedupe keys, and does not fetch file contents or perform GitHub writes.
- `DELETE /connectors/github/events`: clears GitHub memory events and related relationships/vectors only. It does not clear the token.
- `GET /connectors/gmail/status`: returns local Gmail connector status: `credentials_configured`, `connected`, `reconnect_required`, `email_address`, granted `scopes`, `last_error`, `connected_at`, `credential_file_name`, and required scopes. It never returns client secrets or tokens.
- `POST /connectors/gmail/credentials/upload`: saves a user-provided Google OAuth desktop credentials JSON locally. Request:
  `{ "filename": "credentials.json", "content": "{...json...}" }`.
  The backend validates `installed` or compatible OAuth fields and stores the original file at `~/.mindos/connectors/gmail/credentials.json`. Client secret is never returned.
- `POST /connectors/gmail/connect`: starts local OAuth by returning an `auth_url` for the frontend to open. The URL uses localhost callback, CSRF state, `access_type=offline`, and only `gmail.compose` plus `gmail.readonly` scopes.
- `GET /connectors/gmail/oauth/callback`: localhost Google OAuth redirect target. Verifies state, exchanges code for token, validates required scopes, stores `token.json`, fetches the Gmail profile, and returns a small HTML success/error page.
- `POST /connectors/gmail/test`: refreshes token if needed and calls Gmail profile. Returns connected status and email address.
- `GET /connectors/gmail/recent?limit=5`: reads recent Gmail message metadata/snippets only. It does not fetch full message bodies or attachments.
- `POST /connectors/gmail/drafts/test`: creates a Gmail draft addressed to the connected account. It never sends the draft.
- `POST /connectors/gmail/drafts`: creates a Gmail draft using `{ "to": "...", "subject": "...", "body": "..." }`. It never sends the draft.
- `POST /connectors/gmail/drafts/{draft_id}/send`: sends an existing Gmail draft. The frontend must show explicit confirmation before calling this endpoint.
- `POST /connectors/gmail/disconnect`: deletes `token.json`, keeps credentials, and marks Gmail disconnected.
- `DELETE /connectors/gmail/credentials`: deletes local Gmail credentials and token state.
- `GET /connectors/email/status`: returns Email MCP connector status including configured/connected flags, provider name, API base URL, auth type/header name, account label, last sync/error, selected scope, event count, `has_api_key`, and normalized capabilities. It never returns API keys/tokens.
- `POST /connectors/email/config`: save or replace provider-agnostic MCP config. Request:
  `{ "provider_type": "email_mcp", "provider_name": "Corporate Email MCP", "api_base_url": "https://email-mcp.company.com", "auth_type": "bearer", "auth_header_name": "Authorization", "api_key": "...", "account_label": "work email", "tool_mapping": { "test": "email.test", "search": "email.search", "get": "email.get", "list_folders": "email.list_folders" } }`.
  Use `api_base_url: "mock"` and `auth_type: "none"` for demo mode. Passing an empty `api_key` clears the saved credential. Credentials are not returned.
- `POST /connectors/email/test`: tests the configured MCP provider and discovers capabilities through `/health`, `/status`, `/capabilities`, `/email/capabilities`, `/tools/list`, or configured tool calls. Returns normalized capability booleans. Send/delete/modify capabilities may be reported but remain disabled in MindOS.
- `POST /connectors/email/connect`: enables the configured/tested Email MCP connector. Returns connected status.
- `POST /connectors/email/disconnect`: disables the Email MCP connector. Provider config and synced memory events remain. Returns `{ "status": "disconnected", "message": "..." }`.
- `GET /connectors/email/capabilities`: refreshes normalized provider capabilities without creating Memory events.
- `POST /connectors/email/sync`: sync emails read-only through the configured MCP provider. Request:
  `{ "scope": "recent", "query": "deployment", "max_items": 25 }`.
  Scope values: `recent`, `unread`, and `search`. Default max is 25; hard max is 100. Normalized message fields include `id`, `thread_id`, `subject`, `from`, `to`, `cc`, `date`, `snippet`, `body_excerpt`, `labels`, `folder`, `has_attachments`, `attachments`, and `url`. Attachments are metadata only; contents are never fetched. Deduplicates by `email_mcp + provider_name + account_label + provider_message_id`, falling back to a hash when provider id is missing. Does not send, reply, delete, archive, or modify any email. Returns `400` when connector is not connected.
- `POST /connectors/email/drafts`: create a draft through a connected MCP email provider only when `create_draft` capability is available. Request:
  `{ "to": "someone@example.com", "subject": "...", "body": "...", "provider": "email_mcp" }`.
  Response:
  `{ "ok": true, "draft_id": "...", "url": null, "message": "Draft created." }`.
  The adapter tries normalized REST `/email/drafts` and MCP tool names such as `email.create_draft`, `gmail.create_draft`, `gmail.draft`, and `create_draft`. It never sends email and does not create Memory events.
- `DELETE /connectors/email/events`: clears Email memory events and related relationships/vectors only. It does not clear provider config or credentials.
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
- `POST /tasks/gmail/draft/prepare`: prepare an editable Gmail draft preview from user instruction and recent task-history facts. Request:
  `{ "instruction": "draft a mail about last 7 days work of me", "connected_email": "me@example.com", "recent_tasks": [{ "type": "document_summary", "title": "...", "summary": "...", "output_file_name": "..." }], "model_id": null }`.
  Response includes `to`, `subject`, `body`, `tone`, `source_summary`, warnings, model/provider metadata, and an optional planner warning. The selected LLM returns structured JSON when available; otherwise MindOS returns a clean deterministic fallback. The endpoint does not create a Gmail draft, send email, or create Memory events.
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
