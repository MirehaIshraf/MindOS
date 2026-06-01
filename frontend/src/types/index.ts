export type BackendHealth = {
  status: string;
  app: string;
  environment: string;
  storage: string;
  database_path?: string;
  event_count: number;
  task_count?: number;
  chat_session_count?: number;
  chat_message_count?: number;
  search_mode?: string;
};

export type ModelRuntimeStatus = {
  status_generated_at?: string;
  status_request_id?: string;
  status_warnings?: string[];
  local_llm_enabled: boolean;
  ollama_available: boolean;
  chat_model: string;
  active_llm: string;
  ollama_models: string[];
  ollama_num_ctx?: number;
  chat_context_direct_limit?: number;
  chat_context_related_per_event?: number;
  chat_context_max_total_chars?: number;
  chat_history_limit?: number;
  tasks_status?: string;
  selected_chat_model?: string;
  available_chat_models_count?: number;
  available_chat_models?: Array<Pick<ModelConfig, "id" | "display_name" | "provider" | "type" | "available">>;
  providers?: Record<string, { configured: boolean; enabled?: boolean; has_api_key?: boolean; available: boolean | null }>;
  active_provider?: string;
  model_warning?: string | null;
  embeddings_enabled?: boolean;
  embedding_model?: string;
  selected_embedding_model?: string;
  selected_embedding_model_id?: string;
  embedding_index_model?: string | null;
  embedding_index_stale?: boolean;
  embedding_model_available?: boolean;
  chroma_available?: boolean;
  chroma_indexed_count?: number;
  semantic_search_default?: boolean;
  discovered_ollama_models?: string[];
  local_chat_models_count?: number;
  embedding_models_filtered_count?: number;
};

export type BackendStatus = ModelRuntimeStatus & {
  backend: boolean;
  storage: string;
  database_path?: string;
  event_count: number;
  task_count: number;
  chat_session_count: number;
  chat_message_count: number;
  relationship_count: number;
  search_mode: string;
  tasks_status?: string;
};

export type PageRoute = {
  path: string;
  title: string;
};

export type EventSource =
  | "mindos"
  | "manual"
  | "file_system"
  | "vscode"
  | "browser"
  | "vscode_extension"
  | "browser_extension"
  | "activity_tracker"
  | "local_agent"
  | "git"
  | "github"
  | "jira"
  | "logs"
  | "email";

export type MemoryEvent = {
  id: string;
  source: EventSource;
  type: string;
  title: string;
  content: string;
  metadata: Record<string, unknown>;
  timestamp: string;
  created_at: string;
  embedding_status: "not_required" | "pending" | "indexed" | "failed";
  memory_category: string;
  hidden_from_default: boolean;
  is_indexable: boolean;
  is_relationship_eligible: boolean;
  is_context_eligible: boolean;
  related_count?: number;
};

export type RecentEventsResponse = {
  events: MemoryEvent[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
};

export type IngestEventRequest = {
  source: EventSource;
  type: string;
  title: string;
  content?: string;
  metadata?: Record<string, unknown>;
  timestamp?: string | null;
};

export type IngestEventResponse = {
  event_id: string;
  status: "ingested";
};

export type ExternalEventIngestRequest = {
  source: "vscode_extension" | "browser_extension" | "activity_tracker" | "local_agent" | string;
  type: string;
  title?: string;
  content?: string;
  metadata?: Record<string, unknown>;
  timestamp?: string | null;
  client_id?: string | null;
  session_id?: string | null;
};

export type ExternalBulkIngestRequest = {
  events: ExternalEventIngestRequest[];
};

export type ExternalIngestResponse = {
  status: string;
  event_id: string;
  message: string;
};

export type ExternalBulkIngestResponse = {
  status: string;
  ingested: number;
  failed: number;
  event_ids: string[];
  errors: Array<Record<string, unknown>>;
};

export type CollectorClient = {
  id: string;
  name: string;
  type: string;
  enabled: boolean;
  last_seen_at?: string | null;
  events_count: number;
};

export type CollectorClientsResponse = {
  collectors: CollectorClient[];
};

export type ExternalIngestStatusResponse = {
  external_ingest_enabled: boolean;
  supported_sources: string[];
  preferred_event_types: Record<string, string[]>;
  recent_external_events: number;
  collector_clients: CollectorClient[];
  connectors: Connector[];
};

export type DevState = {
  storage: string;
  database_path?: string;
  event_count: number;
  file_system_event_count?: number;
  logs_event_count?: number;
  git_event_count?: number;
  saved_sources_count?: number;
  import_runs_count?: number;
  task_count: number;
  chat_session_count: number;
  chat_message_count: number;
  relationship_count?: number;
  relationships_by_type?: Record<string, number>;
  events_by_source: Record<string, number>;
  events_by_category: Record<string, number>;
  memory_policy?: Record<string, number>;
  local_llm_enabled?: boolean;
  ollama_available?: boolean;
  chat_model?: string;
  active_llm?: string;
  ollama_models?: string[];
  selected_chat_model?: string;
  available_chat_models_count?: number;
  providers?: Record<string, { configured: boolean; enabled?: boolean; has_api_key?: boolean; available: boolean | null }>;
  ollama_num_ctx?: number;
  chat_context_direct_limit?: number;
  chat_context_related_per_event?: number;
  chat_context_max_total_chars?: number;
  chat_history_limit?: number;
  embeddings?: EmbeddingStatusResponse;
};

export type SeedSampleEventsResponse = {
  status: "seeded";
  count: number;
  event_ids: string[];
};

export type SearchResult = {
  event_id: string;
  source: string;
  type: string;
  title: string;
  content_preview: string;
  metadata: Record<string, unknown>;
  timestamp: string;
  created_at: string;
  embedding_status: string;
  memory_category: string;
  hidden_from_default: boolean;
  is_indexable: boolean;
  is_relationship_eligible: boolean;
  is_context_eligible: boolean;
  score: number;
  match_reason: string;
  related_count: number;
  related_preview: Array<Record<string, unknown>>;
};

export type SearchResponse = {
  query: string;
  results: SearchResult[];
  total: number;
  search_mode: string;
  requested_search_mode?: string | null;
  warning?: string | null;
};

export type SearchStatsResponse = {
  total_events: number;
  visible_default_events: number;
  hidden_events: number;
  by_source: Record<string, number>;
  by_category: Record<string, number>;
  last_ingested_at: string | null;
};

export type ChatSource = {
  event_id: string;
  source: string;
  type: string;
  title: string;
  content_preview: string;
  score: number;
  match_reason: string;
  timestamp: string;
  source_kind?: "direct" | "related" | string;
  relationship_type?: string | null;
  relationship_reason?: string | null;
  metadata?: Record<string, unknown>;
  url?: string | null;
  path?: string | null;
};

export type ChatContextStats = {
  direct_count: number;
  related_count: number;
  relationship_count: number;
  sources: string[];
  token_estimate: number;
  warnings?: string[];
  intent?: string | null;
  retrieval_profile?: string | null;
  search_terms?: string[];
  preferred_sources?: string[];
  excluded_types?: string[];
  is_follow_up?: boolean;
  resolved_query?: string | null;
  primary_source_event_id?: string | null;
  primary_source_title?: string | null;
  primary_source_url?: string | null;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  sourcesUsed?: ChatSource[];
  model?: string;
  provider?: string;
  modelDisplayName?: string;
  searchMode?: string;
  taskHint?: string | null;
  taskInstruction?: string;
  contextSummary?: string;
  contextStats?: ChatContextStats | null;
  warning?: string | null;
  answerStyle?: string;
  intent?: string | null;
  isFollowUp?: boolean;
  resolvedQuery?: string | null;
};

export type ChatRequestPayload = {
  message: string;
  history: Array<{ role: string; content: string; timestamp?: string }>;
  use_context?: boolean;
  session_id?: string | null;
  model_id?: string | null;
};

export type ChatResponse = {
  session_id: string;
  reply: string;
  sources_used: ChatSource[];
  model: string;
  provider: string;
  model_display_name: string;
  search_mode: string;
  task_hint?: string | null;
  warning?: string | null;
  context_summary: string;
  context_stats?: ChatContextStats | null;
  answer_style: string;
  intent?: string | null;
  is_follow_up?: boolean;
  resolved_query?: string | null;
};

export type ChatSession = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

export type ChatSessionsResponse = {
  sessions: ChatSession[];
  total: number;
};

export type StoredChatMessage = {
  id: string;
  session_id: string;
  role: "user" | "assistant" | string;
  content: string;
  sources_used?: ChatSource[];
  model?: string | null;
  provider?: string | null;
  model_display_name?: string | null;
  search_mode?: string | null;
  task_hint?: string | null;
  context_summary?: string | null;
  context_stats?: ChatContextStats | null;
  warning?: string | null;
  answer_style?: string | null;
  intent?: string | null;
  is_follow_up?: boolean;
  resolved_query?: string | null;
  metadata?: Record<string, unknown>;
  created_at: string;
};

export type TestLLMResponse = {
  model: string;
  provider?: string;
  model_display_name?: string;
  reply: string;
  warning: string | null;
};

export type ChatMessagesResponse = {
  messages: StoredChatMessage[];
  total: number;
};

export type ModelProvider = {
  id: string;
  name: string;
  type: "local" | "cloud" | string;
  configured: boolean;
  enabled: boolean;
  requires_api_key: boolean;
  has_api_key: boolean;
  available: boolean | null;
  privacy_note: string;
};

export type ModelConfig = {
  id: string;
  provider: string;
  display_name: string;
  model_id: string;
  type: "local" | "cloud" | string;
  enabled: boolean;
  configured: boolean;
  available: boolean;
  status: string;
  supports_tools: boolean;
  supports_vision: boolean;
  default_context_profile: string;
  privacy_level: "local_private" | "cloud_external" | string;
  description: string;
};

export type ModelSettingsResponse = {
  providers: ModelProvider[];
  models: ModelConfig[];
  selected_chat_model: string;
};

export type EmbeddingModelConfig = {
  id: string;
  provider: string;
  display_name: string;
  model_id: string;
  type: "local" | string;
  enabled: boolean;
  configured: boolean;
  available: boolean;
  dimension?: number | null;
  description: string;
  install_command?: string | null;
};

export type EmbeddingSettingsResponse = {
  embedding_enabled: boolean;
  selected_embedding_model: string;
  selected_embedding_model_id: string;
  index_model_id?: string | null;
  index_stale: boolean;
  models: EmbeddingModelConfig[];
};

export type ChatModelsResponse = {
  models: ModelConfig[];
  selected_chat_model: string;
  warning?: string | null;
};

export type TaskPreview = Record<string, unknown>;

export type TaskPlan = {
  task_type: string;
  confidence: number;
  title?: string | null;
  description?: string | null;
  priority?: string | null;
  recipient?: string | null;
  subject?: string | null;
  body?: string | null;
  repo?: string | null;
  branch_name?: string | null;
  commit_message?: string | null;
  pr_title?: string | null;
  pr_body?: string | null;
  report_markdown?: string | null;
  evidence: Array<Record<string, unknown>>;
  missing_fields: string[];
  safety_notes: string[];
};

export type TaskPlanningResponse = {
  plan: TaskPlan;
  model: string;
  provider: string;
  warning?: string | null;
  context_summary?: string | null;
  context_stats?: Record<string, unknown> | null;
};

export type TaskResponse = {
  task_id: string | null;
  status: string;
  task_type: string;
  instruction: string;
  preview: TaskPreview | Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  confirmation_token: string | null;
  message: string;
  sources_used?: Array<Record<string, unknown>>;
  planner_model?: string | null;
  planner_provider?: string | null;
  planner_warning?: string | null;
  context_stats?: Record<string, unknown> | null;
};

export type TaskHistoryItem = {
  id: string;
  task_type: string;
  instruction: string;
  status: string;
  preview: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  confirmation_token?: string | null;
  created_at: string;
  completed_at: string | null;
  planner_model?: string | null;
  planner_provider?: string | null;
  planner_warning?: string | null;
  context_stats?: Record<string, unknown> | null;
  sources_used?: Array<Record<string, unknown>>;
};

export type TaskHistoryResponse = {
  tasks: TaskHistoryItem[];
  total: number;
};

export type FileSnapshotItem = {
  name: string;
  path: string;
  relative_path: string;
  extension: string;
  size_bytes: number;
  modified_at: string;
  is_dir: boolean;
  is_hidden: boolean;
};

export type FileSnapshotResponse = {
  root_path: string;
  files: FileSnapshotItem[];
  folders: FileSnapshotItem[];
  total_files: number;
  total_folders: number;
  warnings: string[];
};

export type FileOperation = {
  type: "create_folder" | "move_file" | "copy_file" | "rename_file";
  from_path?: string | null;
  to_path?: string | null;
  path?: string | null;
  reason: string;
};

export type FileTaskPlan = {
  task_id: string;
  task_type: string;
  root_path: string;
  instruction: string;
  summary: string;
  risk_level: "low" | "medium" | "high";
  requires_confirmation: boolean;
  operations: FileOperation[];
  skipped: Array<{ path: string; reason: string }>;
  warnings: string[];
  blocked_reasons: string[];
  status: "draft" | "awaiting_confirmation" | "blocked" | "completed" | "failed" | "partial" | "undone";
  planner_model?: string | null;
  planner_provider?: string | null;
  planner_warning?: string | null;
};

export type FileTaskExecutionResult = {
  task_id: string;
  status: "completed" | "failed" | "partial" | "cancelled";
  created_folders: number;
  moved_files: number;
  copied_files: number;
  renamed_files: number;
  skipped: Array<{ path: string; reason: string }>;
  errors: string[];
  undo_available: boolean;
};

export type FileTaskUndoResult = {
  task_id: string;
  status: "undone" | "partial" | "failed";
  undone_operations: number;
  errors: string[];
};

export type FileTaskRecord = {
  task_id: string;
  root_path: string;
  instruction: string;
  status: string;
  plan: FileTaskPlan;
  execution?: FileTaskExecutionResult | null;
  undo: Array<Record<string, unknown>>;
  created_at: string;
  updated_at: string;
  executed_at?: string | null;
  undone_at?: string | null;
};

export type FileTaskRecentResponse = {
  tasks: FileTaskRecord[];
  total: number;
};

export type Connector = {
  id: string;
  name: string;
  type: "vscode" | "browser" | "github" | "jira" | "email" | "file_system" | "logs" | "git" | string;
  description: string;
  enabled: boolean;
  configured: boolean;
  connected: boolean;
  status: "off" | "connected" | "disconnected" | "needs_configuration" | "error" | string;
  event_count: number;
  last_event_at?: string | null;
  last_seen_at?: string | null;
  config_summary: Record<string, unknown>;
  supports_toggle: boolean;
  supports_config: boolean;
  supports_manual_import: boolean;
  supports_live_events: boolean;
};

export type ConnectorListResponse = {
  connectors: Connector[];
};

export type ConnectorToggleResponse = {
  id: string;
  enabled: boolean;
  status: string;
  message: string;
};

export type ConnectorConfigResponse = {
  id: string;
  config: Record<string, unknown>;
  configured: boolean;
};

export type ConnectorSource = {
  id: string;
  connector_type: "file_system" | "logs" | "git" | string;
  name: string;
  path: string;
  config: Record<string, unknown>;
  enabled: boolean;
  created_at: string;
  updated_at: string;
  last_import_at?: string | null;
  last_import_status?: string | null;
  last_import_message?: string | null;
};

export type ConnectorSourcesResponse = {
  sources: ConnectorSource[];
  total: number;
};

export type ConnectorSourceCreateRequest = {
  connector_type: string;
  name: string;
  path: string;
  config?: Record<string, unknown>;
  enabled?: boolean;
};

export type ConnectorSourceUpdateRequest = {
  name?: string | null;
  path?: string | null;
  config?: Record<string, unknown> | null;
  enabled?: boolean | null;
};

export type ImportRun = {
  id: string;
  source_id?: string | null;
  connector_type: string;
  path: string;
  status: string;
  imported_count: number;
  skipped_count: number;
  failed_count: number;
  message: string;
  result_json: Record<string, unknown>;
  started_at: string;
  completed_at: string;
};

export type ImportRunsResponse = {
  runs: ImportRun[];
  total: number;
};

export type RunConnectorSourceImportResponse = {
  source: ConnectorSource;
  import_run: ImportRun;
  result: Record<string, unknown>;
};

export type FileImportPayload = {
  folder_path: string;
  recursive: boolean;
  max_files: number;
  max_file_size_kb: number;
  allowed_extensions?: string[] | null;
};

export type FilePreviewResult = {
  total_candidates: number;
  preview_files: Array<Record<string, string | number>>;
  skipped: Array<Record<string, string | number>>;
};

export type FileImportResult = {
  imported_count: number;
  skipped_count: number;
  failed_count: number;
  events_created: string[];
  skipped: Array<Record<string, string | number>>;
  failed: Array<Record<string, string | number>>;
  message: string;
};

export type LogImportPayload = {
  file_path: string;
  max_lines: number;
  only_errors: boolean;
  group_similar?: boolean;
};

export type LogLinePreview = {
  line_number: number;
  level: string;
  message: string;
  timestamp: string | null;
  raw: string;
};

export type LogPreviewResult = {
  file_path: string;
  total_lines_scanned: number;
  matched_lines: number;
  preview: LogLinePreview[];
  skipped: Array<Record<string, string | number>>;
  message: string;
};

export type LogImportResult = {
  imported_count: number;
  skipped_count: number;
  failed_count: number;
  events_created: string[];
  groups_created: number;
  message: string;
};

export type ClearLogEventsResponse = {
  status: "cleared";
  deleted_events: number;
  deleted_relationships: number;
  deleted_vectors?: number | null;
};

export type ClearFileSystemEventsResponse = {
  status: "cleared";
  deleted_events: number;
  deleted_relationships: number;
  deleted_vectors?: number | null;
};

export type ClearGitEventsResponse = {
  status: "cleared";
  deleted_events: number;
  deleted_relationships: number;
  deleted_vectors?: number | null;
};

export type ClearAllDevDataResponse = {
  status: "cleared";
  events_deleted: number;
  relationships_deleted: number;
  tasks_deleted: number;
  chats_deleted: number;
  vectors_deleted: number | null;
  import_runs_deleted: number;
  saved_sources_deleted: number;
  model_settings_cleared: boolean;
  warnings?: string[];
};

export type BrowserDedupeResponse = {
  groups_found: number;
  events_deleted: number;
  events_updated: number;
};

export type GitImportPayload = {
  repo_path: string;
  max_commits: number;
  include_diff_summary?: boolean;
  include_status?: boolean;
};

export type GitCommitPreview = {
  hash: string;
  short_hash: string;
  author: string;
  date: string;
  message: string;
};

export type GitPreviewResult = {
  repo_path: string;
  repo_name: string;
  repo_root?: string | null;
  current_branch: string | null;
  is_git_repo: boolean;
  recent_commits: GitCommitPreview[];
  status_summary: Record<string, number>;
  message: string;
};

export type GitImportResult = {
  imported_count: number;
  skipped_count: number;
  failed_count: number;
  events_created: string[];
  message: string;
};

export type Relationship = {
  id: string;
  from_event_id: string;
  to_event_id: string;
  relationship_type: string;
  strength: number;
  reason: string;
  created_at: string;
};

export type RelatedEvent = {
  event: MemoryEvent;
  relationship: Relationship;
};

export type RelatedEventsResponse = {
  event_id: string;
  related: RelatedEvent[];
  total: number;
};

export type ContextEvent = {
  event_id: string;
  source: string;
  type: string;
  title: string;
  content_preview: string;
  content: string;
  metadata: Record<string, unknown>;
  timestamp: string;
  score: number | null;
  match_reason: string | null;
  memory_category: string;
  hidden_from_default: boolean;
  is_indexable?: boolean;
  is_relationship_eligible?: boolean;
  is_context_eligible?: boolean;
};

export type ContextRelationship = {
  from_event_id: string;
  to_event_id: string;
  relationship_type: string;
  strength: number;
  reason: string;
};

export type ContextSourceGroup = {
  source: string;
  count: number;
  event_ids: string[];
};

export type ContextPackage = {
  query: string;
  direct_events: ContextEvent[];
  related_events: ContextEvent[];
  relationships: ContextRelationship[];
  source_groups: ContextSourceGroup[];
  summary: string;
  token_estimate: number;
  warnings: string[];
  metadata?: Record<string, unknown>;
};

export type EmbeddingStatusResponse = {
  enabled: boolean;
  embedding_model: string;
  selected_embedding_model?: string;
  selected_embedding_model_id?: string;
  index_model?: string | null;
  index_stale?: boolean;
  embedding_model_available?: boolean;
  ollama_available: boolean;
  chroma_available: boolean;
  chroma_path: string;
  indexed_count: number;
  event_status: Record<string, number>;
  total_events?: number;
  indexable_events?: number;
  non_indexable_events?: number;
  relationship_eligible_events?: number;
  context_eligible_events?: number;
  hidden_events?: number;
};

export type EmbeddingReindexResponse = {
  indexed: number;
  failed: number;
  skipped: number;
  skipped_not_indexable?: number;
  total: number;
  errors: Array<Record<string, unknown>>;
};
