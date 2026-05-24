import axios from "axios";

import type {
  BackendHealth,
  ChatMessagesResponse,
  ChatRequestPayload,
  ChatResponse,
  ChatSessionsResponse,
  ConnectorListResponse,
  DevState,
  FileImportPayload,
  FileImportResult,
  FilePreviewResult,
  IngestEventRequest,
  IngestEventResponse,
  MemoryEvent,
  RecentEventsResponse,
  SearchResponse,
  SearchStatsResponse,
  SeedSampleEventsResponse,
  TaskHistoryResponse,
  TaskResponse,
} from "../types";

export const api = axios.create({
  baseURL: "http://localhost:8000",
  timeout: 5000,
});

export async function getHealth(): Promise<BackendHealth> {
  const response = await api.get<BackendHealth>("/health");
  return response.data;
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

export async function getDevState(): Promise<DevState> {
  const response = await api.get<DevState>("/dev/state");
  return response.data;
}

export async function ingestEvent(data: IngestEventRequest): Promise<IngestEventResponse> {
  const response = await api.post<IngestEventResponse>("/ingest", data);
  return response.data;
}

export async function searchEvents(
  query: string,
  sources?: string[],
  limit = 10,
  category?: string,
  includeHidden = true,
): Promise<SearchResponse> {
  const response = await api.post<SearchResponse>("/search", {
    query,
    sources,
    limit,
    category,
    include_hidden: includeHidden,
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

export async function sendChatMessage(payload: ChatRequestPayload): Promise<ChatResponse> {
  const response = await api.post<ChatResponse>("/chat", {
    ...payload,
    use_context: payload.use_context ?? true,
  });
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

export async function executeTask(instruction: string, dryRun = true): Promise<TaskResponse> {
  const response = await api.post<TaskResponse>("/tasks/execute", {
    instruction,
    dry_run: dryRun,
  });
  return response.data;
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

export async function previewFileImport(payload: FileImportPayload): Promise<FilePreviewResult> {
  const response = await api.post<FilePreviewResult>("/connectors/file-system/preview", payload);
  return response.data;
}

export async function importFiles(payload: FileImportPayload): Promise<FileImportResult> {
  const response = await api.post<FileImportResult>("/connectors/file-system/import", payload);
  return response.data;
}
