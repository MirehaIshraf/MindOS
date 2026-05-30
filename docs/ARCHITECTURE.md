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

User message -> selected model -> ContextBuilderService -> SearchService direct events -> RelationshipService related events -> formatted context -> ModelRouterService -> provider/FakeLLM -> response cleaner -> saved chat session and chat memory events

Chat context should use context-eligible events. Raw chat_message and chat_response memory events are stored for history but excluded from normal chat RAG context.

## Connector Flow

User explicitly imports or collector sends event -> ExternalIngestService/IngestionService or connector import service -> EventRepository -> MemoryPolicyService -> EmbeddingIndexService if eligible -> RelationshipService if eligible

File system, logs, and local Git imports are manual path-based flows. Saved connector sources allow re-importing previously configured paths. External collectors use `/ingest/external`.

## Semantic Search Flow

SQLite event -> embedding text builder -> Ollama embedding model -> ChromaDB vector index -> search query embedding -> vector results -> full event fetch from SQLite

SQLite remains source of truth. ChromaDB stores vectors and lightweight metadata only.
