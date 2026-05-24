export type BackendHealth = {
  status: string;
  app: string;
  environment: string;
  storage: string;
  event_count: number;
  task_count?: number;
  chat_session_count?: number;
  chat_message_count?: number;
  search_mode?: string;
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
};

export type RecentEventsResponse = {
  events: MemoryEvent[];
  total: number;
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

export type DevState = {
  storage: string;
  event_count: number;
  task_count: number;
  chat_session_count: number;
  chat_message_count: number;
  events_by_source: Record<string, number>;
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
  score: number;
  match_reason: string;
};

export type SearchResponse = {
  query: string;
  results: SearchResult[];
  total: number;
  search_mode: string;
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
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  sourcesUsed?: ChatSource[];
  model?: string;
  searchMode?: string;
  taskHint?: string | null;
  taskInstruction?: string;
};

export type ChatRequestPayload = {
  message: string;
  history: Array<{ role: string; content: string; timestamp?: string }>;
  use_context?: boolean;
  session_id?: string | null;
};

export type ChatResponse = {
  session_id: string;
  reply: string;
  sources_used: ChatSource[];
  model: string;
  search_mode: string;
  task_hint?: string | null;
  warning?: string | null;
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
  search_mode?: string | null;
  task_hint?: string | null;
  created_at: string;
};

export type ChatMessagesResponse = {
  messages: StoredChatMessage[];
  total: number;
};

export type TaskPreview = Record<string, string | null | undefined>;

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
};

export type TaskHistoryResponse = {
  tasks: TaskHistoryItem[];
  total: number;
};
