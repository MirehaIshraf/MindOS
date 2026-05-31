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
| vscode_extension/editor_file_saved | Yes | Yes | Yes | Yes | Useful editor event, especially when safe content snippets are included. |
| vscode_extension/editor_file_opened | No | No | No | No | Open events are noisy and hidden/non-indexable by default. |
| vscode_extension/editor_workspace_opened | Yes | Yes | Yes | Yes | Useful session/workspace context. |
| browser_extension/browser_page_visited | Yes unless private | Yes unless private | Yes unless private | Yes unless private | If `metadata.private=true`, event is hidden but currently remains eligible. Revisit if private browsing should be fully excluded. |
| activity_tracker/app_focus_changed | No | No | No | No | Raw activity tracker events are noisy. |
| activity_tracker/work_session_summary | No by current source-level policy | No by current source-level policy | No by current source-level policy | No by current source-level policy | Intended direction is summarized tracker events should become indexable; current code treats all activity_tracker events as hidden/non-indexable. |
| mindos/chat_message | No | No | No | No | Stored for history and Chats category only. |
| mindos/chat_response | No | No | No | No | Stored for history and Chats category only. |
| mindos/chat_summary | Yes | Yes | Yes | Yes | Future preferred representation of chat history. |
| mindos/task_completed | Yes | Yes | Yes | Yes | Task lifecycle events are still stored even though Tasks are paused. |
| mindos/report_generated | Yes | Yes | Yes | Yes | Reports are useful memory. |
| local_agent/agent_observation | No | No | No | No | Raw agent observations are noisy by default. |
| local_agent/agent_summary | Yes | Yes | Yes | Yes | Summaries are preferred over raw agent streams. |
| manual/note | Yes | Yes | Yes | Yes | Manual captured memory. |

## Rules

- Raw `chat_message` and `chat_response` events are stored but not indexed, related, or context eligible.
- `chat_summary` is indexable and context eligible.
- Raw activity tracker events are hidden and non-indexable by default.
- Activity summaries are intended to become indexable, but the current source-level code treats all `activity_tracker` events as hidden/non-indexable.
- File, log, Git, VSCode saved/workspace, browser extension, and useful captured events are indexable/context eligible by default.
- VSCode file-opened events are stored but hidden/non-indexable by default to avoid open-file noise.
- `task_completed` and `report_generated` are indexable/context eligible.

## Why This Exists

Without eligibility policy, raw chat logs, focus changes, and noisy event streams pollute ChromaDB, create too many relationships, and inflate chat context. MindOS needs local memory that is rich but not chaotic.

## When to Change This File

Update this file whenever adding new event sources, event types, ingestion clients, indexing behavior, relationship rules, or context-building eligibility.
