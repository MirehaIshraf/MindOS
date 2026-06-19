import axios from "axios";
import type { AxiosError } from "axios";

import type {
  BackendHealth,
  BackendStatus,
  BrowserDedupeResponse,
  ActiveChatRunResponse,
  ChatMessagesResponse,
  ChatModelsResponse,
  ChatRequestPayload,
  ChatRunCancelResponse,
  ChatRunCreatePayload,
  ChatRunStartResponse,
  ChatRunStatus,
  ChatResponse,
  ChatSessionsResponse,
  ContextPackage,
  ClearAllDevDataResponse,
  ClearEmailEventsResponse,
  ClearFileSystemEventsResponse,
  ClearLogEventsResponse,
  ClearGitEventsResponse,
  EmailCapabilityResponse,
  EmailConnectResponse,
  EmailDisconnectResponse,
  EmailDraftRequest,
  EmailDraftResponse,
  EmailMcpConfigRequest,
  EmailSearchRequest,
  EmailSearchResponse,
  EmailTestResponse,
  ConnectorConfigResponse,
  ConnectorListResponse,
  ConnectorSource,
  ConnectorSourceCreateRequest,
  ConnectorSourcesResponse,
  ConnectorSourceUpdateRequest,
  ConnectorToggleResponse,
  CollectorClientsResponse,
  DevState,
  DocumentSummaryPrepareRequest,
  DocumentSummaryPrepareResponse,
  DocumentSummaryCompleteRequest,
  DocumentSummaryCompleteResponse,
  EmailStatusResponse,
  EmailSyncRequest,
  EmailSyncResponse,
  EmbeddingReindexResponse,
  EmbeddingSettingsResponse,
  EmbeddingStatusResponse,
  FileImportPayload,
  FileImportResult,
  FilePreviewResult,
  FileTaskLlmPlanRequest,
  FileSnapshotResponse,
  FileTaskExecutionResult,
  FileTaskPlan,
  FileTaskRecentResponse,
  FileTaskUndoResult,
  GitImportPayload,
  GitImportResult,
  GitPreviewResult,
  GitHubConfigRequest,
  GitHubReposResponse,
  GitHubStatusResponse,
  GitHubSyncRequest,
  GitHubSyncResponse,
  GitHubTestResponse,
  GmailConnectResponse,
  GmailDraftPrepareRequest,
  GmailDraftPrepareResponse,
  GmailDraftRequest,
  GmailDraftResponse,
  GmailRecentEmailsResponse,
  GmailSendRequest,
  GmailSendResponse,
  GmailSendDraftResponse,
  GmailStatusResponse,
  GmailTestResponse,
  LogImportPayload,
  LogImportResult,
  LogPreviewResult,
  ImportRunsResponse,
  FileIndexJob,
  FileIndexJobsResponse,
  IndexedFileSearchRequest,
  IndexedFileSearchResponse,
  IndexedAttachmentReference,
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
  ResolveIndexedAttachmentsResponse,
  RunConnectorSourceImportResponse,
  TrackedFolder,
  TrackedFolderRequest,
  TrackedFoldersResponse,
  SearchResponse,
  SearchStatsResponse,
  SeedSampleEventsResponse,
  TaskHistoryResponse,
  ActionCapabilityRegistry,
  TaskActionExecuteRequest,
  TaskActionExecuteResponse,
  TaskPlanningResponse,
  TaskResponse,
  TestLLMResponse,
  McpServerConfigResponse,
  McpServerListResponse,
  McpServerStatus,
  McpServerToggleResponse,
  McpToolListResponse,
  McpToolCallResponse,
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
  offset = 0,
): Promise<RecentEventsResponse> {
  const response = await api.get<RecentEventsResponse>("/events/recent", {
    params: {
      source: source || undefined,
      limit,
      offset,
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

export async function summarizeEvent(eventId: string, method = "deterministic"): Promise<MemoryEvent> {
  const response = await api.post<MemoryEvent>(`/events/${eventId}/summarize`, { method }, { timeout: 30000 });
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

export async function dedupeBrowserPages(): Promise<BrowserDedupeResponse> {
  const response = await api.post<BrowserDedupeResponse>("/dev/dedupe-browser-pages", {}, { timeout: 130000 });
  return response.data;
}

export async function fixBrowserContentQuality(): Promise<{ updated: number }> {
  const response = await api.post<{ updated: number }>("/dev/fix-browser-content-quality", {}, { timeout: 130000 });
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

export async function startChatRun(payload: ChatRunCreatePayload): Promise<ChatRunStartResponse> {
  const response = await api.post<ChatRunStartResponse>("/chat/runs", {
    ...payload,
    use_memory: payload.use_memory ?? true,
  });
  return response.data;
}

export async function getChatRun(runId: string): Promise<ChatRunStatus> {
  const response = await api.get<ChatRunStatus>(`/chat/runs/${runId}`);
  return response.data;
}

export async function getActiveChatRun(sessionId: string): Promise<ActiveChatRunResponse> {
  const response = await api.get<ActiveChatRunResponse>(`/chat/sessions/${sessionId}/active-run`);
  return response.data;
}

export async function cancelChatRun(runId: string): Promise<ChatRunCancelResponse> {
  const response = await api.post<ChatRunCancelResponse>(`/chat/runs/${runId}/cancel`);
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

export async function getTaskActionCapabilities(): Promise<ActionCapabilityRegistry> {
  const response = await api.get<ActionCapabilityRegistry>("/tasks/actions/capabilities");
  return response.data;
}

export async function executeTaskAction(payload: TaskActionExecuteRequest): Promise<TaskActionExecuteResponse> {
  const response = await api.post<TaskActionExecuteResponse>("/tasks/actions/execute", payload, { timeout: 130000 });
  return response.data;
}

export async function scanFileTask(payload: { root_path: string; max_depth?: number; max_files?: number; include_hidden?: boolean }): Promise<FileSnapshotResponse> {
  const response = await api.post<FileSnapshotResponse>("/tasks/file/scan", payload, { timeout: 30000 });
  return response.data;
}

export async function prepareFileTask(payload: {
  root_path: string;
  instruction: string;
  max_depth?: number;
  max_files?: number;
  include_hidden?: boolean;
  mode?: string;
  dry_run?: boolean;
}): Promise<FileTaskPlan> {
  const response = await api.post<FileTaskPlan>("/tasks/file/prepare", payload, { timeout: 130000 });
  return response.data;
}

export const prepareFileTaskPlan = prepareFileTask;

export async function planFileTaskWithLlm(payload: FileTaskLlmPlanRequest): Promise<FileTaskPlan> {
  const response = await api.post<FileTaskPlan>("/tasks/file/plan-with-llm", payload, { timeout: 130000 });
  return response.data;
}

export async function prepareDocumentSummary(payload: DocumentSummaryPrepareRequest): Promise<DocumentSummaryPrepareResponse> {
  const response = await api.post<DocumentSummaryPrepareResponse>("/tasks/document/summary/prepare", payload, { timeout: 130000 });
  return response.data;
}

export async function completeDocumentSummary(payload: DocumentSummaryCompleteRequest): Promise<DocumentSummaryCompleteResponse> {
  const response = await api.post<DocumentSummaryCompleteResponse>("/tasks/document/summary/complete", payload);
  return response.data;
}

export async function executeFileTask(taskId: string): Promise<FileTaskExecutionResult> {
  const response = await api.post<FileTaskExecutionResult>(`/tasks/file/${taskId}/execute`, { confirmation: true }, { timeout: 130000 });
  return response.data;
}

export async function undoFileTask(taskId: string): Promise<FileTaskUndoResult> {
  const response = await api.post<FileTaskUndoResult>(`/tasks/file/${taskId}/undo`, {}, { timeout: 130000 });
  return response.data;
}

export async function getRecentFileTasks(limit = 20): Promise<FileTaskRecentResponse> {
  const response = await api.get<FileTaskRecentResponse>("/tasks/file/recent", { params: { limit } });
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

export async function indexConnectorSource(sourceId: string): Promise<RunConnectorSourceImportResponse> {
  const response = await api.post<RunConnectorSourceImportResponse>(`/connectors/sources/${sourceId}/index`, {}, { timeout: 130000 });
  return response.data;
}

export async function getTrackedFolders(): Promise<TrackedFoldersResponse> {
  const response = await api.get<TrackedFoldersResponse>("/connectors/file-system/tracked-folders");
  return response.data;
}

export async function addTrackedFolder(payload: TrackedFolderRequest): Promise<TrackedFolder> {
  const response = await api.post<TrackedFolder>("/connectors/file-system/tracked-folders", payload);
  return response.data;
}

export async function updateTrackedFolder(sourceId: string, payload: Partial<TrackedFolderRequest>): Promise<TrackedFolder> {
  const response = await api.put<TrackedFolder>(`/connectors/file-system/tracked-folders/${sourceId}`, payload);
  return response.data;
}

export async function deleteTrackedFolder(sourceId: string): Promise<{ status: string }> {
  const response = await api.delete<{ status: string }>(`/connectors/file-system/tracked-folders/${sourceId}`);
  return response.data;
}

export async function reindexTrackedFolder(sourceId: string): Promise<FileIndexJob> {
  const response = await api.post<FileIndexJob>(`/connectors/file-system/tracked-folders/${sourceId}/reindex`);
  return response.data;
}

export async function getFileIndexJobs(): Promise<FileIndexJobsResponse> {
  const response = await api.get<FileIndexJobsResponse>("/connectors/file-system/index-jobs");
  return response.data;
}

export async function searchIndexedFiles(payload: IndexedFileSearchRequest): Promise<IndexedFileSearchResponse> {
  const response = await api.post<IndexedFileSearchResponse>("/tasks/files/search", payload, { timeout: 30000 });
  return response.data;
}

export async function resolveIndexedAttachments(files: IndexedAttachmentReference[]): Promise<ResolveIndexedAttachmentsResponse> {
  const response = await api.post<ResolveIndexedAttachmentsResponse>("/tasks/files/resolve-attachments", { files }, { timeout: 30000 });
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

export async function clearGitHubEvents(): Promise<ClearGitEventsResponse> {
  const response = await api.delete<ClearGitEventsResponse>("/connectors/github/events");
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

export async function getGitHubStatus(): Promise<GitHubStatusResponse> {
  const response = await api.get<GitHubStatusResponse>("/connectors/github/status");
  return response.data;
}

export async function saveGitHubConfig(payload: GitHubConfigRequest): Promise<GitHubStatusResponse> {
  const response = await api.post<GitHubStatusResponse>("/connectors/github/config", {
    api_base_url: payload.api_base_url ?? "https://api.github.com",
    token: payload.token ?? null,
  });
  return response.data;
}

export async function testGitHubConnection(): Promise<GitHubTestResponse> {
  const response = await api.post<GitHubTestResponse>("/connectors/github/test", {});
  return response.data;
}

export async function listGitHubRepos(): Promise<GitHubReposResponse> {
  const response = await api.get<GitHubReposResponse>("/connectors/github/repos", { timeout: 30000 });
  return response.data;
}

export async function saveGitHubSelection(
  repoFullNames: string[],
  syncSettings?: { commits?: boolean; issues?: boolean; pull_requests?: boolean; max_items_per_type?: number },
): Promise<GitHubStatusResponse> {
  const response = await api.post<GitHubStatusResponse>("/connectors/github/selection", {
    repo_full_names: repoFullNames,
    sync_settings: syncSettings ?? {},
  });
  return response.data;
}

export async function syncGitHubRepos(payload: GitHubSyncRequest): Promise<GitHubSyncResponse> {
  const response = await api.post<GitHubSyncResponse>("/connectors/github/sync", payload, { timeout: 130000 });
  return response.data;
}

export async function getGmailStatus(): Promise<GmailStatusResponse> {
  const response = await api.get<GmailStatusResponse>("/connectors/gmail/status");
  return response.data;
}

export async function uploadGmailCredentials(file: File): Promise<GmailStatusResponse> {
  const response = await api.post<GmailStatusResponse>("/connectors/gmail/credentials/upload", {
    filename: file.name,
    content: await file.text(),
  });
  return response.data;
}

export async function connectGmail(): Promise<GmailConnectResponse> {
  const response = await api.post<GmailConnectResponse>("/connectors/gmail/connect", {});
  return response.data;
}

export async function testGmailConnection(): Promise<GmailTestResponse> {
  const response = await api.post<GmailTestResponse>("/connectors/gmail/test", {});
  return response.data;
}

export async function createGmailTestDraft(): Promise<GmailDraftResponse> {
  const response = await api.post<GmailDraftResponse>("/connectors/gmail/drafts/test", {});
  return response.data;
}

export async function createGmailDraft(payload: GmailDraftRequest | FormData): Promise<GmailDraftResponse> {
  const response = await api.post<GmailDraftResponse>("/connectors/gmail/drafts", payload);
  return response.data;
}

export async function createGmailDraftWithAttachments(payload: GmailDraftRequest & { attachments: File[]; indexed_attachments?: IndexedAttachmentReference[] }): Promise<GmailDraftResponse> {
  const response = await api.post<GmailDraftResponse>("/connectors/gmail/drafts", buildGmailMultipartFormData(payload, false));
  return response.data;
}

export async function getGmailRecentEmails(limit = 10): Promise<GmailRecentEmailsResponse> {
  const response = await api.get<GmailRecentEmailsResponse>("/connectors/gmail/recent", { params: { limit } });
  return response.data;
}

export async function sendGmailMessage(payload: GmailSendRequest | FormData): Promise<GmailSendResponse> {
  const response = await api.post<GmailSendResponse>("/connectors/gmail/send", payload);
  return response.data;
}

export async function sendGmailMessageWithAttachments(payload: GmailSendRequest & { attachments: File[]; indexed_attachments?: IndexedAttachmentReference[] }): Promise<GmailSendResponse> {
  const response = await api.post<GmailSendResponse>(
    "/connectors/gmail/send",
    buildGmailMultipartFormData(
      {
        ...payload,
        to: payload.to.join(","),
      },
      payload.confirmation,
    ),
  );
  return response.data;
}

function buildGmailMultipartFormData(
  payload: {
    to: string;
    cc?: string[];
    bcc?: string[];
    subject: string;
    body: string;
    attachments: File[];
    indexed_attachments?: IndexedAttachmentReference[];
  },
  confirmation: boolean,
) {
  const formData = new FormData();
  formData.append("to", payload.to);
  (payload.cc ?? []).forEach((recipient) => formData.append("cc", recipient));
  (payload.bcc ?? []).forEach((recipient) => formData.append("bcc", recipient));
  formData.append("subject", payload.subject);
  formData.append("body", payload.body);
  formData.append("confirmation", String(confirmation));
  if (payload.indexed_attachments?.length) {
    formData.append("indexed_attachments", JSON.stringify(payload.indexed_attachments));
  }
  payload.attachments.forEach((file) => formData.append("attachments", file, file.name));
  return formData;
}

export async function prepareGmailDraft(payload: GmailDraftPrepareRequest): Promise<GmailDraftPrepareResponse> {
  const response = await api.post<GmailDraftPrepareResponse>("/tasks/gmail/draft/prepare", payload, { timeout: 130000 });
  return response.data;
}

export async function sendGmailDraft(draftId: string): Promise<GmailSendDraftResponse> {
  const response = await api.post<GmailSendDraftResponse>(`/connectors/gmail/drafts/${encodeURIComponent(draftId)}/send`, {});
  return response.data;
}

export async function disconnectGmail(): Promise<GmailStatusResponse> {
  const response = await api.post<GmailStatusResponse>("/connectors/gmail/disconnect", {});
  return response.data;
}

export async function removeGmailCredentials(): Promise<GmailStatusResponse> {
  const response = await api.delete<GmailStatusResponse>("/connectors/gmail/credentials");
  return response.data;
}

export async function getEmailStatus(): Promise<EmailStatusResponse> {
  const response = await api.get<EmailStatusResponse>("/connectors/email/status");
  return response.data;
}

export async function saveEmailConfig(payload: EmailMcpConfigRequest): Promise<EmailStatusResponse> {
  const response = await api.post<EmailStatusResponse>("/connectors/email/config", payload);
  return response.data;
}

export async function testEmailConnection(): Promise<EmailTestResponse> {
  const response = await api.post<EmailTestResponse>("/connectors/email/test", {});
  return response.data;
}

export async function connectEmail(): Promise<EmailConnectResponse> {
  const response = await api.post<EmailConnectResponse>("/connectors/email/connect", {});
  return response.data;
}

export async function getEmailCapabilities(): Promise<EmailCapabilityResponse> {
  const response = await api.get<EmailCapabilityResponse>("/connectors/email/capabilities");
  return response.data;
}

export async function disconnectEmail(): Promise<EmailDisconnectResponse> {
  const response = await api.post<EmailDisconnectResponse>("/connectors/email/disconnect", {});
  return response.data;
}

export async function syncEmailMessages(payload: EmailSyncRequest): Promise<EmailSyncResponse> {
  const response = await api.post<EmailSyncResponse>("/connectors/email/sync", payload, { timeout: 130000 });
  return response.data;
}

export async function createEmailDraft(payload: EmailDraftRequest): Promise<EmailDraftResponse> {
  const response = await api.post<EmailDraftResponse>("/connectors/email/drafts", payload);
  return response.data;
}

export async function searchEmailMessages(payload: EmailSearchRequest): Promise<EmailSearchResponse> {
  const response = await api.post<EmailSearchResponse>("/connectors/email/search", payload, { timeout: 30000 });
  return response.data;
}

export async function clearEmailEvents(): Promise<ClearEmailEventsResponse> {
  const response = await api.delete<ClearEmailEventsResponse>("/connectors/email/events");
  return response.data;
}

// --- MCP Server API ---

export async function getMcpServers(): Promise<McpServerListResponse> {
  const response = await api.get<McpServerListResponse>("/mcp/servers");
  return response.data;
}

export async function getMcpServer(serverId: string): Promise<McpServerStatus> {
  const response = await api.get<McpServerStatus>(`/mcp/servers/${serverId}`);
  return response.data;
}

export async function toggleMcpServer(serverId: string, enabled: boolean): Promise<McpServerToggleResponse> {
  const response = await api.post<McpServerToggleResponse>(`/mcp/servers/${serverId}/toggle`, { enabled });
  return response.data;
}

export async function getMcpServerConfig(serverId: string): Promise<McpServerConfigResponse> {
  const response = await api.get<McpServerConfigResponse>(`/mcp/servers/${serverId}/config`);
  return response.data;
}

export async function updateMcpServerConfig(serverId: string, config: Record<string, unknown>): Promise<McpServerConfigResponse> {
  const response = await api.post<McpServerConfigResponse>(`/mcp/servers/${serverId}/config`, { config });
  return response.data;
}

export async function getMcpServerTools(serverId: string): Promise<McpToolListResponse> {
  const response = await api.get<McpToolListResponse>(`/mcp/servers/${serverId}/tools`);
  return response.data;
}

export async function getMcpAvailableTools(): Promise<McpToolListResponse> {
  const response = await api.get<McpToolListResponse>("/mcp/tools");
  return response.data;
}

export async function callMcpTool(toolName: string, args: Record<string, unknown>, confirmed = false): Promise<McpToolCallResponse> {
  const response = await api.post<McpToolCallResponse>("/mcp/tools/call", { tool_name: toolName, arguments: args, confirmed });
  return response.data;
}
