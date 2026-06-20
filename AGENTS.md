# MindOS Agent Instructions

## Product Summary

MindOS is a local-first personal AI workspace for developers. It collects local work activity from files, logs, Git repositories, editor extensions, browser extension, activity tracker, and future local agents. It stores this data locally, builds searchable memory, creates relationships, supports semantic search, and lets users chat with their own work context.

## Current Priority

The current priority is data collection and memory quality, with safe task execution POCs now active where explicitly implemented:

1. Connectors
2. External ingestion API
3. VSCode extension
4. Browser extension
5. Activity tracker
6. Clean memory/indexing policy
7. Stable local memory and retrieval

Tasks are experimental. Gmail task actions and file/document tasks are active POC features when they follow preview, capability checks, confirmation, and allowlisted execution.

## Non-Negotiable Rules

- Do not add real external task execution unless explicitly requested and guarded by preview plus confirmation.
- Do not send real email silently.
- Do not call real Jira/GitHub write APIs unless that exact write action was explicitly requested and is guarded by editable preview plus confirmation.
- Do not run destructive Git commands.
- Never run arbitrary shell commands from task flows.
- Never force push, delete branches, reset, clean, rebase, or change Git remotes from task flows.
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
- Conversation follow-up resolution may use recent chat-session metadata, but raw chat messages must remain hidden, non-indexed, and relationship-ineligible.

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
- Connector UI should stay simple; advanced sync settings belong behind a collapsed advanced section unless the user explicitly needs them.
- Do not put "upcoming" marketing text in product UI; unsupported connectors should appear as off or needing setup.
- No automatic folder scanning.
- Only user-connected folders may be indexed. Never scan the full disk, home directory, Downloads, Desktop, or other broad locations silently.
- File System tracked-folder indexing must stay lazy/background-only, limited to user-connected folders, and must not create Memory events for source saves, reindex jobs, or scheduler lifecycle. Only `file_system/file_indexed` file records are indexed memory.
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
- Browser page summaries are deterministic/manual for now. Do not auto-run local or cloud LLM summarization on capture.
- Model/page/patent/dataset detail questions should use captured source memory, not root-cause retrieval.
- Raw `browser_page_seen` events should stay hidden and non-indexable.
- No live watching unless explicitly implemented later.
- File/log/git imports must be local-only.
- Git connector must be read-only.
- GitHub connector is read-only until explicitly expanded. Do not add GitHub write actions such as creating issues, commenting, merging, pushing, or updating pull requests unless requested.
- Do not confuse Atlassian Organization Admin API keys with Jira Cloud API tokens. The Jira connector POC uses Jira Cloud site URL + Atlassian email + Jira API token auth only; do not ask for Organization ID or use Atlassian Admin APIs for Jira project/task POCs.
- Jira write actions require an editable preview and explicit confirmation. Jira issue creation may use Jira Cloud REST only for `create issue`; do not add update, delete, transition, assign, comment, or attachment actions unless explicitly requested.
- Email connector is provider-agnostic MCP-style and read-only until explicitly expanded. Do not hardcode Gmail OAuth, Gmail app passwords, IMAP, Samsung Knox, Composio, Zapier, or any single provider unless explicitly requested. Do not add email send, reply, forward, delete, archive, mark-read/unread, or draft actions unless explicitly requested. Do not store full email bodies, attachment contents, API keys, or tokens. Do not log or expose email provider credentials.
- Gmail connector is a separate explicit local OAuth connector. It must use user-uploaded Google OAuth desktop credentials, localhost callback, and only `gmail.compose` plus `gmail.readonly` scopes. Never request broad Gmail full-access scopes, never expose client secrets/tokens to the frontend, and never send Gmail messages without explicit user confirmation.
- Do not route Gmail tasks through the generic Email MCP connector when the Gmail connector exists. `gmail.*` task actions must use Gmail connector status, Gmail capabilities, and Gmail-specific routes unless the user explicitly chooses a custom/corporate Email MCP task.
- Gmail send is allowed only when Gmail is connected, send capability is available, recipient/subject/body are valid, the user has seen an editable preview, and the user explicitly confirms send.
- Gmail drafts may be created after preview. Gmail draft bodies, sent bodies, credentials, and tokens must not be stored in Memory.
- Gmail attachments must never be added silently. Show attachment candidates or manual file choices in preview, require user selection and confirmation, block dangerous file types, enforce size limits, and never store attachment contents in Memory or Task History. Attachment filenames may appear in lightweight Task History.
- Gmail indexed attachments must be resolved from connected File System source ids plus relative paths on the backend. Never trust frontend absolute paths, never search outside connected indexed folders, and never send attachment contents to an LLM or Memory.
- Generated summary/report files must be previewed and saved before they can be attached to Gmail. Gmail should receive generated output attachments as backend-resolved safe output references, not arbitrary frontend paths, and email send still requires a separate final confirmation.
- Attachment discovery must search connected folder file inventory as well as content-indexed memory. A safe file whose text extraction failed can still be found by filename and attached after user selection and confirmation.
- Connected-folder file search summary tasks must search only user-connected indexed File System folders. Show matched files with user selection before reading file contents unless the user selected exact files explicitly. Generated summaries/reports may be saved as new non-overwriting output files, and Gmail send of a generated report still requires a separate editable preview and final confirmation.
- Generic Email MCP remains provider-agnostic for custom/corporate/internal providers and should not be confused with Gmail.
- Future GitHub/local Git write actions require preview, exact capability checks, and explicit confirmation. GitHub API actions belong to the GitHub connector; local repo status/diff/commit/push belongs to the local Git connector.
- Git commit/push tasks must use allowlisted Git commands only.
- External collectors should use the external ingestion API.
- VSCode connector is an implemented MVP connector and should stay user-controlled.
- VSCode connector should behave like an installed extension, not only a debug Extension Development Host.
- MindOS connector toggle is the source of truth for collection; VSCode local settings are only local/emergency controls.
- Browser connector is an implemented MVP connector for manually saved pages/selections, not passive tracking.
- Update docs alongside connector, ingestion, memory, or API changes.

## Background Run Rules

- Long-running chat and future task work should be tracked as backend runs, not only page-local frontend state.
- Page navigation must not cancel an active chat/task run.
- For now, support one active chat run per chat session and recover it through polling.
- Run progress messages are UI-only operational status; do not save them as chat messages, memory events, indexed content, or model chain-of-thought.
- Do not index raw chat messages just because a chat run is tracked.

## Current Known Direction

Tasks are experimental, but file organization, document summary, and Gmail draft/send actions are active POC features. Every task action must follow action classification, capability checks, editable preview, explicit confirmation for side effects, allowlisted execution, and lightweight Task History.

File tasks may use the selected LLM only to draft a plan; FastAPI or the browser POC validates every operation, shows a preview, and requires user confirmation. Do not add delete, overwrite, shell command, Jira, GitHub write, browser, VSCode, or other task adapters unless explicitly requested.

When modifying Tasks, keep task execution safe: LLM plans, FastAPI validates, the user confirms, and the backend executes. Do not add direct execution from the frontend.

Browser-selected file task execution is a POC exception that uses the browser File System Access API only after explicit user confirmation. It must never overwrite existing destinations, and it must not remove an original file until the destination write has completed and been verified.

LLM-generated file task plans must always be validated before preview or execution. Never execute raw LLM tool calls or model-proposed operations directly.

Document summary tasks may read selected safe text documents from a browser-selected folder, but must not modify originals, overwrite output files, store full extracted text in memory, or execute files.
Document summary PDF support is selectable-text extraction only. Do not add OCR or scanned-PDF processing unless explicitly requested.
Generated document summary filenames must be sanitized, should use meaningful inferred topics when possible, and must never overwrite existing files.

Tasks must render action-specific workflows. Do not make the Tasks page file-system-first for every command: folder picker, scan, and file plan controls should appear only for file organization and document summary actions. Gmail draft/send tasks should show an editable Gmail preview, optional user-selected attachments, and a final confirmation before any send.

Task intent should not be rule-only for multi-step work. Use hybrid deterministic hints plus LLM planning where available, validate allowed steps, and fall back to exact deterministic plans. File-dependent Gmail tasks must search connected folders and show file candidates before generating the Gmail preview.

Do not rely on rule-only task categorization for dynamic user requests. The selected LLM should produce a structured task plan when available, while deterministic code extracts hints and provides exact fallback only. Backend validation must repair, clarify, or block unsafe/misclassified plans before any preview or execution.

Gmail task actions use the dedicated Gmail connector. Generic Email MCP actions remain separate and should be used only for explicitly selected custom/corporate MCP provider tasks. Draft/send content must be generated from provided facts only, previewed, and editable before creation/send. Do not index Gmail draft bodies, sent bodies, attachment contents, or store email provider credentials in Memory.

Never execute external side-effect actions without user confirmation. Gmail, GitHub, local Git, file, and future provider actions must follow preview -> capability check -> confirmation -> execution; never execute raw LLM tool calls. Email send must always require explicit confirmation immediately before execution.
Never silently disable risky action buttons. Always show a user-facing blocked reason.

Do not create memory events for operational file tasks. File organize, move, copy, rename, create-folder, cleanup, scan, prepare, execute, and undo activity belongs in Task History only. Only completed document summary tasks should create indexed Memory events, and those events must stay lightweight.

Do not store full source document text in task history or memory. This includes extracted PDF/DOCX text. Document summary task history should store only lightweight counts, filenames, folder names, output format, summary style, and file types.

Clearing Task History must clear only task-history records and the browser-local Recent Tasks list. It must not delete Memory events, connector credentials/data, Gmail/email data, indexed file records, chats, settings, or files unless the user explicitly asks for those scopes.

Future direction may include OpenClaw/Hermes-style agentic execution, but only after the data collection and memory layers are stable.
