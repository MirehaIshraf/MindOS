import { Bot, XCircle } from "lucide-react";

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
  title = "MindOS is thinking",
  message,
  step,
  elapsedSeconds,
  status,
  progressPercent,
  onCancel,
}: RunProgressCardProps) {
  const displayMessage = message || fallbackMessage(status);
  return (
    <div className="flex items-start gap-3">
      <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-app-primary/15 text-app-primary">
        <Bot size={16} />
      </div>
      <article className="w-full max-w-[520px] rounded-2xl rounded-bl-md border border-app-border bg-app-panel px-4 py-3 text-sm text-app-text shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-medium">{title}</span>
              <TypingDots />
            </div>
            <p className="mt-1.5 text-app-muted">{displayMessage}</p>
          </div>
          {onCancel ? (
            <Button type="button" variant="ghost" className="h-8 px-2" onClick={onCancel} title="Cancel response">
              <XCircle size={16} />
            </Button>
          ) : null}
        </div>
        {typeof progressPercent === "number" ? (
          <div className="mt-3 h-1 overflow-hidden rounded-full bg-app-elevated">
            <div
              className="h-full rounded-full bg-app-primary transition-all"
              style={{ width: `${Math.max(0, Math.min(100, progressPercent))}%` }}
            />
          </div>
        ) : null}
        {step || typeof elapsedSeconds === "number" ? (
          <p className="mt-2 text-xs text-app-muted">
            {step ? formatStep(step) : null}
            {step && typeof elapsedSeconds === "number" ? " · " : null}
            {typeof elapsedSeconds === "number" ? formatElapsed(elapsedSeconds) : null}
          </p>
        ) : null}
      </article>
    </div>
  );
}

function TypingDots() {
  return (
    <span className="flex items-center gap-1" aria-hidden="true">
      {[0, 0.15, 0.3].map((delay) => (
        <span
          key={delay}
          className="mindos-typing-dot h-1.5 w-1.5 rounded-full bg-app-primary"
          style={{ animationDelay: `${delay}s` }}
        />
      ))}
    </span>
  );
}

function fallbackMessage(status: string) {
  if (status === "queued") {
    return "Queued...";
  }
  if (status === "failed") {
    return "The response failed.";
  }
  return "Working on your request...";
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
