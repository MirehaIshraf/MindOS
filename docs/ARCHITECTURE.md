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

Chat is the primary user interface. Memory is for browsing and searching stored knowledge. Connectors control data sources. Settings manages models and configuration. Dev is for debugging only. Tasks are experimental, with active POC flows for file organization, document summary, and Gmail draft/send actions.

## Chat-First Command Architecture

Target flow:

ChatPage -> ChatService -> ChatIntent/CommandPlanner -> `CommandPlan` -> `CommandPlanValidator` -> `ToolRegistry` -> `ToolExecutor` -> existing services/connectors -> preview/confirmation when needed -> final Chat result.

The LLM may translate a messy user request into a structured `CommandPlan`, but it does not get direct execution authority. The backend owns validation, risk classification, connector capability checks, confirmation requirements, execution, and sanitized result recording.

TasksPage should evolve into Run History / pending confirmations / debug visibility for command plans and tool runs. It should not become the permanent primary task command input.

## Internal ToolRegistry

`ToolRegistry` is an internal MCP-style registry of allowlisted typed tools. A tool is a wrapper around existing backend services/connectors, such as memory search, connected file search, Gmail read/draft/send, GitHub read, future Jira read/write, or file output creation.

ToolRegistry is not an authentication layer. Connector auth stays with connector services:

- Gmail OAuth and Gmail capabilities stay in the Gmail connector/service.
- GitHub fine-grained access token and selected repositories stay in the GitHub connector/service.
- Future Jira API token/config should stay in a Jira connector/service.
- File System access stays in connected folders or browser-selected directory handles.

MindOS should not require external MCP servers for Gmail, Jira, or GitHub. It may expose internal MCP-style tools, but those tools call MindOS services and connector APIs.

File tools must use connected File System references such as `source_id` plus `relative_path`, or browser-selected directory handles in browser-mode POCs. Tool handlers must not trust arbitrary frontend absolute paths for file reads, writes, or attachments.

## CommandPlan Safety Flow

`CommandPlan` risk is assigned by backend validators, never by the model.

- `read_only`: memory search, connected file search, Gmail unread/search, Jira issue search, GitHub issue/PR/commit search.
- `safe_generate`: summarize, classify, draft text, or create preview-only content.
- `external_write`: Gmail draft/send, future Jira issue/comment, future GitHub issue/comment/PR.
- `file_write`: summary/report creation or file movement after confirmation.
- `high_risk`: delete, destructive transitions, bulk operations, repo delete, issue delete, force push, branch delete, reset, clean, rebase. Disabled for demo.

Read-only tools may run after an explicit user request. Side-effect tools require a preview plus explicit confirmation. High-risk tools must remain unavailable unless a future decision explicitly changes the policy.

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

## GitHub Connector Flow

GitHub is read-only in the current POC: token config -> user connects the connector -> test connection with `/user` -> repository selection -> optional advanced manual sync -> GitHub REST API fetches recent commits, open issues, and open pull requests -> dedupe by repo plus sha/number -> create or update `github_commit`, `github_issue`, and `github_pull_request` memory events -> chat/search can retrieve GitHub context.

The GitHub connector is primarily a configuration and context source. It stores selected repositories and read permissions; user-facing GitHub tasks/actions should be triggered later from Chat or Tasks, not exposed as a busy connector control panel. The token is stored locally in connector settings for now, hidden from config responses, never written to Memory, never logged intentionally, and never sent to the model. GitHub write actions such as creating issues, commenting, merging, pushing, or PR updates are not implemented.

## Email MCP Connector Flow

Email MCP is a provider-agnostic custom/corporate/internal provider path, separate from Gmail. The current POC flow is: user configures provider name -> MCP/API base URL -> auth type and optional token/API key -> optional tool mapping -> test connection/capability discovery -> connect -> sync recent/unread/search messages -> normalize provider responses -> dedupe by provider/account/message id -> create or update `email_message` memory events -> chat/search can retrieve email context.

The adapter supports mock provider mode (`api_base_url=mock`) for demos, direct normalized REST endpoints such as `/email/search`, and MCP tool-call style providers through `/tools/call`. MindOS never hardcodes Gmail, IMAP, Samsung Knox, Composio, Zapier, or any one provider. Provider-specific details stay in `EmailService`/the MCP adapter layer. API keys/tokens are stored locally in connector config for now, stripped from config/status responses, never written to Memory events, never logged intentionally, and never sent to the model. Email MCP draft/send actions are capability-driven and should be used only when the user explicitly chooses a custom/corporate Email MCP task. Gmail tasks use the dedicated Gmail connector instead. Delete, archive, forward, mark read/unread, and other modifying tools remain disabled.

## Gmail Connector Flow

Gmail is a dedicated local OAuth connector separate from the generic Email MCP connector: user uploads Google OAuth desktop `credentials.json` -> MindOS validates and stores it under `~/.mindos/connectors/gmail/` -> Connect Gmail generates a localhost OAuth URL with `gmail.compose` and `gmail.readonly` scopes -> Google redirects to `/connectors/gmail/oauth/callback` -> backend verifies state, exchanges the code, validates granted scopes, stores `token.json`, and fetches the Gmail profile -> connector status shows the connected address.

Gmail API calls go through `GmailService`, which refreshes expired access tokens before profile/read/draft operations. MindOS can create Gmail drafts after direct user action. Sending a draft is exposed as a separate operation and must be guarded by explicit UI confirmation; no AI/tool path may send silently. Credentials and tokens are local-only secrets, never returned to the frontend, never written to Memory, and never sent to an LLM.

Gmail task routing is separate from Email MCP routing: `gmail.*` task action -> Gmail connector status/capabilities -> GmailService/Gmail API. `email_mcp.*` connector work stays in the generic Email MCP connector. Gmail tasks do not use mock Email MCP state, generic Email MCP provider capabilities, or Email MCP send routes unless the user explicitly asks for a custom/corporate Email MCP task.

Gmail Attachment Flow: user instruction -> attachment intent detection -> candidate search from recent task outputs, the currently selected browser-folder scan, and connected File System indexes only -> manual `Choose files` fallback -> editable Gmail draft/send preview -> checkbox selection -> attachment validation for blocked extensions and 20 MB total size -> user confirmation -> Gmail draft/send route -> Gmail MIME message with attachments. Indexed attachments are passed as `{source_id, relative_path}` references; the backend resolves them inside the connected folder root and never trusts frontend absolute paths. Attachment contents are held only long enough to create the Gmail draft/send request; contents are not sent to the LLM, indexed, or stored in Memory/Task History.

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

## Task Execution Flow

Tasks follow a gated execution pattern:

instruction -> classifier -> prepared action -> capability registry -> source/context collection -> LLM planner if needed -> editable preview -> explicit confirmation -> allowlisted execution -> Task History.

LLMs may draft plans, email bodies, issue descriptions, PR text, or commit messages, but raw model output is never executed directly. Every side-effecting action must have visible disabled reasons when blocked, and every send/commit/push/write action requires explicit user confirmation.

## File System Task Adapter UI Flow

The Tasks UI starts with an action classifier: user command -> task action type -> action-specific preview. File organization and document summary actions continue into folder context. Gmail draft, Gmail search, memory report, and GitHub lookup actions render their own preview surfaces instead of showing folder controls.

Gmail draft/send task flow: user command -> `gmail.createDraft` or `gmail.sendEmail` action -> Gmail connector status/capabilities -> collect recent task-history facts -> selected LLM draft planner returns structured To/Subject/Body JSON -> editable preview -> optional attachment selection -> final confirmation for send -> GmailService creates the draft or sends the message. If the selected model is unavailable, MindOS uses a clean deterministic formatter instead of raw task-history dumps. If Gmail is disconnected, draft/send is unavailable, or recent task history is missing, the UI shows Gmail-specific state clearly without falling back to file/folder controls or Email MCP.

The file task UI follows a compact command flow: user command -> folder scan -> deterministic or AI-assisted plan preview -> confirmation -> browser execution for selected handles -> undo when available.

File task input sources:

1. `backend_path`: the user types or pastes an absolute local path. The frontend sends the path to the backend for validation and metadata-only scanning.
2. `browser_handle`: the user chooses a folder with the Chromium File System Access API. The browser does not expose an absolute Windows path, so the frontend scans the selected directory handle and builds a preview from that in-memory snapshot.

File scan flow: user path -> `POST /tasks/file/scan` -> `FileSnapshotService` -> safe metadata-only scan -> UI scan summary and category counts.

Connected File Index flow: user adds a tracked File System folder -> source config is saved -> lazy scheduler queues background indexing -> safe bounded folder scan -> operational inventory upsert for every safe discovered file -> optional readable text extraction -> dedupe/upsert one `file_indexed` Memory event only when content extraction succeeds -> memory policy marks successful content events indexable/context eligible -> `/tasks/files/search` can search inventory filename metadata plus successful content excerpts. The indexer skips blocked extensions, secrets, excluded folders, oversized files, and never scans outside user-connected folders. Periodic polling uses `next_index_after`; startup queues stale enabled sources lazily and never blocks `/status` or app startup. Missing/deleted files are marked `missing` in inventory/content metadata rather than deleted.

File Inventory vs Content Index: inventory is operational connector metadata used for filename search, attachment candidate search, attachability checks, size/modified metadata, and missing-file tracking. It is not a Memory event. `file_system/file_indexed` is only created for files where readable content extraction succeeds. Failed PDF/DOCX/text extraction records remain searchable by filename and may still be attachable if the file type and size are safe.

File task prepare flow: user instruction + root path -> `POST /tasks/file/prepare` -> `FileSnapshotService` scan -> deterministic planner -> safety validation -> preview plan -> user confirmation later.

File task AI planning flow: browser scan -> deterministic instruction intent -> metadata-only `POST /tasks/file/plan-with-llm` when useful -> selected chat model returns JSON plan -> exact-intent fallback if the model fails -> backend validates allowed `create_folder` / `move_file` operations -> frontend validates against the browser scan again -> preview plan -> user confirmation -> browser execution.

For browser-selected folders, deterministic prepare and POC execution are frontend-side because no absolute path is available for backend validation. AI-assisted planning may call the backend model router, but only scanned metadata is sent, never file contents or handles. The preview uses real scanned file metadata and validated `file.create_folder` / `file.move_file` rows. Browser execution requests read/write permission on the selected directory handle, creates category folders, and moves files with no overwrites by writing the destination before removing the original entry. Backend path execution will be added later and must remain backend-controlled: FastAPI validates, the user confirms, the backend executes, and undo support is created during execution.

Document Summary Task flow: browser-selected folder scan -> readable file selection -> output filename/format/style options -> safe text extraction in the browser -> `POST /tasks/document/summary/prepare` with selected extracted text -> selected model summary preview -> user confirms Save summary -> browser File System Access API writes a new non-overwriting `.md` or `.txt` file -> lightweight `document_summary_created` memory event. The extraction layer supports text-like files, selectable-text PDFs through pdf.js, and DOCX raw text through Mammoth. No OCR is performed. Original documents are not modified, and extracted full text is not stored in task history or memory.

Document Summary Naming flow: selected file names + folder name + extracted headings + generated summary -> deterministic naming service -> optional LLM naming when a model was already used -> sanitized title/topic/filename suggestion -> user-editable output filename -> collision-safe browser save.

Task History and Memory are separate. Operational file tasks can appear in Tasks/Recent Tasks, but they do not create Memory events or index entries. Document summary completion is the only task flow that creates Memory today, and it records only lightweight output filename, folder, and file-count metadata.

## Unified Task Action Execution Flow

User instruction -> classifier -> planner -> capability check -> action-specific preview -> user confirmation -> allowlisted execution -> Task History.

`PreparedAction` and the action capability registry are the shared foundation for Gmail, GitHub, local Git, file, and document actions. LLMs may draft text such as email bodies, commit messages, issue titles, and PR descriptions, but the backend validates capabilities and preview payloads before any side-effect action runs. External write actions such as Gmail send, GitHub issue/PR creation, local Git commit, and Git push remain disabled until explicitly implemented.

Gmail task flow: instruction -> email intent classification -> Gmail planner/search -> Gmail capability check -> action-specific preview -> user-facing blocked reason or confirmation -> GmailService action -> Task History. Search and summarize actions are read-only. Gmail send is available only when the Gmail connector exposes `send_email`; if send is absent but `create_draft` exists, the preview switches the primary action to Create Gmail Draft. Send still requires confirmation at the UI and backend service boundary.

Gmail tasks never use Email MCP unless the user explicitly asks for a custom/corporate Email MCP task.

## Gmail Task Flow

`gmail.*` task -> Gmail connector status/capabilities -> Gmail planner/search -> editable draft/send preview -> optional attachment selection -> final confirmation -> GmailService draft/send route.

The Gmail connector owns Gmail-specific OAuth, recent metadata reads, draft creation, sends, and attachments. Email MCP capabilities must not leak into Gmail task availability.

## Gmail Attachment Flow

instruction -> attachment intent detection -> candidate search from recent task outputs, the current selected folder, or connected File System indexes -> manual Choose Files fallback -> checkbox selection -> validation -> preview -> confirmation -> Gmail draft/send.

Indexed candidates are selected by source id and relative path, then resolved by the backend inside the connected folder root before Gmail receives bytes. Attachment validation blocks dangerous extensions, enforces the configured total-size cap, and prevents silent attachment. Attachment contents are only held long enough to submit the confirmed Gmail request; they are not indexed, sent to the LLM, or stored in Memory/Task History.

## GitHub And Local Git Future Flow

GitHub API tasks are planned for repository API actions such as issues, pull requests, and repository metadata. They should use GitHub connector capabilities, preview, and confirmation.

Local Git tasks are planned for repository status, diff, commit, and push. Commit/push flow should be: status/diff -> LLM commit message or action plan -> selected files preview -> explicit confirmation -> allowlisted Git command. GitHub push is a local Git remote operation, not only a GitHub API operation.

No future GitHub/local Git task may force push, delete branches, reset, clean, rebase, change remotes, or run arbitrary shell commands unless an explicit future decision changes that policy.
