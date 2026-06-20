# Decisions

## 001 SQLite before PostgreSQL

Decision: Use SQLite for the desktop MVP.

Reason: Desktop MVP should not require a separate database service. SQLite is simpler for local installer packaging.

## 002 ChromaDB is an index, SQLite is source of truth

Decision: SQLite stores raw events and metadata. ChromaDB stores vectors only.

Reason: Vector indexes can be rebuilt. Raw data must remain stable.

## 003 Raw chats are stored but not indexed

Decision: Store chat messages/responses for history, but exclude them from default indexing, relationships, and chat context.

Reason: Raw chats create noisy relationships and context explosion.

## 004 Tasks are experimental with explicit POC exceptions

Decision: Tasks remain experimental. File organization, document summary, and Gmail draft/send actions are allowed as POC features when they follow preview, confirmation, and allowlisted execution.

Reason: Data collection and memory quality remain priorities, but the user explicitly requested safe task execution POCs. Safety rules still apply.

## 005 Ollama must not auto-start

Decision: The app must not start Ollama automatically from status/dev/model checks.

Reason: The user should control local runtimes and resource usage.

## 006 Model registry separates chat and embedding models

Decision: Chat model registry and embedding model registry are separate.

Reason: They serve different purposes and should not pollute each other's UI.

## 007 Connectors are explicit user action

Decision: No automatic folder scanning or tracking without explicit connector/user action.

Reason: Privacy and predictability.

## 008 Provider failure is not backend failure

Decision: If Ollama/Chroma/cloud provider fails, backend should remain online.

Reason: Optional subsystems should degrade gracefully.

## 009 Gmail connector separated from Email MCP

Decision: Gmail has a dedicated connector for local Gmail OAuth and Gmail-specific tasks. Generic Email MCP remains separate for custom/corporate providers.

Reason: Avoid provider confusion, mock-provider leakage, and wrong capability routing.

## 010 Safe task execution allowed as POC after explicit user request

Decision: Tasks are no longer fully paused. File/document/Gmail tasks are allowed as POC features when they follow preview plus confirmation.

Reason: The user explicitly requested task execution. Safety rules still apply.

## 011 Gmail send requires explicit confirmation

Decision: Gmail send can only happen after editable preview and final confirmation.

Reason: Sending email is external side-effecting behavior and must never happen silently.

## 012 Attachments require user selection

Decision: MindOS may suggest attachment candidates, but files must be shown and selected/confirmed by the user.

Reason: Prevent accidental sensitive file attachment.

## 013 GitHub API actions and local Git actions are separate

Decision: GitHub connector handles API actions such as issues/PRs. Local Git connector handles repo status/diff/commit/push.

Reason: Pushing to GitHub is a local Git remote operation, not just GitHub API.

## 014 Chat is the primary command surface

Decision: Chat becomes the primary place where users ask MindOS to plan and run work.

Reason: Users expect one conversational command surface. Connectors should stay focused on setup/access, not task complexity.

## 015 TasksPage becomes Run History and Debug

Decision: TasksPage should evolve into Run History, pending confirmations, and debug visibility for command plans/runs.

Reason: This preserves useful task visibility without splitting the command UX away from Chat.

## 016 Internal ToolRegistry for safe execution

Decision: MindOS will use an internal MCP-style ToolRegistry of allowlisted typed tools wrapping existing services/connectors.

Reason: This keeps execution auditable and typed while avoiding dependency on external MCP servers for core Gmail/Jira/GitHub flows.

## 017 Connector auth remains inside connector services

Decision: ToolRegistry does not own auth. Gmail, GitHub, future Jira, Email MCP, and File System access remain inside their connector/service boundaries.

Reason: Credentials, scopes, selected repositories/folders, and provider capabilities must stay centralized and protected.

## 018 Jira/GitHub writes are allowed only through validated tools

Decision: Future Jira/GitHub write actions may be added only as allowlisted tools with connector state checks, preview, backend validation, and explicit confirmation. This supersedes the old absolute "no real Jira/GitHub writes" rule.

Reason: The product direction includes useful developer actions, but only through controlled, confirmable execution.

## 019 Destructive tools are disabled for the demo

Decision: Deletes, destructive transitions, bulk destructive operations, repository deletes, issue deletes, force push, branch delete, reset, clean, and rebase remain disabled.

Reason: The demo should support useful POC actions without exposing irreversible or high-risk operations.

## 020 Direct MCP/tool execution cannot bypass CommandPlan validation

Decision: Any internal tool execution triggered from Chat must pass through CommandPlan validation and capability/risk checks.

Reason: The model should propose plans, not directly execute tools.

## 021 GitHub API tools and local Git tools remain separate

Decision: GitHub API tools handle GitHub repository APIs such as issues, comments, PRs, and repository metadata. Local Git tools handle local repository status, diff, commit, and push.

Reason: API actions and local Git command actions have different credentials, risk models, and validation requirements.
