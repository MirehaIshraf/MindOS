import { AlertTriangle, CheckCircle, Circle, Clock, Play, Plus, RotateCcw, Trash2, Workflow, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Badge } from "../components/shared/Badge";
import { Button } from "../components/shared/Button";
import { Card } from "../components/shared/Card";
import { EmptyState } from "../components/shared/EmptyState";
import {
  checkPlaybookDeps,
  deletePlaybook,
  getErrorMessage,
  getPlaybooks,
  runPlaybook,
  savePlaybook,
  startRecording,
  stopRecording,
} from "../services/api";
import type { Playbook, PlaybookRunResponse, PlaybookRunStepLog, SkillStep } from "../types";

// ---------------------------------------------------------------------------
// Types for local UI state
// ---------------------------------------------------------------------------

type View = "list" | "record" | "preview" | "running";

type RecordState = "idle" | "starting" | "recording" | "processing";

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

const ACTION_ICON: Record<string, string> = {
  navigate_url: "🌐",
  open_app: "🚀",
  type: "⌨️",
  hotkey: "⌨️",
  click: "🖱️",
  key: "⌨️",
  scroll: "↕️",
  close_window: "✖️",
  switch_window: "⇄",
};

function StepBadge({ step }: { step: SkillStep }) {
  const icon = ACTION_ICON[step.action] ?? "•";
  const primary = step.description || `${step.action} in ${step.app_name || "unknown app"}`;
  const secondary = [step.app_name, step.url || step.text || step.element_name].filter(Boolean).join(" · ");

  return (
    <div className="flex items-start gap-3 rounded-md border border-app-border bg-zinc-900 p-3">
      <span className="mt-0.5 flex-none text-base leading-none">{icon}</span>
      <div className="min-w-0 flex-1">
        <p className="text-sm text-app-text">{primary}</p>
        {secondary && <p className="mt-0.5 text-xs text-app-muted">{secondary}</p>}
      </div>
      <div className="flex flex-none gap-1">
        {step.is_destructive && <Badge variant="danger">destructive</Badge>}
        {step.requires_confirmation && <Badge variant="warning">confirm</Badge>}
      </div>
    </div>
  );
}

function RunStepRow({ log }: { log: PlaybookRunStepLog }) {
  const icon =
    log.status === "ok" ? <CheckCircle size={14} className="text-emerald-400" /> :
    log.status === "failed" ? <XCircle size={14} className="text-red-400" /> :
    log.status === "paused" ? <AlertTriangle size={14} className="text-amber-400" /> :
    <Circle size={14} className="text-app-muted" />;

  const stepIcon = ACTION_ICON[log.action] ?? "•";
  return (
    <div className="flex items-start gap-3 py-2">
      <div className="mt-0.5 flex-none">{icon}</div>
      <div className="min-w-0 flex-1">
        <p className="text-sm text-app-text">
          <span className="mr-1.5">{stepIcon}</span>
          {log.description || log.action}
        </p>
        {log.message ? <p className="mt-0.5 text-xs text-app-muted">{log.message}</p> : null}
      </div>
      <Badge variant={log.status === "ok" ? "success" : log.status === "paused" ? "warning" : log.status === "failed" ? "danger" : "default"}>
        {log.status}
      </Badge>
    </div>
  );
}

function PlaybookCard({
  playbook,
  onRun,
  onDelete,
}: {
  playbook: Playbook;
  onRun: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  return (
    <div className="rounded-lg border border-app-border bg-app-panel p-5 flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="font-semibold text-app-text truncate">{playbook.name}</h3>
          {playbook.description ? (
            <p className="mt-1 text-xs text-app-muted line-clamp-2">{playbook.description}</p>
          ) : null}
        </div>
        <Workflow size={18} className="flex-none text-violet-400 mt-0.5" />
      </div>

      <div className="flex items-center gap-3 text-xs text-app-muted">
        <span>{playbook.steps.length} steps</span>
        <span>·</span>
        <span>{playbook.run_count} run{playbook.run_count !== 1 ? "s" : ""}</span>
        {playbook.last_run_at ? (
          <>
            <span>·</span>
            <span className="flex items-center gap-1">
              <Clock size={11} />
              {new Date(playbook.last_run_at).toLocaleDateString()}
            </span>
          </>
        ) : null}
      </div>

      <div className="flex gap-2 pt-1">
        <Button variant="primary" className="flex-1 h-8 text-xs" onClick={() => onRun(playbook.id)}>
          <Play size={12} /> Run
        </Button>
        <Button
          variant="ghost"
          className="h-8 w-8 p-0"
          onClick={() => onDelete(playbook.id)}
          title="Delete playbook"
        >
          <Trash2 size={13} className="text-red-400" />
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function PlaybooksPage() {
  const [view, setView] = useState<View>("list");
  const [playbooks, setPlaybooks] = useState<Playbook[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Record flow
  const [recordState, setRecordState] = useState<RecordState>("idle");
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [recordError, setRecordError] = useState<string | null>(null);
  const [depsStatus, setDepsStatus] = useState<{ pynput_available: boolean; pywinauto_available: boolean; pillow_available: boolean } | null>(null);

  // Preview (captured steps before saving)
  const [previewSteps, setPreviewSteps] = useState<SkillStep[]>([]);
  const [saving, setSaving] = useState(false);

  // Run flow
  const [runResult, setRunResult] = useState<PlaybookRunResponse | null>(null);
  const [runningId, setRunningId] = useState<string | null>(null);
  const [runningName, setRunningName] = useState("");
  const [runLoading, setRunLoading] = useState(false);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ------------------------------------------------------------------
  // Load playbooks
  // ------------------------------------------------------------------

  async function loadPlaybooks() {
    try {
      setLoading(true);
      setError(null);
      const data = await getPlaybooks();
      setPlaybooks(data.playbooks);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadPlaybooks();
  }, []);

  // ------------------------------------------------------------------
  // Recording flow
  // ------------------------------------------------------------------

  async function openRecordPanel() {
    setNewName("");
    setNewDescription("");
    setRecordError(null);
    setRecordState("idle");
    setDepsStatus(null);
    setView("record");
    try {
      const deps = await checkPlaybookDeps();
      setDepsStatus(deps);
    } catch {
      // not critical — just won't show the deps warning
    }
  }

  async function handleStartRecording() {
    if (!newName.trim()) {
      setRecordError("Playbook name is required.");
      return;
    }
    setRecordError(null);
    setRecordState("starting");
    try {
      await startRecording();
      setRecordState("recording");
    } catch (err) {
      setRecordState("idle");
      setRecordError(getErrorMessage(err));
    }
  }

  async function handleStopRecording() {
    setRecordState("processing");
    try {
      const result = await stopRecording();
      setPreviewSteps(result.steps);
      setView("preview");
    } catch (err) {
      setRecordError(getErrorMessage(err));
      setRecordState("idle");
    }
  }

  // ------------------------------------------------------------------
  // Save playbook
  // ------------------------------------------------------------------

  async function handleSave() {
    setSaving(true);
    try {
      await savePlaybook({
        name: newName.trim(),
        description: newDescription.trim(),
        steps: previewSteps,
      });
      await loadPlaybooks();
      setView("list");
    } catch (err) {
      setRecordError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  // ------------------------------------------------------------------
  // Run playbook
  // ------------------------------------------------------------------

  async function handleRun(id: string) {
    const pb = playbooks.find((p) => p.id === id);
    setRunningId(id);
    setRunningName(pb?.name ?? "Playbook");
    setRunResult(null);
    setRunLoading(true);
    setView("running");
    try {
      const result = await runPlaybook(id);
      setRunResult(result);
    } catch (err) {
      setRunResult({
        playbook_id: id,
        status: "failed",
        steps_total: 0,
        steps_completed: 0,
        steps_failed: 1,
        log: [{ step_index: -1, action: "", description: getErrorMessage(err), status: "failed", message: "" }],
      });
    } finally {
      setRunLoading(false);
    }
  }

  async function handleConfirmStep(stepIndex: number) {
    if (!runningId) return;
    setRunLoading(true);
    try {
      const continuation = await runPlaybook(runningId, stepIndex);
      // Merge: keep previous completed/failed entries, replace the paused entry
      // with the actual results from the continuation run.
      setRunResult((prev) => {
        const previousLog = prev ? prev.log.filter((l) => l.status !== "paused") : [];
        return {
          ...continuation,
          steps_completed: (prev?.steps_completed ?? 0) + continuation.steps_completed,
          steps_failed: (prev?.steps_failed ?? 0) + continuation.steps_failed,
          log: [...previousLog, ...continuation.log],
        };
      });
    } catch (err) {
      setRunResult((prev) =>
        prev
          ? {
              ...prev,
              status: "failed",
              log: [
                ...prev.log.filter((l) => l.status !== "paused"),
                { step_index: stepIndex, action: "", description: getErrorMessage(err), status: "failed" as const, message: "" },
              ],
            }
          : null
      );
    } finally {
      setRunLoading(false);
    }
  }

  // ------------------------------------------------------------------
  // Delete
  // ------------------------------------------------------------------

  async function handleDelete(id: string) {
    try {
      await deletePlaybook(id);
      setPlaybooks((prev) => prev.filter((p) => p.id !== id));
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  // ------------------------------------------------------------------
  // Render helpers
  // ------------------------------------------------------------------

  function backToList() {
    setView("list");
    setRunResult(null);
    setRunningId(null);
  }

  // ------------------------------------------------------------------
  // Views
  // ------------------------------------------------------------------

  if (view === "record") {
    return (
      <Card>
        <div className="mb-6 flex items-center gap-3">
          <button onClick={backToList} className="text-app-muted hover:text-app-text text-sm">← Back</button>
          <h2 className="text-lg font-semibold text-app-text">New Playbook</h2>
        </div>

        <div className="max-w-lg space-y-4">
          <div>
            <label className="block text-sm font-medium text-app-text mb-1">Name</label>
            <input
              type="text"
              className="w-full rounded-md border border-app-border bg-zinc-900 px-3 py-2 text-sm text-app-text placeholder:text-app-muted focus:outline-none focus:ring-1 focus:ring-violet-500"
              placeholder="e.g. Export monthly report"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              disabled={recordState !== "idle"}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-app-text mb-1">Description (optional)</label>
            <input
              type="text"
              className="w-full rounded-md border border-app-border bg-zinc-900 px-3 py-2 text-sm text-app-text placeholder:text-app-muted focus:outline-none focus:ring-1 focus:ring-violet-500"
              placeholder="What does this playbook do?"
              value={newDescription}
              onChange={(e) => setNewDescription(e.target.value)}
              disabled={recordState !== "idle"}
            />
          </div>

          {depsStatus && !depsStatus.pynput_available && (
            <div className="rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-300 space-y-1">
              <p className="font-medium">Missing dependency: pynput</p>
              <p className="text-amber-200/70">Run in your backend venv: <code className="font-mono">pip install pynput pywinauto pillow pyautogui psutil</code></p>
              <p className="text-amber-200/70">Then restart the backend server.</p>
            </div>
          )}

          {recordError ? (
            <p className="text-sm text-red-400">{recordError}</p>
          ) : null}

          {recordState === "idle" && (
            <Button variant="primary" onClick={handleStartRecording}>
              <Circle size={12} className="fill-red-400 text-red-400" /> Start Recording
            </Button>
          )}

          {recordState === "starting" && (
            <div className="flex items-center gap-2 text-sm text-app-muted">
              <RotateCcw size={14} className="animate-spin" /> Starting recorder…
            </div>
          )}

          {recordState === "recording" && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 rounded-md border border-red-500/30 bg-red-500/10 px-4 py-3">
                <span className="relative flex h-2.5 w-2.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-400 opacity-75" />
                  <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-red-500" />
                </span>
                <span className="text-sm font-medium text-red-300">Recording… perform your task now</span>
              </div>
              <p className="text-xs text-app-muted">
                Switch to any app and perform the steps. Come back here when done.
              </p>
              <Button variant="secondary" onClick={handleStopRecording}>
                Stop Recording
              </Button>
            </div>
          )}

          {recordState === "processing" && (
            <div className="flex items-center gap-2 text-sm text-app-muted">
              <RotateCcw size={14} className="animate-spin" /> Analyzing captured steps…
            </div>
          )}
        </div>
      </Card>
    );
  }

  if (view === "preview") {
    return (
      <Card>
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button onClick={() => setView("record")} className="text-app-muted hover:text-app-text text-sm">← Re-record</button>
            <h2 className="text-lg font-semibold text-app-text">Review Captured Steps</h2>
          </div>
          <Badge variant="info">{previewSteps.length} steps</Badge>
        </div>

        {previewSteps.length === 0 ? (
          <p className="text-sm text-app-muted">No actions were captured. Try recording again.</p>
        ) : (
          <div className="space-y-2 max-h-[480px] overflow-y-auto pr-1">
            {previewSteps.map((step) => (
              <StepBadge key={step.step_index} step={step} />
            ))}
          </div>
        )}

        {recordError ? <p className="mt-4 text-sm text-red-400">{recordError}</p> : null}

        <div className="mt-6 flex gap-3">
          <Button
            variant="primary"
            loading={saving}
            disabled={previewSteps.length === 0}
            onClick={handleSave}
          >
            Save Playbook
          </Button>
          <Button variant="ghost" onClick={backToList}>
            Discard
          </Button>
        </div>
      </Card>
    );
  }

  if (view === "running") {
    const pausedStep = runResult?.status === "paused" ? runResult.log.find((l) => l.status === "paused") : null;

    return (
      <Card>
        <div className="mb-6 flex items-center gap-3">
          <button onClick={backToList} className="text-app-muted hover:text-app-text text-sm">← Back</button>
          <h2 className="text-lg font-semibold text-app-text">Running: {runningName}</h2>
          {runResult && (
            <Badge variant={runResult.status === "completed" ? "success" : runResult.status === "paused" ? "warning" : "danger"}>
              {runResult.status}
            </Badge>
          )}
        </div>

        {runLoading && !runResult && (
          <div className="flex items-center gap-2 text-sm text-app-muted">
            <RotateCcw size={14} className="animate-spin" /> Executing steps…
          </div>
        )}

        {runResult && (
          <>
            <div className="flex gap-4 mb-4 text-sm">
              <span className="text-emerald-400">{runResult.steps_completed} completed</span>
              {runResult.steps_failed > 0 && <span className="text-red-400">{runResult.steps_failed} failed</span>}
              <span className="text-app-muted">{runResult.steps_total} total</span>
            </div>

            <div className="space-y-1 divide-y divide-app-border max-h-[400px] overflow-y-auto">
              {runResult.log.map((entry, i) => (
                <RunStepRow key={i} log={entry} />
              ))}
            </div>

            {pausedStep && (
              <div className="mt-6 rounded-md border border-amber-500/30 bg-amber-500/10 p-4 space-y-3">
                <p className="text-sm font-medium text-amber-300">
                  Confirmation required before step {pausedStep.step_index + 1}
                </p>
                <p className="text-xs text-app-muted">{pausedStep.description}</p>
                <div className="flex gap-2">
                  <Button variant="primary" loading={runLoading} onClick={() => handleConfirmStep(pausedStep.step_index)}>
                    Confirm & Continue
                  </Button>
                  <Button variant="ghost" onClick={backToList}>Cancel</Button>
                </div>
              </div>
            )}

            {runResult.status !== "paused" && (
              <div className="mt-6 flex gap-3">
                <Button variant="secondary" onClick={backToList}>Back to Playbooks</Button>
                {runResult.status === "failed" && runningId && (
                  <Button variant="ghost" onClick={() => handleRun(runningId)}>
                    <RotateCcw size={13} /> Retry
                  </Button>
                )}
              </div>
            )}
          </>
        )}
      </Card>
    );
  }

  // ------------------------------------------------------------------
  // List view (default)
  // ------------------------------------------------------------------

  return (
    <Card>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-app-text">Playbooks</h2>
          <p className="mt-0.5 text-sm text-app-muted">Record multi-app tasks and replay them securely.</p>
        </div>
        <Button variant="primary" onClick={openRecordPanel}>
          <Plus size={14} /> New Playbook
        </Button>
      </div>

      {error ? (
        <p className="text-sm text-red-400 mb-4">{error}</p>
      ) : null}

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-app-muted py-8">
          <RotateCcw size={14} className="animate-spin" /> Loading…
        </div>
      ) : playbooks.length === 0 ? (
        <EmptyState
          icon={<Workflow size={36} />}
          title="No Playbooks Yet"
          description="Record yourself performing a task and MindOS will learn how to replicate it securely."
          action={
            <Button variant="primary" onClick={openRecordPanel}>
              <Plus size={14} /> Record your first playbook
            </Button>
          }
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {playbooks.map((pb) => (
            <PlaybookCard
              key={pb.id}
              playbook={pb}
              onRun={handleRun}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}
    </Card>
  );
}
