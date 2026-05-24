import { AlertTriangle, CheckCircle2, ClipboardCheck, History, Send } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { Badge } from "../components/shared/Badge";
import { Button } from "../components/shared/Button";
import { Card } from "../components/shared/Card";
import { EmptyState } from "../components/shared/EmptyState";
import { cancelTask, confirmTask, executeTask, getPendingTasks, getTaskHistory } from "../services/api";
import type { TaskHistoryItem, TaskResponse } from "../types";

const exampleTasks = [
  "Create a Jira ticket for the login bug",
  "Draft an email about deployment failure",
  "Suggest a branch name for JWT fix",
  "Generate a commit message for recent changes",
  "Prepare a weekly report",
];

export function TasksPage() {
  const [searchParams] = useSearchParams();
  const [taskText, setTaskText] = useState("");
  const [activeTask, setActiveTask] = useState<TaskResponse | null>(null);
  const [pendingTasks, setPendingTasks] = useState<TaskHistoryItem[]>([]);
  const [history, setHistory] = useState<TaskHistoryItem[]>([]);
  const [highlightedTaskId, setHighlightedTaskId] = useState<string | null>(null);
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pendingSectionRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const instruction = searchParams.get("instruction");
    if (instruction) {
      setTaskText(instruction);
    }
  }, [searchParams]);

  useEffect(() => {
    void refreshTasks();
  }, []);

  async function refreshTasks() {
    const [historyResponse, pendingResponse] = await Promise.all([getTaskHistory(), getPendingTasks()]);
    setHistory(historyResponse.tasks);
    setPendingTasks(pendingResponse.tasks);
  }

  async function safeRefreshTasks() {
    try {
      await refreshTasks();
    } catch {
      setHistory([]);
      setPendingTasks([]);
    }
  }

  async function handleSubmit() {
    const instruction = taskText.trim();
    if (!instruction) {
      return;
    }

    setLoadingAction("execute");
    setError(null);
    try {
      const response = await executeTask(instruction);
      setActiveTask(response);
      setTaskText("");
      await refreshTasks();
    } catch {
      setError("Could not prepare task. Backend may be offline.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleConfirmToken(confirmationToken: string) {
    setLoadingAction(`confirm:${confirmationToken}`);
    setError(null);
    try {
      const response = await confirmTask(confirmationToken);
      setActiveTask(response);
      await refreshTasks();
    } catch {
      setError("Could not confirm task.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleCancelTask(taskId: string) {
    setLoadingAction(`cancel:${taskId}`);
    setError(null);
    try {
      const response = await cancelTask(taskId);
      setActiveTask(response);
      await refreshTasks();
    } catch {
      setError("Could not cancel task.");
    } finally {
      setLoadingAction(null);
    }
  }

  function handleReview(taskId: string) {
    setHighlightedTaskId(taskId);
    pendingSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    window.setTimeout(() => setHighlightedTaskId(null), 1400);
  }

  const activePendingTask = activeTask?.status === "confirmation_required" ? activeTask : null;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-app-text">Tasks</h1>
        <p className="mt-2 text-sm text-app-muted">Create, preview, confirm, and track actions safely.</p>
      </header>

      <div className="rounded-md border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
        Development mode: task actions are mocked. Real integrations will require confirmation later.
      </div>

      {error ? <p className="rounded-md border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</p> : null}

      <Card className="space-y-4">
        <textarea
          value={taskText}
          onChange={(event) => setTaskText(event.target.value)}
          placeholder="Tell MindOS what task you want to prepare..."
          className="min-h-28 w-full resize-none rounded-md border border-app-border bg-zinc-950 px-4 py-3 text-sm leading-6 text-app-text outline-none transition placeholder:text-zinc-600 focus:border-app-primary focus:ring-2 focus:ring-violet-900/50"
        />
        <div className="flex flex-wrap gap-2">
          {exampleTasks.map((task) => (
            <button key={task} type="button" onClick={() => setTaskText(task)} className="transition hover:opacity-80">
              <Badge variant="info">{task}</Badge>
            </button>
          ))}
        </div>
        <div className="flex justify-end">
          <Button type="button" variant="primary" onClick={handleSubmit} disabled={!taskText.trim()} loading={loadingAction === "execute"}>
            <Send size={16} />
            Prepare Task
          </Button>
        </div>
      </Card>

      {activePendingTask ? (
        <TaskPreviewCard
          task={activePendingTask}
          onConfirm={() => activePendingTask.confirmation_token && handleConfirmToken(activePendingTask.confirmation_token)}
          onCancel={() => activePendingTask.task_id && handleCancelTask(activePendingTask.task_id)}
          loading={loadingAction === `confirm:${activePendingTask.confirmation_token}`}
        />
      ) : activeTask ? (
        <TaskResultCard task={activeTask} />
      ) : null}

      <div ref={pendingSectionRef}>
        <Card>
          <div className="flex items-center gap-3">
            <ClipboardCheck size={18} className="text-violet-300" />
            <h2 className="text-base font-semibold text-app-text">Pending Confirmations</h2>
          </div>
          <div className="mt-4 space-y-3">
            {pendingTasks.length === 0 ? (
              <EmptyState title="No Pending Confirmations" description="Tasks waiting for approval will appear here." />
            ) : (
              pendingTasks.map((task) => (
                <PendingTaskCard
                  key={task.id}
                  task={task}
                  highlighted={highlightedTaskId === task.id}
                  onConfirm={() => task.confirmation_token && handleConfirmToken(task.confirmation_token)}
                  onCancel={() => handleCancelTask(task.id)}
                  confirmLoading={loadingAction === `confirm:${task.confirmation_token}`}
                  cancelLoading={loadingAction === `cancel:${task.id}`}
                />
              ))
            )}
          </div>
        </Card>
      </div>

      <Card>
        <div className="flex items-center gap-3">
          <History size={18} className="text-violet-300" />
          <h2 className="text-base font-semibold text-app-text">Recent Tasks</h2>
        </div>
        <div className="mt-4 space-y-3">
          {history.length === 0 ? (
            <EmptyState title="No Task History" description="Prepared and completed tasks will appear here." />
          ) : (
            history.map((task) => (
              <HistoryRow
                key={task.id}
                task={task}
                onReview={() => handleReview(task.id)}
                onConfirm={() => task.confirmation_token && handleConfirmToken(task.confirmation_token)}
                onCancel={() => handleCancelTask(task.id)}
                hasPendingCard={pendingTasks.some((pending) => pending.id === task.id)}
              />
            ))
          )}
        </div>
      </Card>

      <button type="button" className="sr-only" onClick={() => void safeRefreshTasks()}>
        Refresh task state
      </button>
    </div>
  );
}

function PendingTaskCard({
  task,
  highlighted,
  onConfirm,
  onCancel,
  confirmLoading,
  cancelLoading,
}: {
  task: TaskHistoryItem;
  highlighted: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  confirmLoading: boolean;
  cancelLoading: boolean;
}) {
  return (
    <div
      className={`rounded-md border bg-zinc-950 px-4 py-3 transition ${
        highlighted ? "border-violet-400 shadow-sm shadow-violet-950/60" : "border-app-border"
      }`}
    >
      <div className="flex items-center gap-2">
        <Badge variant="warning">{task.task_type}</Badge>
        <Badge>confirmation_required</Badge>
        <span className="ml-auto text-xs text-app-muted">{formatTimestamp(task.created_at)}</span>
      </div>
      <p className="mt-3 text-sm font-medium text-app-text">{task.instruction}</p>
      <p className="mt-2 text-sm text-app-muted">{previewSummary(task.preview)}</p>
      <div className="mt-3 flex items-center gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
        <AlertTriangle size={16} />
        <span>This action is waiting for your confirmation. No real external action will happen. Mock mode is active.</span>
      </div>
      <div className="mt-4 flex gap-3">
        <Button variant="primary" onClick={onConfirm} loading={confirmLoading} disabled={!task.confirmation_token}>
          Confirm
        </Button>
        <Button variant="secondary" onClick={onCancel} loading={cancelLoading}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

function TaskPreviewCard({ task, onConfirm, onCancel, loading }: { task: TaskResponse; onConfirm: () => void; onCancel: () => void; loading: boolean }) {
  return (
    <Card>
      <div className="flex items-start gap-3">
        <ClipboardCheck className="mt-1 text-violet-300" size={20} />
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <Badge variant="warning">{task.task_type}</Badge>
            <Badge>{task.status}</Badge>
          </div>
          <h2 className="mt-3 text-base font-semibold text-app-text">Confirmation Required</h2>
          <p className="mt-2 text-sm text-app-muted">{task.message}</p>
          <p className="mt-3 rounded-md border border-violet-500/30 bg-violet-500/10 px-3 py-2 text-sm text-violet-100">
            This task preview was saved to Memory.
          </p>
          <div className="mt-3 flex items-center gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
            <AlertTriangle size={16} />
            <span>No real external action will happen. This is a mock execution.</span>
          </div>
          <JsonBlock title="Preview" value={task.preview} />
          {task.sources_used?.length ? <JsonBlock title="Sources Used" value={task.sources_used} /> : null}
          <div className="mt-4 flex gap-3">
            <Button variant="primary" onClick={onConfirm} loading={loading} disabled={!task.confirmation_token}>
              Confirm Mock Execution
            </Button>
            <Button variant="secondary" onClick={onCancel}>
              Cancel
            </Button>
          </div>
        </div>
      </div>
    </Card>
  );
}

function TaskResultCard({ task }: { task: TaskResponse }) {
  const isMock = task.result?.mock === true;
  return (
    <Card>
      <div className="flex items-start gap-3">
        <CheckCircle2 className="mt-1 text-emerald-300" size={20} />
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <Badge variant={task.status === "completed" ? "success" : task.status === "failed" ? "danger" : "default"}>{task.status}</Badge>
            <Badge variant="info">{task.task_type}</Badge>
          </div>
          <p className="mt-3 text-sm text-app-muted">{task.message}</p>
          {task.status === "completed" ? (
            <p className="mt-3 rounded-md border border-violet-500/30 bg-violet-500/10 px-3 py-2 text-sm text-violet-100">
              This task was also saved to Memory.
            </p>
          ) : null}
          {isMock ? <p className="mt-3 rounded-md border border-violet-500/30 bg-violet-500/10 px-3 py-2 text-sm text-violet-100">Mock result only. No real external action happened.</p> : null}
          <JsonBlock title="Result" value={task.result ?? task.preview} />
        </div>
      </div>
    </Card>
  );
}

function HistoryRow({
  task,
  onReview,
  onConfirm,
  onCancel,
  hasPendingCard,
}: {
  task: TaskHistoryItem;
  onReview: () => void;
  onConfirm: () => void;
  onCancel: () => void;
  hasPendingCard: boolean;
}) {
  const isPending = task.status === "confirmation_required";
  return (
    <div className="rounded-md border border-app-border bg-zinc-950 px-4 py-3">
      <div className="flex items-center gap-2">
        <Badge variant="info">{task.task_type}</Badge>
        <Badge variant={isPending ? "warning" : "default"}>{isPending ? "Confirmation required" : task.status}</Badge>
        <span className="ml-auto text-xs text-app-muted">{formatTimestamp(task.created_at)}</span>
      </div>
      <p className="mt-2 text-sm text-app-text">{task.instruction}</p>
      {isPending ? (
        <div className="mt-3 flex gap-2">
          {hasPendingCard ? (
            <Button className="h-8 px-3" variant="secondary" onClick={onReview}>
              Review
            </Button>
          ) : (
            <>
              <Button className="h-8 px-3" variant="primary" onClick={onConfirm} disabled={!task.confirmation_token}>
                Confirm
              </Button>
              <Button className="h-8 px-3" variant="secondary" onClick={onCancel}>
                Cancel
              </Button>
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}

function previewSummary(preview: Record<string, unknown> | null) {
  if (!preview) {
    return "No preview details available.";
  }
  const title = preview.title || preview.subject || preview.pr_title || preview.branch_name || preview.commit_message;
  if (typeof title === "string" && title.trim()) {
    return title;
  }
  const summary = preview.context_summary;
  return typeof summary === "string" ? summary : "Preview details are available.";
}

function JsonBlock({ title, value }: { title: string; value: unknown }) {
  return (
    <div className="mt-4">
      <p className="text-xs uppercase text-app-muted">{title}</p>
      <pre className="mt-2 max-h-72 overflow-auto rounded-md border border-app-border bg-zinc-950 p-3 text-xs leading-5 text-app-text">
        {JSON.stringify(value ?? {}, null, 2)}
      </pre>
    </div>
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
