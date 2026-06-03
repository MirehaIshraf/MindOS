# Memory Policy

## Purpose

MindOS stores many event types. Not every stored event should be embedded, related, or used as chat context.

The current policy is implemented in `backend/app/services/memory_policy_service.py` and applied by event repositories during event creation.

## Core Fields

- `memory_category`: broad grouping used by Memory UI and retrieval, such as `chat`, `task`, `report`, `captured_event`, `activity`, or `agent`.
- `hidden_from_default`: whether the event is hidden from the default Memory All view.
- `is_indexable`: whether the event should be sent to the embedding pipeline and ChromaDB.
- `is_relationship_eligible`: whether the event should participate in relationship detection.
- `is_context_eligible`: whether the event can be used in normal chat/task context building.
- `embedding_status`: indexing state, currently `not_required`, `pending`, `indexed`, or `failed`.

## Policy Table

| Event/source | Default visible | Indexable | Relationship eligible | Context eligible | Notes |
|---|---:|---:|---:|---:|---|
| file_system/file_imported | Yes | Yes | Yes | Yes | Captured local file content. Actual file event types may vary by importer. |
| logs/log_error | Yes | Yes | Yes | Yes | Captured log errors should be searchable and usable for diagnosis. |
| logs/log_warning | Yes | Yes | Yes | Yes | Captured log warnings should be searchable and usable for diagnosis. |
| git/git_commit | Yes | Yes | Yes | Yes | Local Git import is read-only. |
| git/git_repo_snapshot | Yes | Yes | Yes | Yes | Repository snapshot context. |
| git/git_working_tree_status | Yes | Yes | Yes | Yes | Working tree status context. |
| github/github_commit | Yes | Yes | Yes | Yes | Read-only GitHub sync commit context. |
| github/github_issue | Yes | Yes | Yes | Yes | Read-only open issue context. |
| github/github_pull_request | Yes | Yes | Yes | Yes | Read-only open pull request context. |
| vscode_extension/editor_file_saved | Yes | Yes | Yes | Yes | Useful editor event, especially when safe content snippets are included. |
| vscode_extension/editor_file_opened | No | No | No | No | Open events are noisy and hidden/non-indexable by default. |
| vscode_extension/editor_workspace_opened | Yes | Yes | Yes | Yes | Useful session/workspace context. |
| browser_extension/browser_page_saved | Yes unless private | Yes | Yes | Yes | Manual browser popup save; no automatic history tracking. |
| browser_extension/browser_selection_saved | Yes unless private | Yes | Yes | Yes | User-selected page text saved manually. |
| browser_extension/browser_research_note | Yes unless private | Yes | Yes | Yes | User-authored browser research note. |
| browser_extension/browser_page_seen | No | No | No | No | Lightweight smart history only; hidden from default memory and normal context. |
| browser_extension/browser_search_query | No | Yes | No | No | Hidden search evidence for precise memory lookup; not normal chat context. |
| browser_extension/browser_page_captured | Yes unless private | Yes | Yes | Yes | Smart-captured work/research page with readable context excerpt; one visible memory item per normalized URL. |
| browser_extension/browser_page_summary | Yes unless private | Yes | Yes | Yes | Future summarized browser memory; not generated automatically today. |
| activity_tracker/app_focus_changed | No | No | No | No | Raw activity tracker events are noisy. |
| activity_tracker/work_session_summary | No by current source-level policy | No by current source-level policy | No by current source-level policy | No by current source-level policy | Intended direction is summarized tracker events should become indexable; current code treats all activity_tracker events as hidden/non-indexable. |
| mindos/chat_message | No | No | No | No | Stored for history and Chats category only. |
| mindos/chat_response | No | No | No | No | Stored for history and Chats category only. |
| mindos/chat_summary | Yes | Yes | Yes | Yes | Future preferred representation of chat history. |
| mindos/task_completed | Yes | Yes | Yes | Yes | Legacy/mock task lifecycle events. Operational file tasks should use Task History only instead. |
| mindos/file_task_prepared | Yes | No | No | No | File task preview/confirmation state; visible but not normal context. |
| mindos/file_task_completed | Yes | No | No | No | Legacy safety net only. Operational file tasks should appear in Task History, not Memory. |
| mindos/file_task_failed | Yes | No | No | No | Legacy safety net only. Operational file tasks should appear in Task History, not Memory. |
| mindos/file_task_undone | Yes | No | No | No | Legacy safety net only. Operational file task undo should appear in Task History, not Memory. |
| mindos/document_summary_created | Yes | Yes | Yes | Yes | Lightweight record that a document summary file was created, including dynamic title/topic, output filename, folder, counts, style, format, and file types. Do not store full source document text. |
| mindos/report_generated | Yes | Yes | Yes | Yes | Reports are useful memory. |
| local_agent/agent_observation | No | No | No | No | Raw agent observations are noisy by default. |
| local_agent/agent_summary | Yes | Yes | Yes | Yes | Summaries are preferred over raw agent streams. |
| manual/note | Yes | Yes | Yes | Yes | Manual captured memory. |

## Rules

- Raw `chat_message` and `chat_response` events are stored but not indexed, related, or context eligible.
- Chat-session metadata can store recent source ids, URLs, titles, entities, and follow-up resolution hints. This is active conversation state only; it must not make raw chat messages indexable or relationship eligible.
- `chat_summary` is indexable and context eligible.
- Raw activity tracker events are hidden and non-indexable by default.
- Activity summaries are intended to become indexable, but the current source-level code treats all `activity_tracker` events as hidden/non-indexable.
- File, log, Git, VSCode saved/workspace, manually saved browser extension events, and useful captured events are indexable/context eligible by default.
- GitHub connector events for commits, issues, and pull requests are visible, indexable, relationship eligible, and context eligible. GitHub connector token save, test connection, repo listing, sync start, and sync completion are not Memory events.
- VSCode file-opened events are stored but hidden/non-indexable by default to avoid open-file noise.
- Browser manual saves are visible and indexable. Smart capture can create hidden `browser_page_seen` history, hidden/indexable `browser_search_query` lookup evidence, and visible/indexable `browser_page_captured` memory for important work/research pages. Captured page events should include readable page context when extraction succeeds.
- `browser_page_captured` events are upserted by normalized URL. Repeat visits increment `visit_count` and update `last_seen_at` instead of creating duplicate visible memory.
- Browser captured-page metadata includes extraction diagnostics such as `captured_text_chars`, `text_excerpt_included`, `page_context_missing`, and `extraction_diagnostics`.
- `page_context_missing=true` means the event is title/URL memory only and should not be treated as content-rich. Placeholder phrases such as "No readable page text was extracted." do not count as captured content.
- Title-only browser captures remain searchable by title, URL, domain, and metadata, but should not be summarized from page content.
- Browser page summarization is manual and deterministic. Pending browser captures can be summarized from captured readable context, which updates the same `browser_page_captured` event with `summary_status=ready`, `summary_method=deterministic`, and `content_quality=summary`.
- LLM summarization must not run automatically for every browser page capture.
- Browser smart capture must not store private/login/payment pages, and full page text must remain off by default.
- `task_completed` and `report_generated` are indexable/context eligible for legacy/read-only task flows.
- Task memory policy: `document_summary_created` is visible, indexable, relationship eligible, and context eligible. Operational file tasks such as `file_organize`, `file_move`, `file_copy`, `file_rename`, and `create_folders` are Task History only; they must not create Memory events, be indexed, or be used for relationship/context expansion.
- Document summary task history and memory events must stay lightweight. `document_summary_created` may use a dynamic title/topic and safe output filename metadata, but must not store full source document text, including extracted PDF/DOCX text, in either task history or memory.
- Existing `file_task_prepared`, `file_task_completed`, `file_task_failed`, and `file_task_undone` policy entries are non-indexable/non-context safety nets. New operational file tasks should avoid creating these memory events in the first place.

## Why This Exists

Without eligibility policy, raw chat logs, focus changes, and noisy event streams pollute ChromaDB, create too many relationships, and inflate chat context. MindOS needs local memory that is rich but not chaotic.

## When to Change This File

Update this file whenever adding new event sources, event types, ingestion clients, indexing behavior, relationship rules, or context-building eligibility.
