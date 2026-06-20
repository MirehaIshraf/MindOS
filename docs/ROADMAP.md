# Roadmap

## Current Phase: Chat-First Documentation Alignment

- Align docs around Chat as the primary command surface.
- Define `CommandPlan`, internal ToolRegistry, and validation/confirmation rules.
- Clarify that Connectors handle setup/access/auth.
- Clarify TasksPage future role as Run History, pending confirmations, and debug visibility.
- Preserve current branch caveats: GitHub read-only POC, Jira placeholder/mock-only, Gmail OAuth task POC, Email MCP separate from Gmail.

## Phase 1: Chat-First Shell And CommandPlan Persistence

- Add `CommandPlan` model and repository.
- Add Chat planner service that turns user requests into structured command plans.
- Add plan cards in Chat for previews, pending confirmations, and blocked reasons.
- Make TasksPage visually behave like Run History / pending confirmations instead of the primary task input.
- Keep raw chat messages non-indexable.

## Phase 2: Read-Only ToolRegistry

- Implement internal ToolRegistry and ToolExecutor.
- Add read-only tools:
  - `memory.search`
  - `files.search_connected`
  - `gmail.search_unread`
  - `jira.search_issues` when a real Jira connector is connected
  - `github.search_issues` / GitHub read tools when GitHub is connected
- Persist sanitized tool results in command history, not Memory by default.
- Ensure credentials and tokens never appear in tool results.

## Phase 3: Confirmation And Side-Effect Execution

- Add risk-aware CommandPlan validation.
- Add preview/confirmation cards in Chat.
- Support side-effect tools only after explicit confirmation:
  - Gmail draft/send through the Gmail connector.
  - File summary/report writes through browser-selected or connected folders.
  - File move/organize only with validated preview and confirmation.
- Keep high-risk destructive tools disabled.

## Phase 4: Move Existing Working Flows Into Chat

- Resume/report -> Gmail draft/send with attachment preview.
- Browser/file/document context -> summary/report -> Gmail attachment.
- Folder organize flow from Chat with scan, plan, preview, and confirmation.
- Logs -> report/summary flow from Chat.
- Preserve existing POC routes until Chat flow is stable.

## Phase 5: Jira And GitHub Write Tools

- Add Jira issue/comment tools only after a real Jira connector exists.
- Add GitHub issue/comment/create-pull-request tools through the GitHub connector.
- Keep GitHub API actions separate from local Git status/diff/commit/push.
- Require preview, capability checks, and explicit confirmation for every external write.
- Keep delete, destructive transitions, force push, reset, clean, rebase, branch delete, repo delete, and issue delete disabled.

## Phase 6: UI Polish

- Improve Chat plan cards, confirmation cards, and progress cards.
- Improve markdown, tables, source previews, and result formatting.
- Support light/dark polish.
- Stream progress for long-running command plans.
- Keep advanced/debug details in Run History rather than cluttering Chat.

## Desktop Phase

- Tauri shell.
- Windows installer.
- Local runtime manager.
- Optional model packs.
- Later macOS/Linux.
