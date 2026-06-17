import { Activity, DatabaseZap, HeartPulse, RefreshCw, Send, Trash2 } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  applyMemoryPolicy,
  buildContext,
  cleanMemoryIndexes,
  clearAllDevData,
  clearChats,
  clearEmbeddingIndex,
  clearEvents,
  clearRelationships,
  clearTasks,
  dedupeBrowserPages,
  fixBrowserContentQuality,
  getErrorMessage,
  getDevState,
  getEmbeddingStatus,
  getIngestStatus,
  getModelSettings,
  getRecentEvents,
  getStatus,
  ingestExternalEvent,
  ingestEvent,
  planTask,
  rebuildRelationships,
  reindexEmbeddings,
  seedSampleEvents,
  testLLM,
} from "../services/api";
import { clearRecentTaskHistoryStorage } from "../services/taskHistoryStorage";
import type {
  BackendHealth,
  BackendStatus,
  ClearAllDevDataResponse,
  ContextPackage,
  DevState,
  EmbeddingReindexResponse,
  EmbeddingStatusResponse,
  ExternalIngestResponse,
  ExternalIngestStatusResponse,
  EventSource,
  MemoryEvent,
  ModelSettingsResponse,
  TaskPlanningResponse,
  TestLLMResponse,
} from "../types";
import { Badge } from "../components/shared/Badge";
import { Button } from "../components/shared/Button";
import { Card } from "../components/shared/Card";
import { EmptyState } from "../components/shared/EmptyState";
import { Input } from "../components/shared/Input";

const eventSources: EventSource[] = ["manual", "file_system", "vscode", "browser", "git", "github", "jira", "logs", "email"];

const emptyForm = {
  source: "manual" as EventSource,
  type: "note",
  title: "",
  content: "",
  metadata: "",
};

type IngestForm = typeof emptyForm;

const emptyExternalForm = {
  source: "vscode_extension",
  type: "editor_file_saved",
  title: "Saved auth_middleware.py",
  content: "Edited JWT refresh flow",
  metadata: '{\n  "file_path": "C:\\\\project\\\\auth_middleware.py",\n  "language": "python"\n}',
};

type ExternalIngestForm = typeof emptyExternalForm;

export function DevPage() {
  const [health, setHealth] = useState<BackendHealth | null>(null);
  const [status, setStatus] = useState<BackendStatus | null>(null);
  const [devState, setDevState] = useState<DevState | null>(null);
  const [modelSettings, setModelSettings] = useState<ModelSettingsResponse | null>(null);
  const [events, setEvents] = useState<MemoryEvent[]>([]);
  const [form, setForm] = useState<IngestForm>(emptyForm);
  const [contextQuery, setContextQuery] = useState("jwt login failure");
  const [contextResult, setContextResult] = useState<ContextPackage | null>(null);
  const [llmTestMessage, setLlmTestMessage] = useState("Say hello from MindOS");
  const [llmTestResult, setLlmTestResult] = useState<TestLLMResponse | null>(null);
  const [plannerInstruction, setPlannerInstruction] = useState("Create a Jira ticket for the login bug");
  const [plannerResult, setPlannerResult] = useState<TaskPlanningResponse | null>(null);
  const [embeddingStatus, setEmbeddingStatus] = useState<EmbeddingStatusResponse | null>(null);
  const [embeddingResult, setEmbeddingResult] = useState<EmbeddingReindexResponse | null>(null);
  const [ingestStatus, setIngestStatus] = useState<ExternalIngestStatusResponse | null>(null);
  const [externalForm, setExternalForm] = useState<ExternalIngestForm>(emptyExternalForm);
  const [externalResult, setExternalResult] = useState<ExternalIngestResponse | null>(null);
  const [clearAllResult, setClearAllResult] = useState<ClearAllDevDataResponse | null>(null);
  const [clearSavedSources, setClearSavedSources] = useState(false);
  const [clearModelSettings, setClearModelSettings] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [optionalWarnings, setOptionalWarnings] = useState<Record<string, string>>({});
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const refreshSeq = useRef(0);

  const backendOnline = status !== null;

  useEffect(() => {
    void refreshAll();
  }, []);

  async function refreshAll() {
    const requestId = refreshSeq.current + 1;
    refreshSeq.current = requestId;
    setLoadingAction("refresh");
    setError(null);
    try {
      const statusResponse = await getStatus();
      console.info("GET /status success", statusResponse.status_request_id ?? "");
      if (refreshSeq.current !== requestId) {
        return;
      }
      setStatus(statusResponse);
      setOptionalWarnings({});
      void loadOptionalDevState(requestId);
    } catch (caughtError) {
      console.error("GET /status failed", caughtError);
      if (refreshSeq.current !== requestId) {
        return;
      }
      setHealth(null);
      setStatus(null);
      setError(getErrorMessage(caughtError));
    } finally {
      if (refreshSeq.current === requestId) {
        setLoadingAction(null);
      }
    }
  }

  async function loadOptionalDevState(requestId: number) {
    const warnings: Record<string, string> = {};
    const applyWarning = (key: string, value: string) => {
      warnings[key] = value;
      if (refreshSeq.current === requestId) {
        setOptionalWarnings((current) => ({ ...current, [key]: value }));
      }
    };

    try {
      const stateResponse = await getDevState();
      console.info("GET /dev/state success");
      if (refreshSeq.current === requestId) {
        setDevState(stateResponse);
      }
    } catch (caughtError) {
      console.warn("GET /dev/state failed", caughtError);
      applyWarning("devState", "Dev state unavailable.");
    }

    try {
      const eventsResponse = await getRecentEvents(undefined, 20, undefined, true);
      console.info("GET /events/recent success");
      if (refreshSeq.current === requestId) {
        setEvents(eventsResponse.events);
      }
    } catch (caughtError) {
      console.warn("GET /events/recent failed", caughtError);
      applyWarning("events", "Recent events unavailable.");
    }

    try {
      const embeddingResponse = await getEmbeddingStatus();
      console.info("GET /embeddings/status success");
      if (refreshSeq.current === requestId) {
        setEmbeddingStatus(embeddingResponse);
      }
    } catch (caughtError) {
      console.warn("GET /embeddings/status failed", caughtError);
      applyWarning("embeddings", "Embedding status unavailable.");
    }

    try {
      const modelSettingsResponse = await getModelSettings();
      console.info("GET /models/settings success");
      if (refreshSeq.current === requestId) {
        setModelSettings(modelSettingsResponse);
      }
    } catch (caughtError) {
      console.warn("GET /models/settings failed", caughtError);
      applyWarning("models", "Model settings unavailable.");
    }

    try {
      const ingestResponse = await getIngestStatus();
      console.info("GET /ingest/status success");
      if (refreshSeq.current === requestId) {
        setIngestStatus(ingestResponse);
      }
    } catch (caughtError) {
      console.warn("GET /ingest/status failed", caughtError);
      applyWarning("ingest", "External ingest status unavailable.");
    }
  }

  async function handleSeed() {
    setLoadingAction("seed");
    setError(null);
    setMessage(null);
    try {
      const response = await seedSampleEvents();
      setMessage(`Seeded ${response.count} sample events.`);
      await refreshAll();
    } catch {
      setError("Could not seed sample events.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleClear() {
    if (!window.confirm("Clear all in-memory events?")) {
      return;
    }

    setLoadingAction("clear");
    setError(null);
    setMessage(null);
    try {
      await clearEvents();
      setMessage("Cleared local memory events.");
      await refreshAll();
    } catch {
      setError("Could not clear events.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleClearTasks() {
    if (!window.confirm("Clear all in-memory task history?")) {
      return;
    }

    setLoadingAction("clearTasks");
    setError(null);
    setMessage(null);
    try {
      const response = await clearTasks();
      clearRecentTaskHistoryStorage();
      setMessage(`Cleared local task history${typeof response.deleted_count === "number" ? ` (${response.deleted_count} backend items)` : ""}.`);
      await refreshAll();
    } catch {
      setError("Could not clear tasks.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleClearChats() {
    if (!window.confirm("Clear all in-memory chat sessions and messages?")) {
      return;
    }

    setLoadingAction("clearChats");
    setError(null);
    setMessage(null);
    try {
      await clearChats();
      setMessage("Cleared local chat history.");
      await refreshAll();
    } catch {
      setError("Could not clear chats.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleRebuildRelationships() {
    setLoadingAction("rebuildRelationships");
    setError(null);
    setMessage(null);
    try {
      const response = await rebuildRelationships();
      setMessage(`Rebuilt ${response.created} relationships.`);
      await refreshAll();
    } catch {
      setError("Could not rebuild relationships.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleClearRelationships() {
    if (!window.confirm("Clear all detected memory relationships?")) {
      return;
    }
    setLoadingAction("clearRelationships");
    setError(null);
    setMessage(null);
    try {
      await clearRelationships();
      setMessage("Cleared memory relationships.");
      await refreshAll();
    } catch {
      setError("Could not clear relationships.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleApplyMemoryPolicy() {
    setLoadingAction("applyMemoryPolicy");
    setError(null);
    setMessage(null);
    try {
      const response = await applyMemoryPolicy();
      setMessage(`Applied memory policy to ${response.updated} events.`);
      await refreshAll();
    } catch (caughtError) {
      setError(getErrorMessage(caughtError));
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleCleanMemoryIndexes() {
    if (!window.confirm("Apply memory policy, rebuild eligible relationships, and reindex eligible memories?")) {
      return;
    }
    setLoadingAction("cleanMemoryIndexes");
    setError(null);
    setMessage(null);
    try {
      const response = await cleanMemoryIndexes();
      setMessage(`Cleaned memory indexes. Policy updated: ${String(response.policy_updated ?? 0)}.`);
      await refreshAll();
    } catch (caughtError) {
      setError(getErrorMessage(caughtError));
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleDedupeBrowserPages() {
    setLoadingAction("dedupeBrowserPages");
    setError(null);
    setMessage(null);
    try {
      const response = await dedupeBrowserPages();
      setMessage(
        `Deduplicated browser pages. Groups: ${response.groups_found}, deleted: ${response.events_deleted}, updated: ${response.events_updated}.`,
      );
      await refreshAll();
    } catch (caughtError) {
      setError(getErrorMessage(caughtError));
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleFixBrowserContentQuality() {
    setLoadingAction("fixBrowserContentQuality");
    setError(null);
    setMessage(null);
    try {
      const response = await fixBrowserContentQuality();
      setMessage(`Fixed browser content quality metadata for ${response.updated} events.`);
      await refreshAll();
    } catch (caughtError) {
      setError(getErrorMessage(caughtError));
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleBuildContext() {
    if (!contextQuery.trim()) {
      setError("Context query is required.");
      return;
    }
    setLoadingAction("buildContext");
    setError(null);
    setMessage(null);
    try {
      setContextResult(
        await buildContext({
          query: contextQuery,
          mode: "chat",
          limit: 5,
          related_per_event: 2,
        }),
      );
    } catch {
      setError("Could not build context.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleTestLLM() {
    if (!llmTestMessage.trim()) {
      setError("LLM test message is required.");
      return;
    }
    setLoadingAction("testLLM");
    setError(null);
    setMessage(null);
    setLlmTestResult(null);
    try {
      setLlmTestResult(await testLLM(llmTestMessage));
      const statusResponse = await getStatus();
      setStatus(statusResponse);
    } catch {
      setError("Could not test the active LLM.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function handlePlanTask() {
    if (!plannerInstruction.trim()) {
      setError("Task planner instruction is required.");
      return;
    }
    setLoadingAction("planTask");
    setError(null);
    setMessage(null);
    setPlannerResult(null);
    try {
      setPlannerResult(await planTask({ instruction: plannerInstruction, use_context: true }));
    } catch {
      setError("Could not plan task.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleReindexEmbeddings() {
    setLoadingAction("reindexEmbeddings");
    setError(null);
    setMessage(null);
    setEmbeddingResult(null);
    try {
      const response = await reindexEmbeddings();
      setEmbeddingResult(response);
      setMessage(`Reindexed ${response.indexed} events. Failed: ${response.failed}.`);
      setEmbeddingStatus(await getEmbeddingStatus());
    } catch (caughtError) {
      setError(getErrorMessage(caughtError));
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleClearEmbeddingIndex() {
    if (!window.confirm("Clear the local vector index? SQLite memory events will remain.")) {
      return;
    }
    setLoadingAction("clearEmbeddings");
    setError(null);
    setMessage(null);
    try {
      const response = await clearEmbeddingIndex();
      setMessage(`Cleared vector index. Updated ${response.updated_events} event statuses.`);
      setEmbeddingStatus(await getEmbeddingStatus());
    } catch (caughtError) {
      setError(getErrorMessage(caughtError));
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleClearAll() {
    const confirmed = window.confirm(
      "This will clear events, chats, tasks, relationships, vector index, and import history. Saved sources and model settings will be kept unless selected. Continue?",
    );
    if (!confirmed) {
      return;
    }
    setLoadingAction("clearAll");
    setError(null);
    setMessage(null);
    setClearAllResult(null);
    try {
      const response = await clearAllDevData({
        clear_saved_sources: clearSavedSources,
        clear_model_settings: clearModelSettings,
      });
      clearRecentTaskHistoryStorage();
      setClearAllResult(response);
      setMessage(
        `Cleared ${response.events_deleted} events, ${response.tasks_deleted} tasks, ${response.chats_deleted} chat sessions, and ${response.relationships_deleted} relationships.`,
      );
      await refreshAll();
    } catch (caughtError) {
      setError(getErrorMessage(caughtError));
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleManualIngest() {
    const title = form.title.trim();
    const type = form.type.trim();
    if (!title || !type) {
      setError("Type and title are required.");
      return;
    }

    setLoadingAction("ingest");
    setError(null);
    setMessage(null);
    try {
      await ingestEvent({
        source: form.source,
        type,
        title,
        content: form.content,
        metadata: parseMetadata(form.metadata),
      });
      setMessage("Manual event ingested.");
      setForm(emptyForm);
      await refreshAll();
    } catch (caughtError) {
      setError(caughtError instanceof SyntaxError ? caughtError.message : "Could not ingest event.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleExternalIngest() {
    const title = externalForm.title.trim();
    const type = externalForm.type.trim();
    if (!type) {
      setError("External event type is required.");
      return;
    }

    setLoadingAction("externalIngest");
    setError(null);
    setMessage(null);
    setExternalResult(null);
    try {
      const response = await ingestExternalEvent({
        source: externalForm.source,
        type,
        title,
        content: externalForm.content,
        metadata: parseMetadata(externalForm.metadata),
        client_id: `${externalForm.source}-dev`,
      });
      setExternalResult(response);
      setMessage(`External event ingested: ${response.event_id}`);
      await refreshAll();
    } catch (caughtError) {
      setError(caughtError instanceof SyntaxError ? caughtError.message : getErrorMessage(caughtError));
    } finally {
      setLoadingAction(null);
    }
  }

  const sourceCounts = useMemo(() => {
    if (!devState) {
      return [];
    }
    return Object.entries(devState.events_by_source);
  }, [devState]);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-app-text">Developer Mode</h1>
        <p className="mt-2 text-sm text-app-muted">
          Internal tools for testing ingestion, memory, search, tasks, storage, and local services.
        </p>
      </header>

      {error ? <StatusMessage variant="danger" message={error} /> : null}
      {message ? <StatusMessage variant="success" message={message} /> : null}
      {Object.values(optionalWarnings).length > 0 ? (
        <div className="rounded-md border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
          {Object.values(optionalWarnings).join(" ")}
        </div>
      ) : null}

      <div className="grid grid-cols-3 gap-4">
        <Card>
          <SectionHeader icon={<HeartPulse size={18} />} title="Backend Health" />
          <div className="mt-4 space-y-3 text-sm">
            <Row label="status" value={backendOnline ? "online" : "offline"} tone={backendOnline ? "success" : "danger"} />
            <Row label="storage" value={status?.storage ?? devState?.storage ?? health?.storage ?? "-"} />
            <Row label="database" value={status?.database_path ?? devState?.database_path ?? health?.database_path ?? "-"} />
            <Row label="event count" value={String(status?.event_count ?? devState?.event_count ?? health?.event_count ?? 0)} />
            <Row label="file events" value={String(devState?.file_system_event_count ?? 0)} />
            <Row label="log events" value={String(devState?.logs_event_count ?? 0)} />
            <Row label="git events" value={String(devState?.git_event_count ?? 0)} />
            <Row label="saved sources" value={String(devState?.saved_sources_count ?? 0)} />
            <Row label="import runs" value={String(devState?.import_runs_count ?? 0)} />
            <Row label="task count" value={String(status?.task_count ?? devState?.task_count ?? health?.task_count ?? 0)} />
            <Row label="chat sessions" value={String(status?.chat_session_count ?? devState?.chat_session_count ?? health?.chat_session_count ?? 0)} />
            <Row label="chat messages" value={String(status?.chat_message_count ?? devState?.chat_message_count ?? health?.chat_message_count ?? 0)} />
            <Row label="relationships" value={String(status?.relationship_count ?? devState?.relationship_count ?? 0)} />
          </div>
          {devState?.storage === "sqlite" || health?.storage === "sqlite" ? (
            <p className="mt-4 text-xs leading-5 text-app-muted">SQLite data persists across backend restarts.</p>
          ) : null}
          {sourceCounts.length > 0 ? (
            <div className="mt-4 flex flex-wrap gap-2">
              {sourceCounts.map(([source, count]) => (
                <Badge key={source} variant="default">
                  {source}: {count}
                </Badge>
              ))}
            </div>
          ) : null}
        </Card>

        <Card>
          <SectionHeader icon={<HeartPulse size={18} />} title="Model Runtime" />
          <div className="mt-4 space-y-3 text-sm">
            <Row label="local LLM" value={String(status?.local_llm_enabled ?? devState?.local_llm_enabled ?? false)} />
            <Row
              label="Ollama"
              value={(status?.ollama_available ?? devState?.ollama_available) ? "available" : "unavailable"}
              tone={(status?.ollama_available ?? devState?.ollama_available) ? "success" : "danger"}
            />
            <Row label="chat model" value={status?.chat_model ?? devState?.chat_model ?? "qwen3:8b"} />
            <Row label="selected model" value={status?.selected_chat_model ?? "-"} />
            <Row label="active LLM" value={status?.active_llm ?? devState?.active_llm ?? "fake-llm"} />
            <Row label="active provider" value={status?.active_provider ?? "-"} />
            <Row label="enabled models" value={String(status?.available_chat_models_count ?? status?.available_chat_models?.length ?? 0)} />
            <Row label="settings models" value={String(modelSettings?.models.length ?? "-")} />
            <Row label="installed Ollama" value={String(status?.discovered_ollama_models?.length ?? devState?.ollama_models?.length ?? 0)} />
            <Row label="local chat models" value={String(status?.local_chat_models_count ?? 0)} />
            <Row label="filtered embeddings" value={String(status?.embedding_models_filtered_count ?? 0)} />
            <Row label="num ctx" value={String(status?.ollama_num_ctx ?? devState?.ollama_num_ctx ?? "-")} />
            <Row label="direct limit" value={String(status?.chat_context_direct_limit ?? devState?.chat_context_direct_limit ?? "-")} />
            <Row label="related each" value={String(status?.chat_context_related_per_event ?? devState?.chat_context_related_per_event ?? "-")} />
            <Row label="max context chars" value={String(status?.chat_context_max_total_chars ?? devState?.chat_context_max_total_chars ?? "-")} />
            <Row label="history limit" value={String(status?.chat_history_limit ?? devState?.chat_history_limit ?? "-")} />
          </div>
          {!(status?.ollama_available ?? devState?.ollama_available) ? (
            <p className="mt-4 text-xs leading-5 text-amber-200">
              Ollama unavailable. Start Ollama manually to use local models.
            </p>
          ) : null}
          {status?.available_chat_models && status.available_chat_models.length > 0 ? (
            <div className="mt-4 flex flex-wrap gap-2">
              {status.available_chat_models.map((model) => (
                <Badge key={model.id} variant={model.type === "cloud" ? "warning" : "success"}>
                  {model.display_name}
                </Badge>
              ))}
            </div>
          ) : null}
          {status?.discovered_ollama_models?.length ? (
            <div className="mt-4 flex flex-wrap gap-2">
              {status.discovered_ollama_models.map((model) => (
                <Badge key={model}>{model}</Badge>
              ))}
            </div>
          ) : null}
          {status?.providers ? (
            <div className="mt-4 space-y-2 text-sm">
              {Object.entries(status.providers).map(([provider, details]) => (
                <Row
                  key={provider}
                  label={provider}
                  value={details.available === true ? "available" : details.configured ? "configured" : "not configured"}
                  tone={details.available === true || details.configured ? "success" : "danger"}
                />
              ))}
            </div>
          ) : null}
          {status ? (
            <details className="mt-4 rounded-md border border-app-border bg-zinc-950 p-3">
              <summary className="cursor-pointer text-xs text-app-muted">Raw Status JSON</summary>
              <pre className="mt-3 max-h-72 overflow-auto text-xs leading-5 text-app-text">{JSON.stringify(status, null, 2)}</pre>
            </details>
          ) : null}
          <div className="mt-4 space-y-3">
            <Button variant="secondary" onClick={refreshAll} loading={loadingAction === "refresh"}>
              Refresh Status
            </Button>
            <LabeledInput label="Test message" value={llmTestMessage} onChange={setLlmTestMessage} />
            <Button variant="primary" onClick={handleTestLLM} loading={loadingAction === "testLLM"}>
              Test LLM
            </Button>
            {llmTestResult ? (
              <div className="rounded-md border border-app-border bg-zinc-950 p-3 text-sm">
                <div className="mb-2 flex flex-wrap gap-2">
                  <Badge variant="info">{llmTestResult.model}</Badge>
                  {llmTestResult.warning ? <Badge variant="warning">fallback</Badge> : null}
                </div>
                {llmTestResult.warning ? <p className="mb-2 text-xs text-amber-200">{llmTestResult.warning}</p> : null}
                <p className="whitespace-pre-wrap text-app-muted">{llmTestResult.reply}</p>
              </div>
            ) : null}
          </div>
        </Card>

        <Card>
          <SectionHeader icon={<DatabaseZap size={18} />} title="Seed Sample Data" />
          <p className="mt-3 text-sm text-app-muted">Create realistic developer events in memory.</p>
          <Button className="mt-5" variant="primary" onClick={handleSeed} loading={loadingAction === "seed"}>
            Seed sample events
          </Button>
        </Card>

        <Card>
          <SectionHeader icon={<Activity size={18} />} title="Experimental Modules" />
          <div className="mt-4 space-y-3 text-sm">
            <Row label="Tasks" value={status?.tasks_status ?? "experimental_paused"} tone="danger" />
            <p className="text-app-muted">Task execution is paused while MindOS focuses on connectors, collectors, and clean memory ingestion.</p>
            <Button variant="secondary" onClick={() => window.location.assign("/tasks")}>
              Open Tasks
            </Button>
          </div>
        </Card>

        <Card>
          <SectionHeader icon={<Send size={18} />} title="External Ingestion" />
          <div className="mt-4 space-y-3 text-sm">
            <Row label="POST" value="/ingest/external" />
            <Row label="POST" value="/ingest/external/bulk" />
            <Row label="enabled" value={String(ingestStatus?.external_ingest_enabled ?? true)} />
            <Row label="recent events" value={String(ingestStatus?.recent_external_events ?? 0)} />
            <Row label="collectors" value={String(ingestStatus?.collector_clients.length ?? 0)} />
            <Row
              label="VSCode events"
              value={String(
                ingestStatus?.collector_clients
                  .filter((collector) => collector.type === "vscode_extension")
                  .reduce((total, collector) => total + collector.events_count, 0) ?? 0,
              )}
            />
          </div>
          {ingestStatus?.supported_sources.length ? (
            <div className="mt-4 flex flex-wrap gap-2">
              {ingestStatus.supported_sources.map((source) => (
                <Badge key={source} variant="info">{source}</Badge>
              ))}
            </div>
          ) : null}
          {ingestStatus?.collector_clients.length ? (
            <div className="mt-4 space-y-2">
              {ingestStatus.collector_clients.slice(0, 4).map((collector) => (
                <div key={`${collector.type}-${collector.id}`} className="rounded-md border border-app-border bg-zinc-950 px-3 py-2">
                  <div className="flex items-center gap-2">
                    <Badge>{collector.type}</Badge>
                    <span className="text-sm text-app-text">{collector.name}</span>
                    <span className="ml-auto text-xs text-app-muted">{collector.events_count} events</span>
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </Card>

        <Card>
          <SectionHeader icon={<Trash2 size={18} />} title="Danger Zone" />
          <p className="mt-3 text-sm text-app-muted">
            Clear local development data. Saved sources and model settings are kept unless you explicitly include them.
          </p>
          <div className="mt-5 flex flex-wrap gap-3">
            <Button variant="danger" onClick={handleClear} loading={loadingAction === "clear"}>
              Clear events
            </Button>
            <Button variant="secondary" onClick={handleClearTasks} loading={loadingAction === "clearTasks"}>
              Clear tasks
            </Button>
            <Button variant="secondary" onClick={handleClearChats} loading={loadingAction === "clearChats"}>
              Clear chats
            </Button>
            <Button variant="secondary" onClick={handleClearRelationships} loading={loadingAction === "clearRelationships"}>
              Clear relationships
            </Button>
          </div>
          <div className="mt-5 space-y-3 rounded-md border border-red-500/30 bg-red-500/5 p-3">
            <label className="flex items-center gap-3 text-sm text-app-text">
              <input
                type="checkbox"
                checked={clearSavedSources}
                onChange={(event) => setClearSavedSources(event.target.checked)}
                className="h-4 w-4 accent-red-600"
              />
              Also clear saved connector sources
            </label>
            <label className="flex items-center gap-3 text-sm text-app-text">
              <input
                type="checkbox"
                checked={clearModelSettings}
                onChange={(event) => setClearModelSettings(event.target.checked)}
                className="h-4 w-4 accent-red-600"
              />
              Also clear model settings/API key config
            </label>
            <Button variant="danger" onClick={handleClearAll} loading={loadingAction === "clearAll"}>
              Clear All Local Data
            </Button>
          </div>
          {clearAllResult ? (
            <div className="mt-4 flex flex-wrap gap-2">
              <Badge variant="danger">events: {clearAllResult.events_deleted}</Badge>
              <Badge>tasks: {clearAllResult.tasks_deleted}</Badge>
              <Badge>chats: {clearAllResult.chats_deleted}</Badge>
              <Badge>relationships: {clearAllResult.relationships_deleted}</Badge>
              <Badge>import runs: {clearAllResult.import_runs_deleted}</Badge>
              <Badge>vectors: {clearAllResult.vectors_deleted ?? "n/a"}</Badge>
              {clearAllResult.saved_sources_deleted ? <Badge variant="warning">saved sources: {clearAllResult.saved_sources_deleted}</Badge> : null}
              {clearAllResult.model_settings_cleared ? <Badge variant="warning">model settings cleared</Badge> : null}
            </div>
          ) : null}
          {clearAllResult?.warnings?.length ? (
            <p className="mt-3 text-xs leading-5 text-amber-200">{clearAllResult.warnings.join("; ")}</p>
          ) : null}
        </Card>

        <Card>
          <SectionHeader icon={<Activity size={18} />} title="Relationship Debug" />
          <div className="mt-4 flex flex-wrap gap-2">
            {Object.entries(devState?.relationships_by_type ?? {}).map(([type, count]) => (
              <Badge key={type} variant="default">
                {type}: {count}
              </Badge>
            ))}
          </div>
          <div className="mt-5 flex flex-wrap gap-3">
            <Button variant="primary" onClick={handleRebuildRelationships} loading={loadingAction === "rebuildRelationships"}>
              Rebuild Relationships
            </Button>
            <Button variant="secondary" onClick={handleClearRelationships} loading={loadingAction === "clearRelationships"}>
              Clear Relationships
            </Button>
          </div>
        </Card>

        <Card>
          <SectionHeader icon={<DatabaseZap size={18} />} title="Memory Policy Debug" />
          <p className="mt-3 text-sm text-app-muted">
            Raw chat messages are stored, but should not be embedded, related, or used as normal chat context.
          </p>
          <div className="mt-4 space-y-3 text-sm">
            {Object.entries(devState?.memory_policy ?? {}).map(([key, value]) => (
              <Row key={key} label={key.replace(/_/g, " ")} value={String(value)} />
            ))}
          </div>
          <p className="mt-4 text-xs leading-5 text-amber-200">
            If old chat messages were indexed or related, run Clean Memory Indexes.
          </p>
          <div className="mt-5 flex flex-wrap gap-3">
            <Button variant="secondary" onClick={handleApplyMemoryPolicy} loading={loadingAction === "applyMemoryPolicy"}>
              Apply Memory Policy
            </Button>
            <Button variant="primary" onClick={handleCleanMemoryIndexes} loading={loadingAction === "cleanMemoryIndexes"}>
              Clean Memory Indexes
            </Button>
          </div>
        </Card>

        <Card>
          <SectionHeader icon={<DatabaseZap size={18} />} title="Browser Memory Cleanup" />
          <p className="mt-3 text-sm leading-6 text-app-muted">
            Tools for keeping smart-captured browser pages idempotent while extraction diagnostics are tuned.
          </p>
          <div className="mt-5 flex flex-wrap gap-3">
            <Button variant="secondary" onClick={handleDedupeBrowserPages} loading={loadingAction === "dedupeBrowserPages"}>
              Deduplicate Browser Pages
            </Button>
            <Button variant="secondary" onClick={handleFixBrowserContentQuality} loading={loadingAction === "fixBrowserContentQuality"}>
              Fix Browser Content Quality
            </Button>
          </div>
        </Card>

        <Card>
          <SectionHeader icon={<DatabaseZap size={18} />} title="Embeddings / Semantic Search" />
          <div className="mt-4 space-y-3 text-sm">
            <Row label="enabled" value={String(embeddingStatus?.enabled ?? status?.embeddings_enabled ?? false)} />
            <Row label="selected model" value={embeddingStatus?.selected_embedding_model ?? status?.selected_embedding_model ?? status?.embedding_model ?? "nomic-embed-text"} />
            <Row label="index model" value={embeddingStatus?.index_model ?? status?.embedding_index_model ?? "none"} />
            <Row label="index stale" value={String(embeddingStatus?.index_stale ?? status?.embedding_index_stale ?? false)} tone={embeddingStatus?.index_stale ?? status?.embedding_index_stale ? "danger" : "success"} />
            <Row label="model available" value={String(embeddingStatus?.embedding_model_available ?? status?.embedding_model_available ?? false)} tone={embeddingStatus?.embedding_model_available ?? status?.embedding_model_available ? "success" : "danger"} />
            <Row
              label="Ollama"
              value={(embeddingStatus?.ollama_available ?? status?.ollama_available) ? "available" : "unavailable"}
              tone={(embeddingStatus?.ollama_available ?? status?.ollama_available) ? "success" : "danger"}
            />
            <Row
              label="Chroma"
              value={(embeddingStatus?.chroma_available ?? status?.chroma_available) ? "available" : "unavailable"}
              tone={(embeddingStatus?.chroma_available ?? status?.chroma_available) ? "success" : "danger"}
            />
            <Row label="indexed" value={String(embeddingStatus?.indexed_count ?? status?.chroma_indexed_count ?? 0)} />
            <Row label="indexable events" value={String(embeddingStatus?.indexable_events ?? devState?.memory_policy?.indexable_events ?? 0)} />
            <Row label="non-indexable" value={String(embeddingStatus?.non_indexable_events ?? devState?.memory_policy?.non_indexable_events ?? 0)} />
            {Object.entries(embeddingStatus?.event_status ?? {}).map(([statusKey, count]) => (
              <Row key={statusKey} label={statusKey} value={String(count)} />
            ))}
          </div>
          <p className="mt-4 text-xs leading-5 text-app-muted">
            Semantic search uses local Ollama embeddings. Memory content stays on this machine.
          </p>
          <div className="mt-5 flex flex-wrap gap-3">
            <Button variant="secondary" onClick={refreshAll} loading={loadingAction === "refresh"}>
              Refresh
            </Button>
            <Button variant="primary" onClick={handleReindexEmbeddings} loading={loadingAction === "reindexEmbeddings"}>
              Reindex All
            </Button>
            <Button variant="secondary" onClick={handleClearEmbeddingIndex} loading={loadingAction === "clearEmbeddings"}>
              Clear Vector Index
            </Button>
          </div>
          {embeddingResult ? (
            <div className="mt-4 flex flex-wrap gap-2">
              <Badge variant="success">indexed: {embeddingResult.indexed}</Badge>
              <Badge variant={embeddingResult.failed ? "warning" : "default"}>failed: {embeddingResult.failed}</Badge>
              <Badge>skipped: {embeddingResult.skipped}</Badge>
              <Badge>total: {embeddingResult.total}</Badge>
            </div>
          ) : null}
        </Card>

        <Card>
          <SectionHeader icon={<Activity size={18} />} title="Context Debug" />
          <div className="mt-4 space-y-3">
            <LabeledInput label="Query" value={contextQuery} onChange={setContextQuery} />
            <Button variant="primary" onClick={handleBuildContext} loading={loadingAction === "buildContext"}>
              Build Context
            </Button>
            {contextResult ? (
              <div className="space-y-3 rounded-md border border-app-border bg-zinc-950 p-3 text-sm">
                <div className="flex flex-wrap gap-2">
                  <Badge variant="info">direct: {contextResult.direct_events.length}</Badge>
                  <Badge variant="info">related: {contextResult.related_events.length}</Badge>
                  <Badge>relationships: {contextResult.relationships.length}</Badge>
                  <Badge>tokens: ~{contextResult.token_estimate}</Badge>
                </div>
                <IntentDebug metadata={contextResult.metadata} />
                <p className="text-app-muted">{contextResult.summary}</p>
                {contextResult.source_groups.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {contextResult.source_groups.map((group) => (
                      <Badge key={group.source}>
                        {group.source}: {group.count}
                      </Badge>
                    ))}
                  </div>
                ) : null}
                {contextResult.warnings.length > 0 ? (
                  <p className="text-amber-200">{contextResult.warnings.join("; ")}</p>
                ) : null}
              </div>
            ) : null}
          </div>
        </Card>

        <Card>
          <SectionHeader icon={<Activity size={18} />} title="Task Planner Debug" />
          <div className="mt-4 space-y-3">
            <LabeledInput label="Instruction" value={plannerInstruction} onChange={setPlannerInstruction} />
            <Button variant="primary" onClick={handlePlanTask} loading={loadingAction === "planTask"}>
              Plan Task
            </Button>
            {plannerResult ? (
              <div className="space-y-3 rounded-md border border-app-border bg-zinc-950 p-3 text-sm">
                <div className="flex flex-wrap gap-2">
                  <Badge variant="info">{plannerResult.plan.task_type}</Badge>
                  <Badge>confidence {plannerResult.plan.confidence.toFixed(2)}</Badge>
                  <Badge>{plannerResult.model}</Badge>
                  <Badge>{plannerResult.provider}</Badge>
                </div>
                {plannerResult.warning ? <p className="text-amber-200">{plannerResult.warning}</p> : null}
                {plannerResult.context_summary ? <p className="text-app-muted">{plannerResult.context_summary}</p> : null}
                <JsonPreview value={plannerResult.plan} />
              </div>
            ) : null}
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-[1.1fr_0.9fr] gap-4">
        <Card>
          <div className="flex items-center justify-between gap-4">
            <SectionHeader icon={<Activity size={18} />} title="Recent Raw Events" />
            <Button variant="ghost" onClick={refreshAll} loading={loadingAction === "refresh"}>
              <RefreshCw size={16} />
              Refresh
            </Button>
          </div>
          <p className="mt-3 text-xs text-app-muted">Raw events include hidden chat events.</p>
          <div className="mt-4 space-y-3">
            {events.length === 0 ? (
              <EmptyState title="No Events" description="Seed or ingest events to inspect raw local memory." />
            ) : (
              events.map((event) => <RawEventRow key={event.id} event={event} />)
            )}
          </div>
        </Card>

        <Card>
          <SectionHeader icon={<Send size={18} />} title="Manual Ingest Test" />
          <div className="mt-4 space-y-3">
            <label className="block text-xs font-medium uppercase text-app-muted">
              Source
              <select
                value={form.source}
                onChange={(event) => setForm((current) => ({ ...current, source: event.target.value as EventSource }))}
                className="mt-2 h-10 w-full rounded-md border border-app-border bg-zinc-950 px-3 text-sm text-app-text outline-none focus:border-app-primary"
              >
                {eventSources.map((source) => (
                  <option key={source} value={source}>
                    {source}
                  </option>
                ))}
              </select>
            </label>
            <LabeledInput label="Type" value={form.type} onChange={(value) => setForm((current) => ({ ...current, type: value }))} />
            <LabeledInput label="Title" value={form.title} onChange={(value) => setForm((current) => ({ ...current, title: value }))} />
            <label className="block text-xs font-medium uppercase text-app-muted">
              Content
              <textarea
                value={form.content}
                onChange={(event) => setForm((current) => ({ ...current, content: event.target.value }))}
                className="mt-2 min-h-24 w-full resize-none rounded-md border border-app-border bg-zinc-950 px-3 py-2 text-sm leading-6 text-app-text outline-none focus:border-app-primary"
              />
            </label>
            <label className="block text-xs font-medium uppercase text-app-muted">
              Metadata JSON
              <textarea
                value={form.metadata}
                onChange={(event) => setForm((current) => ({ ...current, metadata: event.target.value }))}
                placeholder='{"project":"mindos"}'
                className="mt-2 min-h-20 w-full resize-none rounded-md border border-app-border bg-zinc-950 px-3 py-2 text-sm leading-6 text-app-text outline-none placeholder:text-zinc-600 focus:border-app-primary"
              />
            </label>
            <Button variant="primary" onClick={handleManualIngest} loading={loadingAction === "ingest"}>
              Ingest event
            </Button>
          </div>
        </Card>

        <Card>
          <SectionHeader icon={<Send size={18} />} title="External Ingest Test" />
          <div className="mt-4 space-y-3">
            <label className="block text-xs font-medium uppercase text-app-muted">
              Source
              <select
                value={externalForm.source}
                onChange={(event) => setExternalForm((current) => ({ ...current, source: event.target.value }))}
                className="mt-2 h-10 w-full rounded-md border border-app-border bg-zinc-950 px-3 text-sm text-app-text outline-none focus:border-app-primary"
              >
                {["vscode_extension", "browser_extension", "activity_tracker", "local_agent"].map((source) => (
                  <option key={source} value={source}>
                    {source}
                  </option>
                ))}
              </select>
            </label>
            <LabeledInput label="Type" value={externalForm.type} onChange={(value) => setExternalForm((current) => ({ ...current, type: value }))} />
            <LabeledInput label="Title" value={externalForm.title} onChange={(value) => setExternalForm((current) => ({ ...current, title: value }))} />
            <label className="block text-xs font-medium uppercase text-app-muted">
              Content
              <textarea
                value={externalForm.content}
                onChange={(event) => setExternalForm((current) => ({ ...current, content: event.target.value }))}
                className="mt-2 min-h-20 w-full resize-none rounded-md border border-app-border bg-zinc-950 px-3 py-2 text-sm leading-6 text-app-text outline-none focus:border-app-primary"
              />
            </label>
            <label className="block text-xs font-medium uppercase text-app-muted">
              Metadata JSON
              <textarea
                value={externalForm.metadata}
                onChange={(event) => setExternalForm((current) => ({ ...current, metadata: event.target.value }))}
                className="mt-2 min-h-24 w-full resize-none rounded-md border border-app-border bg-zinc-950 px-3 py-2 text-sm leading-6 text-app-text outline-none focus:border-app-primary"
              />
            </label>
            <Button variant="primary" onClick={handleExternalIngest} loading={loadingAction === "externalIngest"}>
              Send External Event
            </Button>
            {externalResult ? (
              <div className="rounded-md border border-app-border bg-zinc-950 p-3 text-sm">
                <Badge variant="success">{externalResult.status}</Badge>
                <p className="mt-2 text-app-muted">{externalResult.message}</p>
                <p className="mt-1 text-xs text-app-muted">{externalResult.event_id}</p>
              </div>
            ) : null}
          </div>
        </Card>
      </div>
    </div>
  );
}

function parseMetadata(value: string): Record<string, unknown> {
  if (!value.trim()) {
    return {};
  }

  const parsed = JSON.parse(value) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new SyntaxError("Metadata must be a JSON object.");
  }
  return parsed as Record<string, unknown>;
}

function SectionHeader({ icon, title }: { icon: ReactNode; title: string }) {
  return (
    <div className="flex items-center gap-3">
      <div className="flex h-9 w-9 items-center justify-center rounded-md border border-violet-500/30 bg-violet-500/10 text-violet-300">
        {icon}
      </div>
      <h2 className="text-base font-semibold text-app-text">{title}</h2>
    </div>
  );
}

function Row({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "success" | "danger" }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-app-muted">{label}</span>
      <Badge variant={tone === "success" ? "success" : tone === "danger" ? "danger" : "default"}>{value}</Badge>
    </div>
  );
}

function IntentDebug({ metadata }: { metadata?: Record<string, unknown> }) {
  const intent = metadata?.intent;
  if (!intent || typeof intent !== "object" || Array.isArray(intent)) {
    return null;
  }
  const details = intent as Record<string, unknown>;
  const searchTerms = Array.isArray(details.search_terms) ? details.search_terms.map(String) : [];
  const preferredSources = Array.isArray(details.preferred_sources) ? details.preferred_sources.map(String) : [];
  const excludedTypes = Array.isArray(details.excluded_types) ? details.excluded_types.map(String) : [];
  return (
    <div className="space-y-2 rounded-md border border-app-border bg-black/20 p-3">
      <div className="flex flex-wrap gap-2">
        <Badge variant="info">intent: {String(details.intent ?? "-")}</Badge>
        <Badge>profile: {String(details.retrieval_profile ?? "-")}</Badge>
        <Badge>confidence: {Number(details.confidence ?? 0).toFixed(2)}</Badge>
      </div>
      {searchTerms.length > 0 ? <p className="text-xs text-app-muted">Search terms: {searchTerms.join(", ")}</p> : null}
      {preferredSources.length > 0 ? <p className="text-xs text-app-muted">Preferred sources: {preferredSources.join(", ")}</p> : null}
      {excludedTypes.length > 0 ? <p className="text-xs text-app-muted">Excluded types: {excludedTypes.join(", ")}</p> : null}
    </div>
  );
}

function RawEventRow({ event }: { event: MemoryEvent }) {
  return (
    <div className="rounded-md border border-app-border bg-zinc-950 px-4 py-3">
      <div className="flex items-center gap-2">
        <Badge variant="info">{event.source}</Badge>
        <Badge>{event.type}</Badge>
        <span className="ml-auto text-xs text-app-muted">{formatTimestamp(event.timestamp)}</span>
      </div>
      <h3 className="mt-3 text-sm font-semibold text-app-text">{event.title}</h3>
    </div>
  );
}

function LabeledInput({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="block text-xs font-medium uppercase text-app-muted">
      {label}
      <Input className="mt-2" value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function StatusMessage({ variant, message }: { variant: "success" | "danger"; message: string }) {
  return (
    <div
      className={`rounded-md border px-4 py-3 text-sm ${
        variant === "success"
          ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
          : "border-red-500/30 bg-red-500/10 text-red-200"
      }`}
    >
      {message}
    </div>
  );
}

function JsonPreview({ value }: { value: unknown }) {
  return (
    <pre className="max-h-72 overflow-auto rounded-md border border-app-border bg-black/20 p-3 text-xs leading-5 text-app-text">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function formatTimestamp(value: string) {
  return new Date(value).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
