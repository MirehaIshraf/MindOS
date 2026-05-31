import axios from "axios";
import type { AxiosError } from "axios";

import type {
  BackendHealth,
  BackendStatus,
  ChatMessagesResponse,
  ChatModelsResponse,
  ChatRequestPayload,
  ChatResponse,
  ChatSessionsResponse,
  ContextPackage,
  ClearAllDevDataResponse,
  ClearFileSystemEventsResponse,
  ClearLogEventsResponse,
  ClearGitEventsResponse,
  ConnectorConfigResponse,
  ConnectorListResponse,
  ConnectorSource,
  ConnectorSourceCreateRequest,
  ConnectorSourcesResponse,
  ConnectorSourceUpdateRequest,
  ConnectorToggleResponse,
  CollectorClientsResponse,
  DevState,
  EmbeddingReindexResponse,
  EmbeddingSettingsResponse,
  EmbeddingStatusResponse,
  FileImportPayload,
  FileImportResult,
  FilePreviewResult,
  GitImportPayload,
  GitImportResult,
  GitPreviewResult,
  LogImportPayload,
  LogImportResult,
  LogPreviewResult,
  ImportRunsResponse,
  ModelConfig,
  ModelSettingsResponse,
  IngestEventRequest,
  IngestEventResponse,
  ExternalBulkIngestRequest,
  ExternalBulkIngestResponse,
  ExternalEventIngestRequest,
  ExternalIngestResponse,
  ExternalIngestStatusResponse,
  MemoryEvent,
  RelatedEventsResponse,
  RecentEventsResponse,
  RunConnectorSourceImportResponse,
  SearchResponse,
  SearchStatsResponse,
  SeedSampleEventsResponse,
  TaskHistoryResponse,
  TaskPlanningResponse,
  TaskResponse,
  TestLLMResponse,
} from "../types";

export const api = axios.create({
  baseURL: "http://localhost:8000",
  timeout: 5000,
});

export function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<{ detail?: unknown; message?: string }>;
    if (axiosError.response?.data?.detail) {
      return typeof axiosError.response.data.detail === "string"
        ? axiosError.response.data.detail
        : JSON.stringify(axiosError.response.data.detail);
    }
    if (axiosError.response?.data?.message) {
      return axiosError.response.data.message;
    }
    if (axiosError.response) {
      return `Request failed with status ${axiosError.response.status}`;
    }
    if (axiosError.request) {
      return "Backend may be offline.";
    }
  }
  return error instanceof Error ? error.message : "Unknown error";
}

export const getApiErrorMessage = getErrorMessage;

function logApiError(endpoint: string, error: unknown) {
  console.error(`${endpoint} failed`, error);
}

export async function getHealth(): Promise<BackendHealth> {
  const response = await api.get<BackendHealth>("/health");
  return response.data;
}

export async function getStatus(): Promise<BackendStatus> {
  try {
    const response = await api.get<BackendStatus>("/status", { timeout: 30000 });
    return response.data;
  } catch (error) {
    logApiError("GET /status", error);
    throw error;
  }
}

export const healthCheck = getHealth;

export async function getRecentEvents(
  source?: string,
  limit = 20,
  category?: string,
  includeHidden = false,
): Promise<RecentEventsResponse> {
  const response = await api.get<RecentEventsResponse>("/events/recent", {
    params: {
      source: source || undefined,
      limit,
      category: category || undefined,
      include_hidden: includeHidden,
    },
  });
  return response.data;
}

export async function seedSampleEvents(): Promise<SeedSampleEventsResponse> {
  const response = await api.post<SeedSampleEventsResponse>("/dev/sample-events");
  return response.data;
}

export async function clearEvents(): Promise<{ status: "cleared" }> {
  const response = await api.delete<{ status: "cleared" }>("/dev/clear-events");
  return response.data;
}

export async function clearTasks(): Promise<{ status: "cleared" }> {
  const response = await api.delete<{ status: "cleared" }>("/dev/clear-tasks");
  return response.data;
}

export async function clearChats(): Promise<{ status: "cleared" }> {
  const response = await api.delete<{ status: "cleared" }>("/dev/clear-chats");
  return response.data;
}

export async function clearAllDevData(options: {
  clear_saved_sources?: boolean;
  clear_model_settings?: boolean;
} = {}): Promise<ClearAllDevDataResponse> {
  const response = await api.delete<ClearAllDevDataResponse>("/dev/clear-all", {
    data: {
      clear_saved_sources: options.clear_saved_sources ?? false,
      clear_model_settings: options.clear_model_settings ?? false,
    },
    timeout: 30000,
  });
  return response.data;
}

export async function getDevState(): Promise<DevState> {
  const response = await api.get<DevState>("/dev/state");
  return response.data;
}

export async function ingestEvent(data: IngestEventRequest): Promise<IngestEventResponse> {
  const response = await api.post<IngestEventResponse>("/ingest", data);
  return response.data;
}

export async function ingestExternalEvent(data: ExternalEventIngestRequest): Promise<ExternalIngestResponse> {
  const response = await api.post<ExternalIngestResponse>("/ingest/external", data);
  return response.data;
}

export async function ingestExternalEventsBulk(data: ExternalBulkIngestRequest): Promise<ExternalBulkIngestResponse> {
  const response = await api.post<ExternalBulkIngestResponse>("/ingest/external/bulk", data, { timeout: 30000 });
  return response.data;
}

export async function getIngestStatus(): Promise<ExternalIngestStatusResponse> {
  const response = await api.get<ExternalIngestStatusResponse>("/ingest/status");
  return response.data;
}

export async function searchEvents(
  query: string,
  sources?: string[],
  limit = 10,
  category?: string,
  includeHidden = true,
  searchMode = "auto",
): Promise<SearchResponse> {
  const response = await api.post<SearchResponse>("/search", {
    query,
    sources,
    limit,
    category,
    include_hidden: includeHidden,
    search_mode: searchMode,
  });
  return response.data;
}

export async function getSearchStats(): Promise<SearchStatsResponse> {
  const response = await api.get<SearchStatsResponse>("/search/stats");
  return response.data;
}

export async function getEventDetail(eventId: string): Promise<MemoryEvent> {
  const response = await api.get<MemoryEvent>(`/search/event/${eventId}`);
  return response.data;
}

export async function getRelatedEvents(eventId: string, limit = 10): Promise<RelatedEventsResponse> {
  const response = await api.get<RelatedEventsResponse>(`/events/${eventId}/related`, {
    params: { limit },
  });
  return response.data;
}

export async function rebuildRelationships(): Promise<{ status: string; created: number; by_type: Record<string, number> }> {
  const response = await api.post<{ status: string; created: number; by_type: Record<string, number> }>("/dev/rebuild-relationships");
  return response.data;
}

export async function clearRelationships(): Promise<{ status: "cleared" }> {
  const response = await api.delete<{ status: "cleared" }>("/dev/clear-relationships");
  return response.data;
}

export async function applyMemoryPolicy(): Promise<{ status: string; updated: number; counts: Record<string, number> }> {
  const response = await api.post<{ status: string; updated: number; counts: Record<string, number> }>("/dev/apply-memory-policy");
  return response.data;
}

export async function cleanMemoryIndexes(): Promise<Record<string, unknown>> {
  const response = await api.post<Record<string, unknown>>("/dev/clean-memory-indexes", {}, { timeout: 130000 });
  return response.data;
}

export async function buildContext(payload: {
  query: string;
  mode?: "chat" | "task";
  limit?: number;
  related_per_event?: number;
}): Promise<ContextPackage> {
  const response = await api.post<ContextPackage>("/context/build", payload);
  return response.data;
}

export async function getEventContext(eventId: string, relatedLimit = 10): Promise<ContextPackage> {
  const response = await api.get<ContextPackage>(`/context/event/${eventId}`, {
    params: { related_limit: relatedLimit },
  });
  return response.data;
}

export async function sendChatMessage(payload: ChatRequestPayload): Promise<ChatResponse> {
  const response = await api.post<ChatResponse>("/chat", {
    ...payload,
    use_context: payload.use_context ?? true,
  }, {
    timeout: 130000,
  });
  return response.data;
}

export async function getModelSettings(): Promise<ModelSettingsResponse> {
  try {
    const response = await api.get<ModelSettingsResponse>("/models/settings", { timeout: 30000 });
    return response.data;
  } catch (error) {
    logApiError("GET /models/settings", error);
    throw error;
  }
}

export async function getChatModels(): Promise<ModelConfig[]> {
  const response = await api.get<ChatModelsResponse>("/models/chat", { timeout: 30000 });
  return response.data.models;
}

export async function getChatModelsResponse(): Promise<ChatModelsResponse> {
  try {
    const response = await api.get<ChatModelsResponse>("/models/chat", { timeout: 30000 });
    return response.data;
  } catch (error) {
    logApiError("GET /models/chat", error);
    throw error;
  }
}

export async function selectChatModel(modelId: string): Promise<{ status: string; selected_chat_model: string }> {
  const response = await api.post<{ status: string; selected_chat_model: string }>("/models/select", { model_id: modelId });
  return response.data;
}

export async function updateProviderConfig(payload: {
  provider: string;
  api_key?: string | null;
  base_url?: string | null;
  enabled?: boolean;
}): Promise<{ status: string; provider: string; configured: boolean; enabled: boolean; has_api_key: boolean }> {
  const response = await api.post<{ status: string; provider: string; configured: boolean; enabled: boolean; has_api_key: boolean }>(
    "/models/provider-config",
    payload,
  );
  return response.data;
}

export async function setModelEnabled(modelId: string, enabled: boolean): Promise<{ status: string; model_id: string; enabled: boolean }> {
  const response = await api.post<{ status: string; model_id: string; enabled: boolean }>(`/models/${modelId}/enabled`, {
    model_id: modelId,
    enabled,
  });
  return response.data;
}

export async function getProviderHealth(): Promise<Record<string, unknown>> {
  const response = await api.get<Record<string, unknown>>("/models/providers/health");
  return response.data;
}

export async function getEmbeddingStatus(): Promise<EmbeddingStatusResponse> {
  const response = await api.get<EmbeddingStatusResponse>("/embeddings/status", { timeout: 30000 });
  return response.data;
}

export async function getEmbeddingModels(): Promise<EmbeddingSettingsResponse> {
  const response = await api.get<EmbeddingSettingsResponse>("/models/embeddings", { timeout: 30000 });
  return response.data;
}

export async function selectEmbeddingModel(modelId: string): Promise<EmbeddingSettingsResponse> {
  const response = await api.post<EmbeddingSettingsResponse>("/models/embeddings/select", { model_id: modelId }, { timeout: 30000 });
  return response.data;
}

export async function reindexEmbeddings(): Promise<EmbeddingReindexResponse> {
  const response = await api.post<EmbeddingReindexResponse>("/embeddings/reindex", {}, { timeout: 130000 });
  return response.data;
}

export async function clearEmbeddingIndex(): Promise<{ status: string; updated_events: number }> {
  const response = await api.post<{ status: string; updated_events: number }>("/embeddings/clear", {}, { timeout: 30000 });
  return response.data;
}

export async function testLLM(message: string): Promise<TestLLMResponse> {
  const response = await api.post<TestLLMResponse>("/dev/test-llm", { message }, { timeout: 130000 });
  return response.data;
}

export async function getChatSessions(limit = 20): Promise<ChatSessionsResponse> {
  const response = await api.get<ChatSessionsResponse>("/chat/sessions", {
    params: { limit },
  });
  return response.data;
}

export async function getChatMessages(sessionId: string): Promise<ChatMessagesResponse> {
  const response = await api.get<ChatMessagesResponse>(`/chat/sessions/${sessionId}/messages`);
  return response.data;
}

export async function deleteChatSession(sessionId: string): Promise<{ status: "deleted" }> {
  const response = await api.delete<{ status: "deleted" }>(`/chat/sessions/${sessionId}`);
  return response.data;
}

export async function executeTask(instruction: string, dryRun = true, modelId?: string | null): Promise<TaskResponse> {
  try {
    const response = await api.post<TaskResponse>(
      "/tasks/execute",
      {
        instruction,
        dry_run: dryRun,
        model_id: modelId ?? null,
        use_context: true,
      },
      { timeout: 130000 },
    );
    return response.data;
  } catch (error) {
    logApiError("POST /tasks/execute", error);
    throw error;
  }
}

export async function planTask(payload: {
  instruction: string;
  task_type?: string | null;
  model_id?: string | null;
  use_context?: boolean;
}): Promise<TaskPlanningResponse> {
  try {
    const response = await api.post<TaskPlanningResponse>("/tasks/plan", payload, { timeout: 130000 });
    return response.data;
  } catch (error) {
    logApiError("POST /tasks/plan", error);
    throw error;
  }
}

export async function confirmTask(confirmationToken: string): Promise<TaskResponse> {
  const response = await api.post<TaskResponse>("/tasks/confirm", {
    confirmation_token: confirmationToken,
  });
  return response.data;
}

export async function cancelTask(taskId: string): Promise<TaskResponse> {
  const response = await api.post<TaskResponse>("/tasks/cancel", {
    task_id: taskId,
  });
  return response.data;
}

export async function getPendingTasks(): Promise<TaskHistoryResponse> {
  const response = await api.get<TaskHistoryResponse>("/tasks/pending");
  return response.data;
}

export async function getTaskHistory(limit = 20): Promise<TaskHistoryResponse> {
  const response = await api.get<TaskHistoryResponse>("/tasks/history", {
    params: { limit },
  });
  return response.data;
}

export async function getPlaybooks(): Promise<never> {
  throw new Error("Not implemented yet");
}

export async function getConnectors(): Promise<ConnectorListResponse> {
  const response = await api.get<ConnectorListResponse>("/connectors");
  return response.data;
}

export async function toggleConnector(id: string, enabled: boolean): Promise<ConnectorToggleResponse> {
  const response = await api.post<ConnectorToggleResponse>(`/connectors/${id}/toggle`, { enabled });
  return response.data;
}

export async function getConnectorConfig(id: string): Promise<ConnectorConfigResponse> {
  const response = await api.get<ConnectorConfigResponse>(`/connectors/${id}/config`);
  return response.data;
}

export async function updateConnectorConfig(id: string, config: Record<string, unknown>): Promise<ConnectorConfigResponse> {
  const response = await api.post<ConnectorConfigResponse>(`/connectors/${id}/config`, { config });
  return response.data;
}

export async function getCollectorClients(): Promise<CollectorClientsResponse> {
  const response = await api.get<CollectorClientsResponse>("/connectors/collectors");
  return response.data;
}

export async function getConnectorSources(connectorType?: string): Promise<ConnectorSourcesResponse> {
  const response = await api.get<ConnectorSourcesResponse>("/connectors/sources", {
    params: { connector_type: connectorType || undefined },
  });
  return response.data;
}

export async function createConnectorSource(payload: ConnectorSourceCreateRequest): Promise<ConnectorSource> {
  const response = await api.post<ConnectorSource>("/connectors/sources", payload);
  return response.data;
}

export async function updateConnectorSource(sourceId: string, payload: ConnectorSourceUpdateRequest): Promise<ConnectorSource> {
  const response = await api.put<ConnectorSource>(`/connectors/sources/${sourceId}`, payload);
  return response.data;
}

export async function deleteConnectorSource(sourceId: string): Promise<{ status: string }> {
  const response = await api.delete<{ status: string }>(`/connectors/sources/${sourceId}`);
  return response.data;
}

export async function runConnectorSourceImport(sourceId: string): Promise<RunConnectorSourceImportResponse> {
  const response = await api.post<RunConnectorSourceImportResponse>(`/connectors/sources/${sourceId}/import`, {}, { timeout: 130000 });
  return response.data;
}

export async function getImportRuns(params: { source_id?: string; connector_type?: string; limit?: number } = {}): Promise<ImportRunsResponse> {
  const response = await api.get<ImportRunsResponse>("/connectors/import-runs", { params });
  return response.data;
}

export async function clearConnectorSourceEvents(sourceId: string): Promise<{ status: string; deleted_events: number; deleted_relationships: number }> {
  const response = await api.delete<{ status: string; deleted_events: number; deleted_relationships: number }>(`/connectors/sources/${sourceId}/events`);
  return response.data;
}

export async function previewFileImport(payload: FileImportPayload): Promise<FilePreviewResult> {
  const response = await api.post<FilePreviewResult>("/connectors/file-system/preview", payload);
  return response.data;
}

export async function importFiles(payload: FileImportPayload): Promise<FileImportResult> {
  const response = await api.post<FileImportResult>("/connectors/file-system/import", payload);
  return response.data;
}

export async function previewLogImport(payload: Omit<LogImportPayload, "group_similar">): Promise<LogPreviewResult> {
  const response = await api.post<LogPreviewResult>("/connectors/logs/preview", payload);
  return response.data;
}

export async function importLogs(payload: LogImportPayload): Promise<LogImportResult> {
  const response = await api.post<LogImportResult>("/connectors/logs/import", payload);
  return response.data;
}

export async function clearLogEvents(): Promise<ClearLogEventsResponse> {
  const response = await api.delete<ClearLogEventsResponse>("/connectors/logs/events");
  return response.data;
}

export async function clearFileSystemEvents(): Promise<ClearFileSystemEventsResponse> {
  const response = await api.delete<ClearFileSystemEventsResponse>("/connectors/file-system/events");
  return response.data;
}

export async function clearGitEvents(): Promise<ClearGitEventsResponse> {
  const response = await api.delete<ClearGitEventsResponse>("/connectors/git/events");
  return response.data;
}

export async function previewGitImport(payload: Pick<GitImportPayload, "repo_path" | "max_commits">): Promise<GitPreviewResult> {
  const response = await api.post<GitPreviewResult>("/connectors/git/preview", payload);
  return response.data;
}

export async function importGitRepo(payload: GitImportPayload): Promise<GitImportResult> {
  const response = await api.post<GitImportResult>("/connectors/git/import", payload);
  return response.data;
}
