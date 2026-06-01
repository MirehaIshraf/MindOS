# Current State

## Last Updated

Last updated: 2026-06-01

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
| Chat | Working | Uses QueryIntentService, ContextBuilderService, and selected model through ModelRouter. |
| Tasks | Paused/Experimental | Backend and page still exist, but product priority is data collection. |
| File connector | Working | Path-based folder import with clear events. |
| Logs connector | Working | Path-based log import with clear events. |
| Local Git connector | Working | Read-only local Git import with clear events. |
| Saved sources | Working/Partial | Saved connector sources and import runs exist for file/log/git. |
| External ingestion | Working/Partial | API exists for VSCode/browser/activity/local-agent collectors; disabled VSCode/Browser connectors reject their events. |
| VSCode extension | Working | MVP exists in `extensions/vscode`; installable local VSIX flow with backend-controlled runtime polling. |
| Browser extension | Working/Partial | MVP exists in `extensions/browser`; manual page/selection save plus privacy-first smart capture with hard DOM access diagnostics, generic visible-text extraction, backend content-quality validation, and normalized URL upsert. |
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
| Tasks | Paused/Experimental | Route/page exists but is hidden from main sidebar. |
| Playbooks | Placeholder | Route/page exists but not a current priority. |

## Implemented Connectors

- File System path import: working; clear file events exists.
- Logs path import: working; clear log events exists.
- Local Git path import: working and read-only; clear Git events exists.
- VSCode extension MVP: working; packaged local install flow, polls MindOS runtime, sends workspace/file-save events after the MindOS VSCode connector toggle is enabled.
- Browser extension MVP: working; manual popup save flow for pages, selected text, and notes after the MindOS Browser connector toggle is enabled. Smart capture can record hidden search evidence and visible important work/research pages with readable context when enabled. Captured pages are upserted by normalized URL, repeat visits update visit metadata, and Hugging Face model/dataset/docs pages are classified as important.
- Saved connector sources: working/partial for file system, logs, and Git.
- Import history: working/partial for saved source imports.
- External ingestion API: working/partial; collector clients are derived from event metadata.

## Planned Collectors

- Activity tracker
- Local agent collector

GitHub, Jira, and Email appear as disabled/unconfigured connector placeholders. They do not perform real integration work yet.

These should send data to `/ingest/external` or `/ingest/external/bulk`.

## Current Known Bugs / Risks

- Tasks module is paused/unstable. Do not prioritize task execution now.
- Dev page has historically had status flicker/false unavailable issues. It should use `/status` as source of truth.
- Raw chat events should not be indexed or related. Use memory policy and clean indexes if old data polluted Chroma/relationships.
- Model and embedding registries must not mix chat and embedding models.
- Ollama must not auto-start from status checks.
- VSCode extension MVP can be packaged with `npm run package` and installed into normal VSCode. F5/debug host is only needed for extension development.
- Browser extension does not request browser history permission or perform full unrestricted history tracking. Smart capture is limited to active-tab dwell events, search queries, and work/research page classification with private/noisy pages filtered. Page context extraction collects visible readable text only, not raw HTML or form/input values.
- Browser extension includes a hard DOM access diagnostic and generic visible-text extraction diagnostics. Backend validation prevents placeholder failure text from being counted as captured content. Site-specific extractors and automatic summarization are not the focus until basic DOM extraction is verified.
- Chat retrieval now uses deterministic query intent routing, but retrieval quality still needs tuning with real memory data.
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
6. Later: revisit task execution.
