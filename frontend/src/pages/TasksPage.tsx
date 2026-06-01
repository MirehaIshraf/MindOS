import { AlertTriangle, CheckCircle2, ClipboardCheck, FolderOpen, History, Send } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { Badge } from "../components/shared/Badge";
import { Button } from "../components/shared/Button";
import { Card } from "../components/shared/Card";
import { EmptyState } from "../components/shared/EmptyState";
import { TaskPreviewDetails } from "../components/tasks/TaskPreviewDetails";
import {
  cancelTask,
  confirmTask,
  executeFileTask,
  executeTask,
  getErrorMessage,
  getPendingTasks,
  getTaskHistory,
  prepareFileTask,
  scanFileTask,
  undoFileTask,
} from "../services/api";
import type { FileOperation, FileSnapshotResponse, FileTaskExecutionResult, FileTaskPlan, FileTaskUndoResult, TaskHistoryItem, TaskResponse } from "../types";

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
  const [modelId, setModelId] = useState<string | null>(null);
  const [activeTask, setActiveTask] = useState<TaskResponse | null>(null);
  const [pendingTasks, setPendingTasks] = useState<TaskHistoryItem[]>([]);
  const [history, setHistory] = useState<TaskHistoryItem[]>([]);
  const [highlightedTaskId, setHighlightedTaskId] = useState<string | null>(null);
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastTaskApiError, setLastTaskApiError] = useState<Record<string, unknown> | null>(null);
  const pendingSectionRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const instruction = searchParams.get("instruction");
    if (instruction) {
      setTaskText(instruction);
    }
    setModelId(searchParams.get("model_id"));
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
    setLastTaskApiError(null);
    try {
      const response = await executeTask(instruction, true, modelId);
      setActiveTask(response);
      setTaskText("");
      await refreshTasks();
    } catch (caughtError) {
      console.error("TasksPage failed to execute task", caughtError);
      setError(getErrorMessage(caughtError));
      setLastTaskApiError(taskApiErrorDetails(caughtError));
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
    } catch (caughtError) {
      console.error("TasksPage failed to confirm task", caughtError);
      setError(getErrorMessage(caughtError));
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
    } catch (caughtError) {
      console.error("TasksPage failed to cancel task", caughtError);
      setError(getErrorMessage(caughtError));
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
        File System tasks can perform real local file moves only after confirmation. Other task actions remain mocked.
      </div>

      {error ? <p className="rounded-md border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</p> : null}
      {lastTaskApiError ? (
        <details className="rounded-md border border-app-border bg-app-panel p-4">
          <summary className="cursor-pointer text-sm text-app-muted">Last task API error</summary>
          <pre className="mt-3 max-h-72 overflow-auto rounded-md bg-zinc-950 p-3 text-xs leading-5 text-app-text">
            {JSON.stringify(lastTaskApiError, null, 2)}
          </pre>
        </details>
      ) : null}

      <FileSystemTaskPanel />

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
        {loadingAction === "execute" ? <p className="text-sm text-app-muted">Planning task from local memory...</p> : null}
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

function FileSystemTaskPanel() {
  const [rootPath, setRootPath] = useState("");
  const [instruction, setInstruction] = useState("Organize this folder by file type");
  const [maxDepth, setMaxDepth] = useState(2);
  const [maxFiles, setMaxFiles] = useState(500);
  const [snapshot, setSnapshot] = useState<FileSnapshotResponse | null>(null);
  const [plan, setPlan] = useState<FileTaskPlan | null>(null);
  const [result, setResult] = useState<FileTaskExecutionResult | null>(null);
  const [undoResult, setUndoResult] = useState<FileTaskUndoResult | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const operationGroups = plan ? groupFileOperations(plan.operations) : null;
  const canExecute = Boolean(plan && plan.status !== "blocked" && plan.operations.length > 0);

  async function handleScan() {
    setLoading("scan");
    setError(null);
    try {
      const response = await scanFileTask({ root_path: rootPath, max_depth: maxDepth, max_files: maxFiles });
      setSnapshot(response);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError));
    } finally {
      setLoading(null);
    }
  }

  async function handlePrepare() {
    setLoading("prepare");
    setError(null);
    setResult(null);
    setUndoResult(null);
    try {
      const response = await prepareFileTask({
        root_path: rootPath,
        instruction,
        max_depth: maxDepth,
        max_files: maxFiles,
        dry_run: true,
      });
      setPlan(response);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError));
    } finally {
      setLoading(null);
    }
  }

  async function handleExecute() {
    if (!plan) return;
    setLoading("execute");
    setError(null);
    try {
      const response = await executeFileTask(plan.task_id);
      setResult(response);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError));
    } finally {
      setLoading(null);
    }
  }

  async function handleUndo() {
    if (!plan) return;
    setLoading("undo");
    setError(null);
    try {
      const response = await undoFileTask(plan.task_id);
      setUndoResult(response);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError));
    } finally {
      setLoading(null);
    }
  }

  return (
    <Card className="space-y-4">
      <div className="flex items-center gap-3">
        <FolderOpen size={18} className="text-violet-300" />
        <div>
          <h2 className="text-base font-semibold text-app-text">File System Task</h2>
          <p className="text-sm text-app-muted">Plan local file organization, preview every operation, then confirm execution.</p>
        </div>
      </div>

      {error ? <p className="rounded-md border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</p> : null}

      <div className="grid gap-3 md:grid-cols-[1fr_120px_120px]">
        <label className="space-y-1 text-sm">
          <span className="text-app-muted">Root folder path</span>
          <input
            value={rootPath}
            onChange={(event) => setRootPath(event.target.value)}
            placeholder="D:\\Downloads"
            className="w-full rounded-md border border-app-border bg-zinc-950 px-3 py-2 text-app-text outline-none focus:border-app-primary"
          />
        </label>
        <label className="space-y-1 text-sm">
          <span className="text-app-muted">Max depth</span>
          <input
            type="number"
            min={0}
            max={5}
            value={maxDepth}
            onChange={(event) => setMaxDepth(Number(event.target.value))}
            className="w-full rounded-md border border-app-border bg-zinc-950 px-3 py-2 text-app-text outline-none focus:border-app-primary"
          />
        </label>
        <label className="space-y-1 text-sm">
          <span className="text-app-muted">Max files</span>
          <input
            type="number"
            min={1}
            max={1000}
            value={maxFiles}
            onChange={(event) => setMaxFiles(Number(event.target.value))}
            className="w-full rounded-md border border-app-border bg-zinc-950 px-3 py-2 text-app-text outline-none focus:border-app-primary"
          />
        </label>
      </div>

      <label className="space-y-1 text-sm">
        <span className="text-app-muted">Instruction</span>
        <textarea
          value={instruction}
          onChange={(event) => setInstruction(event.target.value)}
          className="min-h-20 w-full resize-none rounded-md border border-app-border bg-zinc-950 px-3 py-2 text-app-text outline-none focus:border-app-primary"
        />
      </label>

      <div className="flex flex-wrap gap-2">
        {[
          "Organize this folder by file type",
          "Move PDFs into a PDFs folder",
          "Create folders for images, videos, installers, and archives",
          "Rename screenshots by date",
          "Create a project folder structure",
        ].map((prompt) => (
          <button key={prompt} type="button" onClick={() => setInstruction(prompt)} className="transition hover:opacity-80">
            <Badge variant="info">{prompt}</Badge>
          </button>
        ))}
      </div>

      <div className="flex flex-wrap gap-3">
        <Button variant="secondary" onClick={() => void handleScan()} loading={loading === "scan"} disabled={!rootPath.trim()}>
          Scan
        </Button>
        <Button variant="primary" onClick={() => void handlePrepare()} loading={loading === "prepare"} disabled={!rootPath.trim() || !instruction.trim()}>
          Prepare Plan
        </Button>
      </div>

      {snapshot ? (
        <div className="rounded-md border border-app-border bg-zinc-950 p-3 text-sm">
          <div className="flex flex-wrap gap-2">
            <Badge variant="success">{snapshot.total_files} files</Badge>
            <Badge>{snapshot.total_folders} folders</Badge>
            <Badge>{snapshot.root_path}</Badge>
          </div>
          {snapshot.warnings.length ? <WarningList title="Scan warnings" items={snapshot.warnings} /> : null}
        </div>
      ) : null}

      {plan ? (
        <div className="space-y-4 rounded-md border border-app-border bg-zinc-950 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={plan.status === "blocked" ? "danger" : "warning"}>{plan.status}</Badge>
            <Badge variant={plan.risk_level === "low" ? "success" : "warning"}>risk: {plan.risk_level}</Badge>
            <Badge>{plan.operations.length} operations</Badge>
            {plan.planner_model ? <Badge variant="info">planner: {plan.planner_model}</Badge> : null}
          </div>
          <p className="text-sm text-app-text">{plan.summary}</p>
          {plan.planner_warning ? <p className="text-sm text-amber-200">{plan.planner_warning}</p> : null}
          {plan.blocked_reasons.length ? <WarningList title="Blocked reasons" items={plan.blocked_reasons} danger /> : null}
          {plan.warnings.length ? <WarningList title="Warnings" items={plan.warnings} /> : null}
          {operationGroups ? (
            <div className="grid gap-3 md:grid-cols-2">
              <OperationGroup title="Folders to create" operations={operationGroups.create_folder} rootPath={plan.root_path} />
              <OperationGroup title="Files to move" operations={operationGroups.move_file} rootPath={plan.root_path} />
              <OperationGroup title="Files to copy" operations={operationGroups.copy_file} rootPath={plan.root_path} />
              <OperationGroup title="Files to rename" operations={operationGroups.rename_file} rootPath={plan.root_path} />
            </div>
          ) : null}
          {plan.skipped.length ? (
            <div>
              <p className="text-xs uppercase text-app-muted">Skipped</p>
              <div className="mt-2 max-h-40 overflow-auto rounded-md border border-app-border bg-zinc-900/60 p-3 text-xs leading-5 text-app-muted">
                {plan.skipped.slice(0, 40).map((item) => (
                  <p key={`${item.path}:${item.reason}`}>{relativeDisplay(item.path, plan.root_path)} - {item.reason}</p>
                ))}
              </div>
            </div>
          ) : null}
          <div className="flex flex-wrap gap-3">
            <Button variant="primary" onClick={() => void handleExecute()} loading={loading === "execute"} disabled={!canExecute}>
              Confirm Execute
            </Button>
            <Button variant="secondary" onClick={() => setPlan(null)}>
              Cancel
            </Button>
            <Button variant="secondary" onClick={() => void handlePrepare()} loading={loading === "prepare"} disabled={!rootPath.trim()}>
              Refresh Validation
            </Button>
          </div>
        </div>
      ) : null}

      {result ? (
        <div className="rounded-md border border-app-border bg-zinc-950 p-4 text-sm">
          <div className="flex flex-wrap gap-2">
            <Badge variant={result.status === "completed" ? "success" : result.status === "failed" ? "danger" : "warning"}>{result.status}</Badge>
            <Badge>created {result.created_folders}</Badge>
            <Badge>moved {result.moved_files}</Badge>
            <Badge>copied {result.copied_files}</Badge>
            <Badge>renamed {result.renamed_files}</Badge>
            {result.undo_available ? <Badge variant="info">undo available</Badge> : null}
          </div>
          {result.errors.length ? <WarningList title="Execution errors" items={result.errors} danger /> : null}
          {result.undo_available ? (
            <div className="mt-3">
              <Button variant="secondary" onClick={() => void handleUndo()} loading={loading === "undo"}>
                Undo
              </Button>
            </div>
          ) : null}
        </div>
      ) : null}

      {undoResult ? (
        <div className="rounded-md border border-app-border bg-zinc-950 p-4 text-sm">
          <div className="flex flex-wrap gap-2">
            <Badge variant={undoResult.status === "undone" ? "success" : "warning"}>{undoResult.status}</Badge>
            <Badge>{undoResult.undone_operations} undone</Badge>
          </div>
          {undoResult.errors.length ? <WarningList title="Undo errors" items={undoResult.errors} danger /> : null}
        </div>
      ) : null}
    </Card>
  );
}

function groupFileOperations(operations: FileOperation[]) {
  return {
    create_folder: operations.filter((operation) => operation.type === "create_folder"),
    move_file: operations.filter((operation) => operation.type === "move_file"),
    copy_file: operations.filter((operation) => operation.type === "copy_file"),
    rename_file: operations.filter((operation) => operation.type === "rename_file"),
  };
}

function OperationGroup({ title, operations, rootPath }: { title: string; operations: FileOperation[]; rootPath: string }) {
  return (
    <div className="rounded-md border border-app-border bg-zinc-900/60 p-3">
      <p className="text-xs uppercase text-app-muted">{title}</p>
      {operations.length === 0 ? (
        <p className="mt-2 text-sm text-app-muted">None</p>
      ) : (
        <div className="mt-2 max-h-48 space-y-2 overflow-auto text-xs leading-5 text-app-text">
          {operations.map((operation, index) => (
            <div key={`${operation.type}:${operation.path ?? operation.from_path}:${operation.to_path}:${index}`}>
              <p>{relativeDisplay(operation.path ?? operation.from_path ?? "", rootPath)}</p>
              {operation.to_path ? <p className="text-app-muted">→ {relativeDisplay(operation.to_path, rootPath)}</p> : null}
              {operation.reason ? <p className="text-app-muted">{operation.reason}</p> : null}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function WarningList({ title, items, danger = false }: { title: string; items: string[]; danger?: boolean }) {
  return (
    <div className={`mt-3 rounded-md border px-3 py-2 text-sm ${danger ? "border-red-500/30 bg-red-500/10 text-red-100" : "border-amber-500/30 bg-amber-500/10 text-amber-100"}`}>
      <p className="font-medium">{title}</p>
      <ul className="mt-1 list-disc space-y-1 pl-5">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function relativeDisplay(path: string, rootPath: string) {
  if (!path) return "";
  return path.startsWith(rootPath) ? path.slice(rootPath.length).replace(/^[/\\]+/, "") || "." : path;
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
      <PlannerMeta task={task} />
      <TaskPreviewDetails taskType={task.task_type} preview={task.preview} sourcesUsed={task.sources_used} compact />
      <div className="mt-3 flex items-center gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
        <AlertTriangle size={16} />
        <span>Review the details before confirming. Current execution is mock-only.</span>
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
          <PlannerMeta task={task} />
          <TaskPreviewDetails taskType={task.task_type} preview={task.preview} sourcesUsed={task.sources_used} />
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
          <PlannerMeta task={task} />
          <TaskPreviewDetails taskType={task.task_type} preview={task.preview} result={task.result} sourcesUsed={task.sources_used} />
        </div>
      </div>
    </Card>
  );
}

function PlannerMeta({ task }: { task: Pick<TaskResponse, "planner_model" | "planner_provider" | "planner_warning"> }) {
  if (!task.planner_model && !task.planner_warning) {
    return null;
  }
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      {task.planner_model ? <Badge variant="info">Planned by {task.planner_model}</Badge> : null}
      {task.planner_provider ? <Badge>{task.planner_provider}</Badge> : null}
      {task.planner_warning ? <span className="text-xs text-amber-200">{task.planner_warning}</span> : null}
    </div>
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
  const [expanded, setExpanded] = useState(false);
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
            <Button
              className="h-8 px-3"
              variant="secondary"
              onClick={() => {
                setExpanded((value) => !value);
                onReview();
              }}
            >
              Review & Confirm
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
      {isPending && expanded ? (
        <div className="mt-4 rounded-md border border-app-border bg-zinc-900/60 p-3">
          <TaskPreviewDetails taskType={task.task_type} preview={task.preview} sourcesUsed={task.sources_used} compact />
          <div className="mt-4 flex gap-2">
            <Button className="h-8 px-3" variant="primary" onClick={onConfirm} disabled={!task.confirmation_token}>
              Confirm
            </Button>
            <Button className="h-8 px-3" variant="secondary" onClick={onCancel}>
              Cancel
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function taskApiErrorDetails(error: unknown): Record<string, unknown> {
  if (typeof error === "object" && error !== null && "response" in error) {
    const response = (error as { response?: { status?: number; data?: unknown } }).response;
    return {
      endpoint: "/tasks/execute",
      status: response?.status ?? null,
      detail: response?.data ?? null,
    };
  }
  if (typeof error === "object" && error !== null && "request" in error) {
    return {
      endpoint: "/tasks/execute",
      status: null,
      detail: "No response received from backend.",
    };
  }
  return {
    endpoint: "/tasks/execute",
    status: null,
    detail: error instanceof Error ? error.message : "Unknown error",
  };
}

function formatTimestamp(value: string) {
  return new Date(value).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
