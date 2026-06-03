# Architecture

## Backend Architecture

The backend is a FastAPI app in `backend/app`.

Actual structure:

- `app/main.py`: FastAPI setup, CORS, route registration, startup database initialization.
- `app/api/routes`: HTTP route modules for health/status, ingestion, events, search, chat, connectors, context, embeddings, models, tasks, playbooks, and dev tools.
- `app/schemas`: Pydantic request/response contracts.
- `app/services`: business logic for ingestion, context building, search, chat, relationships, embeddings, model routing/registry, connector imports, connector sources, memory policy, and tasks.
- `app/repositories`: SQLite and in-memory persistence implementations.
- `app/integrations`: external/local system adapters such as Ollama, ChromaDB, provider clients, and mock tools.
- `app/domain`: core enums and domain models.
- `app/core`: configuration, database setup, dependencies, and logging.

Routes should be thin. Business logic belongs in services. Persistence logic belongs in repositories. External system details belong in integrations.

## Frontend Architecture

The frontend is a React app in `frontend/src`.

Actual structure:

- `pages`: route-level UI composition for Chat, Memory, Connectors, Settings, Dev, Tasks, and Playbooks.
- `components`: reusable layout and UI pieces.
- `services/api.ts`: API client functions only.
- `types`: shared frontend TypeScript types.
- `store`: global UI state.

Chat is the primary user interface. Memory is for browsing and searching stored knowledge. Connectors control data sources. Settings manages models and configuration. Dev is for debugging only. Tasks exist but are paused/experimental.

## Data Flow

Connector/client -> ingestion endpoint -> memory policy -> SQLite event -> optional embedding -> optional relationship detection -> search/context builder -> model response

The repository applies memory policy during event creation. Eligible events may be indexed by the embedding service. Eligible events may be processed by relationship detection.

## Chat Flow

User message -> QueryIntentService -> selected retrieval profile -> ContextBuilderService -> SearchService direct events -> optional RelationshipService expansion -> formatted context -> ModelRouterService -> provider/FakeLLM -> response cleaner -> saved chat session and chat memory events

Chat context should use context-eligible events. Raw chat_message and chat_response memory events are stored for history but excluded from normal chat RAG context.

Memory lookup queries use a precision profile: purified search terms, preferred source filtering, no default relationship expansion, and noisy event types excluded. Root-cause and summary queries can use broader context.

Conversation follow-ups run through `ConversationContextService` before intent classification. It reads recent messages from the active chat session, uses assistant response metadata to find the previous primary memory source, resolves references such as "this model" or "this patent", and lets ContextBuilder use the `source_focused` profile to fetch that source directly.

## Background Run Flow

User starts chat -> backend creates a `ChatRun` -> user message is saved immediately -> background execution continues server-side -> frontend can navigate away -> frontend polls run status -> assistant result is saved into the chat session -> user returns and sees the saved response.

Chat runs also expose lightweight UI progress metadata such as `current_step`, `progress_message`, and bounded progress events. These messages describe operational status, are not assistant chat messages, are not memory events, and are not model chain-of-thought.

The current MVP supports one active chat run per chat session. Active-run lookup is session-scoped and only returns queued/running work for that exact session; stale runs older than 30 minutes are marked failed. The same queued/running/completed/failed/cancelled status pattern is intended to support long-running task runs later, but task background execution is not implemented in this step.

## Connector Flow

User explicitly imports or collector sends event -> ExternalIngestService/IngestionService or connector import service -> EventRepository -> MemoryPolicyService -> EmbeddingIndexService if eligible -> RelationshipService if eligible

File system, logs, and local Git imports are manual path-based flows. Saved connector sources allow re-importing previously configured paths. External collectors use `/ingest/external`.

## Connector Registry Pattern

`ConnectorRegistryService` is the backend source of truth for connector cards. It returns one normalized status shape for VSCode, Browser, GitHub, Jira, Email, File System, Logs, and Local Git.

The frontend should render connector status from `GET /connectors` instead of maintaining separate hardcoded connector states. Connector cards should share the same product pattern: status, toggle, configure action, event count, and last seen/sync metadata.

External clients send events through `/ingest/external`. For implemented live connectors such as VSCode, the registry toggle has enforcement: disabled connectors should reject or ignore events cleanly rather than silently collecting data.

## VSCode Extension Runtime Flow

Installed VSCode extension -> polls `/connectors/vscode/runtime` -> sends `/connectors/vscode/heartbeat` -> sends events only if the backend VSCode connector is enabled -> backend ingests through `/ingest/external`.

The MindOS web app toggle is the collection source of truth. VSCode local settings are only local controls such as the emergency kill switch and privacy filters. Heartbeats update connector status but do not create memory events.

## Browser Extension Runtime Flow

Installed browser extension -> popup/background checks `/connectors/browser/runtime` -> sends `/connectors/browser/heartbeat` -> manual save or smart capture sends a `browser_extension` event through `/ingest/external`.

Manual mode only sends events when the user clicks Save to MindOS. Smart mode observes the active tab without browser history permission, waits for dwell time, classifies pages with local deterministic rules, and sends only hidden search/history evidence or visible important work/research page events. Private/login/payment pages and noisy feeds are filtered. Heartbeats update connector status but do not create memory events.

## Browser Memory Flow

Browser extension -> classify page -> run visible-text extraction with diagnostics -> send `browser_page_captured` -> backend normalizes URL -> upsert one visible page memory per normalized URL -> index/retrieve clean browser memory.

The browser extractor has a hard DOM access diagnostic followed by a generic visible-text path. Site-specific extractors should wait until basic DOM injection and readable text extraction are proven reliable.

Hugging Face pages still use the same DOM extraction pipeline, but the extractor prefers page-specific model/dataset/card areas and filters common site navigation lines before sending readable context.

Pending captured pages can be summarized manually from Memory through `POST /events/{event_id}/summarize`. This uses deterministic local text processing, updates the existing browser event with Summary/Key points, and reindexes that event when embeddings are enabled. It does not call an LLM automatically.

`browser_page_seen` and `browser_search_query` are lightweight hidden history. They support lookup questions without becoming normal visible memory or relationship noise. Repeat captures should update visit metadata instead of creating duplicate relationships or duplicate vector entries.

## Semantic Search Flow

SQLite event -> embedding text builder -> Ollama embedding model -> ChromaDB vector index -> search query embedding -> vector results -> full event fetch from SQLite

SQLite remains source of truth. ChromaDB stores vectors and lightweight metadata only.

## File System Task Adapter UI Flow

The Tasks UI follows a compact command flow: user command -> folder scan -> deterministic or AI-assisted plan preview -> confirmation -> browser execution for selected handles -> undo when available.

File task input sources:

1. `backend_path`: the user types or pastes an absolute local path. The frontend sends the path to the backend for validation and metadata-only scanning.
2. `browser_handle`: the user chooses a folder with the Chromium File System Access API. The browser does not expose an absolute Windows path, so the frontend scans the selected directory handle and builds a preview from that in-memory snapshot.

File scan flow: user path -> `POST /tasks/file/scan` -> `FileSnapshotService` -> safe metadata-only scan -> UI scan summary and category counts.

File task prepare flow: user instruction + root path -> `POST /tasks/file/prepare` -> `FileSnapshotService` scan -> deterministic planner -> safety validation -> preview plan -> user confirmation later.

File task AI planning flow: browser scan -> deterministic instruction intent -> metadata-only `POST /tasks/file/plan-with-llm` when useful -> selected chat model returns JSON plan -> exact-intent fallback if the model fails -> backend validates allowed `create_folder` / `move_file` operations -> frontend validates against the browser scan again -> preview plan -> user confirmation -> browser execution.

For browser-selected folders, deterministic prepare and POC execution are frontend-side because no absolute path is available for backend validation. AI-assisted planning may call the backend model router, but only scanned metadata is sent, never file contents or handles. The preview uses real scanned file metadata and validated `file.create_folder` / `file.move_file` rows. Browser execution requests read/write permission on the selected directory handle, creates category folders, and moves files with no overwrites by writing the destination before removing the original entry. Backend path execution will be added later and must remain backend-controlled: FastAPI validates, the user confirms, the backend executes, and undo support is created during execution.

Document Summary Task flow: browser-selected folder scan -> readable file selection -> output filename/format/style options -> safe text extraction in the browser -> `POST /tasks/document/summary/prepare` with selected extracted text -> selected model summary preview -> user confirms Save summary -> browser File System Access API writes a new non-overwriting `.md` or `.txt` file -> lightweight `document_summary_created` memory event. The extraction layer supports text-like files, selectable-text PDFs through pdf.js, and DOCX raw text through Mammoth. No OCR is performed. Original documents are not modified, and extracted full text is not stored in task history or memory.

Document Summary Naming flow: selected file names + folder name + extracted headings + generated summary -> deterministic naming service -> optional LLM naming when a model was already used -> sanitized title/topic/filename suggestion -> user-editable output filename -> collision-safe browser save.

Task History and Memory are separate. Operational file tasks can appear in Tasks/Recent Tasks, but they do not create Memory events or index entries. Document summary completion is the only task flow that creates Memory today, and it records only lightweight output filename, folder, and file-count metadata.
