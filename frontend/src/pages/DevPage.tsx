import { Activity, DatabaseZap, HeartPulse, RefreshCw, Send, Trash2 } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";

import {
  buildContext,
  clearChats,
  clearEvents,
  clearRelationships,
  clearTasks,
  getErrorMessage,
  getDevState,
  getHealth,
  getRecentEvents,
  getStatus,
  ingestEvent,
  planTask,
  rebuildRelationships,
  seedSampleEvents,
  testLLM,
} from "../services/api";
import type { BackendHealth, BackendStatus, ContextPackage, DevState, EventSource, MemoryEvent, TaskPlanningResponse, TestLLMResponse } from "../types";
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

export function DevPage() {
  const [health, setHealth] = useState<BackendHealth | null>(null);
  const [status, setStatus] = useState<BackendStatus | null>(null);
  const [devState, setDevState] = useState<DevState | null>(null);
  const [events, setEvents] = useState<MemoryEvent[]>([]);
  const [form, setForm] = useState<IngestForm>(emptyForm);
  const [contextQuery, setContextQuery] = useState("jwt login failure");
  const [contextResult, setContextResult] = useState<ContextPackage | null>(null);
  const [llmTestMessage, setLlmTestMessage] = useState("Say hello from MindOS");
  const [llmTestResult, setLlmTestResult] = useState<TestLLMResponse | null>(null);
  const [plannerInstruction, setPlannerInstruction] = useState("Create a Jira ticket for the login bug");
  const [plannerResult, setPlannerResult] = useState<TaskPlanningResponse | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingAction, setLoadingAction] = useState<string | null>(null);

  const backendOnline = status !== null;

  useEffect(() => {
    void refreshAll();
  }, []);

  async function refreshAll() {
    setLoadingAction("refresh");
    setError(null);
    try {
      const statusResponse = await getStatus();
      setStatus(statusResponse);
      try {
        const [healthResponse, stateResponse, eventsResponse] = await Promise.all([
          getHealth(),
          getDevState(),
          getRecentEvents(undefined, 20, undefined, true),
        ]);
        setHealth(healthResponse);
        setDevState(stateResponse);
        setEvents(eventsResponse.events);
      } catch (secondaryError) {
        console.error("DevPage secondary state refresh failed", secondaryError);
        setHealth(null);
        setDevState(null);
        setEvents([]);
      }
    } catch (caughtError) {
      console.error("DevPage status refresh failed", caughtError);
      setHealth(null);
      setStatus(null);
      setDevState(null);
      setEvents([]);
      setError(getErrorMessage(caughtError));
    } finally {
      setLoadingAction(null);
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
      await clearTasks();
      setMessage("Cleared local task history.");
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
            <Row label="num ctx" value={String(status?.ollama_num_ctx ?? devState?.ollama_num_ctx ?? "-")} />
            <Row label="direct limit" value={String(status?.chat_context_direct_limit ?? devState?.chat_context_direct_limit ?? "-")} />
            <Row label="related each" value={String(status?.chat_context_related_per_event ?? devState?.chat_context_related_per_event ?? "-")} />
            <Row label="max context chars" value={String(status?.chat_context_max_total_chars ?? devState?.chat_context_max_total_chars ?? "-")} />
            <Row label="history limit" value={String(status?.chat_history_limit ?? devState?.chat_history_limit ?? "-")} />
          </div>
          {!(status?.ollama_available ?? devState?.ollama_available) ? (
            <p className="mt-4 text-xs leading-5 text-amber-200">Start Ollama and pull qwen3:8b to enable local chat.</p>
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
          <SectionHeader icon={<Trash2 size={18} />} title="Clear Local Data" />
          <p className="mt-3 text-sm text-app-muted">Remove all in-memory events from this backend process.</p>
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
          </div>
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
