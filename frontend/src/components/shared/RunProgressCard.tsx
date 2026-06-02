import { XCircle } from "lucide-react";

import { Badge } from "./Badge";
import { Button } from "./Button";

type RunProgressCardProps = {
  title?: string;
  message?: string | null;
  step?: string | null;
  elapsedSeconds?: number | null;
  status: string;
  progressPercent?: number | null;
  onCancel?: () => void;
};

export function RunProgressCard({
  title = "MindOS is working",
  message,
  step,
  elapsedSeconds,
  status,
  progressPercent,
  onCancel,
}: RunProgressCardProps) {
  const displayMessage = message || fallbackMessage(status);
  return (
    <div className="flex justify-start">
      <article className="w-full max-w-[520px] rounded-md border border-app-border bg-app-panel px-4 py-3 text-sm text-app-text shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-app-primary" aria-hidden="true" />
              <h3 className="font-medium">{title}</h3>
            </div>
            <p className="mt-2 text-app-muted">{displayMessage}</p>
          </div>
          {onCancel ? (
            <Button type="button" variant="ghost" className="h-8 px-2" onClick={onCancel} title="Cancel response">
              <XCircle size={16} />
            </Button>
          ) : null}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-app-muted">
          {step ? <Badge>{formatStep(step)}</Badge> : null}
          {typeof elapsedSeconds === "number" ? <span>Elapsed: {formatElapsed(elapsedSeconds)}</span> : null}
          {typeof progressPercent === "number" ? <span>{Math.max(0, Math.min(100, progressPercent))}%</span> : null}
        </div>
        {typeof progressPercent === "number" ? (
          <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-zinc-800">
            <div
              className="h-full rounded-full bg-app-primary transition-all"
              style={{ width: `${Math.max(0, Math.min(100, progressPercent))}%` }}
            />
          </div>
        ) : null}
      </article>
    </div>
  );
}

function fallbackMessage(status: string) {
  if (status === "queued") {
    return "Queued...";
  }
  if (status === "failed") {
    return "The response failed.";
  }
  return "MindOS is working...";
}

function formatStep(step: string) {
  return step.replace(/_/g, " ");
}

function formatElapsed(seconds: number) {
  if (seconds < 60) {
    return `${seconds}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}m ${remainder}s`;
}
