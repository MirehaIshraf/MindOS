# Current State

## Last Updated

Last updated: 2026-06-13

## Backend Status

- Backend framework: FastAPI.
- Storage backend: SQLite by default, with in-memory repository fallbacks still present.
- Vector backend: ChromaDB persistent vector store when embeddings are enabled/available.
- Local model runtime: Ollama for local chat and embedding models; FakeLLM remains fallback.
- Source of truth: SQLite stores raw events, chats, tasks, relationships, saved connector sources, import history, and settings. ChromaDB is rebuildable index state.

## Implemented Backend Modules

| Module | Status | Notes |
|---|---|---|
| Health/status | Working | `/status` should be fast, stable, and non-invasive. |
| Ingestion | Working | Manual `/ingest` and external `/ingest/external` exist. |
| Events/Memory | Working | Events are stored in SQLite and exposed via events/search routes. |
| Search | Working | Keyword plus semantic/hybrid when embeddings are enabled. |
| Embeddings | Working/Partial | Uses Ollama + ChromaDB; optional systems fail over to keyword search. |
| Relationships | Working/Partial | Stored in SQLite; quality and noise reduction need continued tuning. |
| Chat | Working | Uses ConversationContextService, QueryIntentService, ContextBuilderService, selected model through ModelRouter, and background chat runs for navigation-safe responses. |
| Tasks | Partial / active POC | Tasks page uses action-specific previews and preview-confirm-execute gates. Folder picker, scan, and file plan controls appear only for file organization and document summary actions. Browser-selected folder planning/execution is enabled for the POC after validation and confirmation. Document Summary Task POC supports readable file selection, PDF/DOCX/text extraction, output options, model summary preview, and saving a new summary file. Gmail draft/send task actions use the dedicated Gmail connector directly, show editable previews, support user-selected attachments, and require explicit confirmation for send. Draft/send task history is lightweight and not indexed into Memory. Backend path execution and GitHub/local Git write tasks are not production-ready. |
| File connector | Working/POC | Path-based folder import still exists. Connected File System folders are saved as tracked sources and lazily indexed in the background into `file_indexed` memory events. |
| Logs connector | Working | Path-based log import with clear events. |
| Local Git connector | Working | Read-only local Git import with clear events. |
| Saved sources | Working/Partial | Saved connector sources and import runs exist for file/log/git. |
| External ingestion | Working/Partial | API exists for VSCode/browser/activity/local-agent collectors; disabled VSCode/Browser connectors reject their events. |
| VSCode extension | Working | MVP exists in `extensions/vscode`; installable local VSIX flow with backend-controlled runtime polling. |
| Browser extension | Working/Partial | MVP exists in `extensions/browser`; manual page/selection save plus privacy-first smart capture with hard DOM access diagnostics, Hugging Face cleanup in generic visible-text extraction, backend content-quality validation, normalized URL upsert, and manual deterministic summaries. |
| GitHub connector | POC | Read-only connector with local token config, connect/disconnect state, connection test, repository selection, and optional advanced sync for recent commits, open issues, and open pull requests. No write actions are implemented. |
| Gmail connector | POC | Dedicated local-first Gmail OAuth connector. User uploads their own Google OAuth desktop `credentials.json`, connects through a localhost callback, and MindOS stores the Gmail token locally under `~/.mindos/connectors/gmail/`. Supports `gmail.compose` plus `gmail.readonly`, profile test, recent metadata reads, draft creation, multipart attachments, and Gmail send after explicit UI confirmation when Gmail capabilities allow it. Gmail task actions route through Gmail-specific status/routes, not the generic Email MCP connector. Credentials/tokens are local-only and never returned, logged intentionally, stored in Memory, or sent to an LLM. |
| Email connector | POC | Flexible Email MCP connector. Supports mock provider mode and custom/internal/corporate/managed MCP endpoints with bearer, API-key header, or no-auth config. Syncs recent, unread, or searched emails into lightweight `email_message` memory events and can create drafts/send through its own Email MCP routes when explicitly used. Gmail POC tasks do not use Email MCP by default. No delete/archive actions. No Google OAuth, app password, or IMAP requirement. |
| Model registry | Working/Partial | Local Ollama discovery, cloud provider config, FakeLLM fallback. |
| Embedding registry | Working/Partial | Curated and discovered local embedding models; changing model requires reindex. |
| Dev tools | Working/Partial | Useful but should not be treated as product UI. |

## Frontend Pages

| Page | Status | Notes |
|---|---|---|
| Chat | Working | Primary UI. |
| Memory | Working | Browse/search memory with source/category filters and paginated recent timeline. |
| Connectors | Working/Partial | Registry-driven cards with toggle/config/status; manual imports and saved sources remain in configure panels. |
| Settings | Working/Partial | Chat and embedding model settings. |
| Dev | Working/Partial | Debug page; should use `/status` as source of truth. |
| Tasks | Partial / active POC | Task UI supports command entry with action-specific rendering. File and document actions show inline folder context, manual path input, browser-native folder selection, real read-only scan summaries, deterministic or AI-assisted plan previews, browser-handle execution for creating category folders and moving files, document-summary previews for selected safe text/PDF/DOCX files, and connected-log analysis report previews from selected indexed `.log`/`.txt` files. Gmail draft/send actions show LLM-structured editable previews, optional user-selected attachments, clear capability reasons, and final confirmation for send. Browser-selected folders do not expose absolute Windows paths, so file organization and summary saving use the directory handle. Manual path mode remains preview-only. |
| Playbooks | Placeholder | Route/page exists but not a current priority. |

## Implemented Connectors

- File System path import: working; clear file events exists. Connected folder indexing POC is added through tracked File System sources: users add a folder once, MindOS queues background indexing, periodically reindexes only that folder, and marks missing files stale/missing without deleting memory records.
- Logs path import: working; clear log events exists.
- Local Git path import: working and read-only; clear Git events exists.
- VSCode extension MVP: working; packaged local install flow, polls MindOS runtime, sends workspace/file-save events after the MindOS VSCode connector toggle is enabled.
- Browser extension MVP: working; manual popup save flow for pages, selected text, and notes after the MindOS Browser connector toggle is enabled. Smart capture can record hidden search evidence and visible important work/research pages with readable context when enabled. Captured pages are upserted by normalized URL, repeat visits update visit metadata, and Hugging Face model/dataset/docs pages are classified as important.
- GitHub connector POC: simplified read-only token configuration, connect/disconnect, connection testing, repository selection, and optional advanced manual sync of recent commits, open issues, and open pull requests into GitHub memory events. Repositories and sync are disabled while the connector is Off. Tokens are stored locally in connector settings, are not displayed after saving, and are not stored in Memory or sent to the LLM.
- Gmail connector POC: user-provided Google OAuth desktop credentials are uploaded locally, OAuth runs through a localhost callback, and tokens are stored only under the user-local MindOS app directory. The connector can test Gmail profile access, list recent message metadata/snippets, create drafts with `gmail.compose`, attach selected files, and send Gmail messages only after explicit confirmation when the Gmail capability is available. Gmail task actions prefer Gmail connector state and never show Email MCP/mock provider state. Gmail credentials/tokens are not returned to the frontend, logged intentionally, stored in Memory, or sent to an LLM.
- Email connector POC: provider-agnostic MCP-style connector. User configures provider name, MCP/API base URL, auth type, optional credential/header, account label, and optional tool names. The mock provider (`api_base_url=mock`) supports demo sync and mock send without external setup. Test connection discovers normalized `read_email`, `search_email`, `create_draft`, `send_email`, and `reply_email` capabilities. Sync is read-only and stores normalized lightweight `email_message` events with subject, sender, date, excerpt, labels/folder, attachment metadata, and URL when available. Draft/send task actions are capability-driven, show exact disabled reasons, and require preview plus confirmation for send. Provider credentials are never returned, logged, stored in Memory, or sent to the LLM.
- Saved connector sources: working/partial for file system, logs, and Git.
- Import history: working/partial for saved source imports.
- External ingestion API: working/partial; collector clients are derived from event metadata.

## Planned Collectors

- Activity tracker
- Local agent collector

Jira appears as a disabled/unconfigured connector placeholder and does not perform real integration work yet. GitHub and Email MCP are now read-only POC connectors.

These should send data to `/ingest/external` or `/ingest/external/bulk`.

## Current Known Bugs / Risks

- Tasks are experimental active POCs, not general autonomous agents. The Tasks page now provides action-specific previews for file organization, document summaries, Gmail draft/send, Gmail search/summarize, memory reports, and GitHub lookup. File task planning classifies intent first, so fallback preserves the user request instead of broadening it to organize-by-type. Browser execution creates folders and moves files only after confirmation, without deletes, overwrites, audit log, or shell commands. Manual path execution is not connected yet.
- Document Summary Task POC supports browser-selected folders only. It lets the user choose readable `.txt`, `.md`, `.log`, `.json`, `.csv`, `.pdf`, and `.docx` files, pick output filename/format, choose brief/detailed/file-by-file style, send only selected extracted text to the selected model for a preview, and save a new `.md`/`.txt` summary file after confirmation. PDF extraction supports selectable-text PDFs only; scanned/image PDFs and OCR are not supported yet. Summary preview now suggests a dynamic task title, topic, and safe output filename from selected filenames, extracted headings/text, generated summary, instruction, and folder name; the user can edit the filename before saving. Original files are never modified, output files are never overwritten, and full source document text is not stored in task history or memory.
- Recent Tasks can list all meaningful task activity, but only completed document summary tasks create indexed Memory events. Operational file tasks such as organize/move/copy/rename/create-folder remain Task History only and intentionally do not create Memory events or vector index entries. Tasks now includes a clear-history action for Recent Tasks, and Dev Clear tasks uses the same task-history clearing path without deleting Memory, connector data, Gmail/email data, settings, indexed files, or local files.
- A unified action approval/execution foundation now exists for future Gmail, GitHub, and local Git actions. Prepared actions use a capability registry, render a preview, require explicit confirmation for risky side effects, and record user-facing Task History. Gmail task actions now use the Gmail connector directly for search previews, draft creation, and send previews. Sending always requires Gmail `send_email`, valid recipient/subject/body fields, and explicit confirmation; disabled buttons show Gmail-specific reasons. If Gmail send is unavailable but draft creation is available, Tasks shows a Create Gmail Draft fallback. GitHub write and local Git write actions remain disabled.
- Task intent planning is now LLM-first when a selected model is available: deterministic code extracts hints, the model returns a structured plan, backend validation repairs or blocks unsafe/misclassified steps, and deterministic fallback is used only when the model is unavailable or invalid. Summarization/report prompts are routed to connected-file summary instead of folder organization, log-analysis prompts search log-like files first, and file-dependent Gmail tasks search connected File System indexes before showing Gmail preview.
- Gmail attachment preview supports explicit manual file selection and lightweight candidate search from recent summary outputs, the currently selected browser folder scan, or connected File System folder indexes. Indexed candidates are shown as selectable files, resolved server-side by source id plus relative path, and never attached silently. Dangerous file types are blocked, total attachment size is capped at 20 MB, and attachment contents are never stored in Memory or Task History.
- Connected-folder search summary tasks can search user-connected File System indexes by filename and indexed content, show matched files with checkboxes, read only the selected readable files, generate a summary/report preview, and save a new markdown output under the local MindOS outputs folder. If the instruction asks to email the generated report, Tasks creates the output first, then opens a Gmail preview with that generated file attached; sending still requires final confirmation.
- Log Analysis Report Task POC searches only connected indexed folders for log-like `.log`, `.txt`, `.out`, and `.err` candidates, filters random text files out of log search results, prefers latest/relevant logs when requested, lets the user choose files, reads bounded selected log text, redacts secrets before model analysis, shows an error/root-cause report preview, and saves a new markdown report under the local MindOS outputs folder without modifying originals. Raw logs and full reports are not stored in Memory or Task History.
- File System connected-folder indexing maintains operational file inventory for every safe discovered file and creates searchable `file_system/file_indexed` Memory events only when readable content extraction succeeds. A file can be inventoried and attachable even if content indexing failed, such as a PDF with no extractable text. Blocked extensions, secrets, oversized files, and excluded directories are skipped. New or changed files are picked up by lazy background indexing, and deleted/moved files are marked missing rather than removed. Search for indexed files is available through `/tasks/files/search`; no arbitrary filesystem reads happen during search.
- Gmail and Email MCP connector capabilities must not be confused. Gmail POC tasks route through the Gmail connector; Email MCP is for explicitly selected custom/corporate/internal providers.
- Attachment candidate search must stay bounded to recent task outputs, the current selected folder scan, or explicit connected File System indexes. It must not silently full-scan the disk.
- File tasks must not delete, overwrite, run shell commands, read file contents, move outside the selected root, or touch system folders.
- Dev page has historically had status flicker/false unavailable issues. It should use `/status` as source of truth.
- Raw chat events should not be indexed or related. Use memory policy and clean indexes if old data polluted Chroma/relationships.
- Model and embedding registries must not mix chat and embedding models.
- Ollama must not auto-start from status checks.
- VSCode extension MVP can be packaged with `npm run package` and installed into normal VSCode. F5/debug host is only needed for extension development.
- Browser extension does not request browser history permission or perform full unrestricted history tracking. Smart capture is limited to active-tab dwell events, search queries, and work/research page classification with private/noisy pages filtered. Page context extraction collects visible readable text only, not raw HTML or form/input values.
- Browser extension includes a hard DOM access diagnostic and generic visible-text extraction diagnostics. Backend validation prevents placeholder failure text from being counted as captured content. Site-specific extractors and automatic summarization are not the focus until basic DOM extraction is verified.
- Chat retrieval now uses deterministic query intent routing, but retrieval quality still needs tuning with real memory data.
- Chat follow-up resolution is implemented for active sessions. Assistant response metadata stores primary source ids/titles/URLs so prompts like "summarize this model" can reuse the previous memory source without indexing raw chat messages.
- Chat background runs are implemented. A chat response continues server-side after page navigation, active runs are scoped by chat session, stale runs are failed after 30 minutes, and one active chat run per session is supported for now. Runs expose transient UI-only progress messages that are not stored as chat messages or memory. Task background execution is planned but not implemented.
- Greeting/simple conversational prompts such as "Hi" and "Hello" route to `general_chat` with the `no_memory` profile even when local memory is enabled.
- Entity/detail prompts such as "give me details of this model MiniCPM5-1B" route to source-focused memory lookup instead of root-cause retrieval.
- Activity tracker and local agent collector are not implemented yet; only the ingestion API exists for those sources.
- Activity tracker summaries are intended to be indexable later, but current policy treats all `activity_tracker` source events as hidden/non-indexable.

## What Not To Rebuild

- Do not rebuild model registry from scratch.
- Do not rebuild connectors from scratch.
- Do not rebuild task module now.
- Do not replace SQLite with PostgreSQL.
- Do not replace ChromaDB unless explicitly requested.
- Do not duplicate connector cards, routes, services, or repositories.

## Next Recommended Work

1. Stabilize connector data collection.
2. Harden/package VSCode extension MVP.
3. Activity tracker.
4. Browser extension packaging hardening.
5. Memory summaries/noise reduction.
6. Continue safe task POC hardening: task history, background task runs, local Git/GitHub previews.
