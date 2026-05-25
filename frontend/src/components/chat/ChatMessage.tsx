import { useState } from "react";

import type { ChatMessage as ChatMessageRecord, ChatSource } from "../../types";
import { Badge } from "../shared/Badge";
import { Button } from "../shared/Button";

type ChatMessageProps = {
  message: ChatMessageRecord;
  onOpenTask?: (instruction: string) => void;
};

export function ChatMessage({ message, onOpenTask }: ChatMessageProps) {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [contextOpen, setContextOpen] = useState(false);
  const isUser = message.role === "user";
  const sources = message.sourcesUsed ?? [];
  const contextStats = message.contextStats;

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <article
        className={[
          "max-w-[78%] rounded-2xl px-4 py-3 text-sm leading-6 shadow-sm",
          isUser
            ? "rounded-br-md bg-app-primary text-white"
            : "rounded-bl-md border border-app-border bg-app-panel text-app-text",
        ].join(" ")}
      >
        <p className="whitespace-pre-wrap">{message.content}</p>

        {!isUser && (message.model || message.searchMode) ? (
          <p className="mt-3 text-xs text-app-muted">
            {message.model}
            {message.model && message.searchMode ? " - " : null}
            {message.searchMode ? `${message.searchMode} memory` : null}
          </p>
        ) : null}

        {!isUser && message.taskHint ? (
          <div className="mt-3 rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-amber-100">
            <p className="text-xs font-medium">This looks like a task: {message.taskHint}</p>
            <Button className="mt-3 h-8 px-3" variant="secondary" onClick={() => onOpenTask?.(message.taskInstruction ?? message.content)}>
              Prepare in Tasks
            </Button>
          </div>
        ) : null}

        {!isUser && sources.length > 0 ? (
          <div className="mt-3">
            <button
              type="button"
              onClick={() => setSourcesOpen((open) => !open)}
              className="text-xs font-medium text-violet-300 hover:text-violet-200"
            >
              Sources used ({sources.length})
            </button>
            {sourcesOpen ? (
              <div className="mt-3 space-y-2">
                {sources.map((source) => (
                  <SourceCard key={source.event_id} source={source} />
                ))}
              </div>
            ) : null}
          </div>
        ) : null}

        {!isUser && contextStats ? (
          <div className="mt-3 border-t border-app-border pt-3">
            <button
              type="button"
              onClick={() => setContextOpen((open) => !open)}
              className="text-xs font-medium text-violet-300 hover:text-violet-200"
            >
              Context used
            </button>
            {contextOpen ? (
              <div className="mt-3 space-y-2 rounded-md border border-app-border bg-zinc-950 p-3">
                <div className="flex flex-wrap gap-2">
                  <Badge variant="info">direct {contextStats.direct_count}</Badge>
                  <Badge variant="info">related {contextStats.related_count}</Badge>
                  <Badge>relationships {contextStats.relationship_count}</Badge>
                  <Badge>tokens ~{contextStats.token_estimate}</Badge>
                </div>
                {contextStats.sources.length > 0 ? (
                  <p className="text-xs leading-5 text-app-muted">Sources: {contextStats.sources.join(", ")}</p>
                ) : null}
                {message.contextSummary ? <p className="text-xs leading-5 text-app-muted">{message.contextSummary}</p> : null}
              </div>
            ) : null}
          </div>
        ) : null}

        <time className={`mt-2 block text-xs ${isUser ? "text-violet-100/80" : "text-app-muted"}`}>
          {new Date(message.timestamp).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </time>
      </article>
    </div>
  );
}

function SourceCard({ source }: { source: ChatSource }) {
  return (
    <div className="rounded-md border border-app-border bg-zinc-950 p-3">
      <div className="flex items-center gap-2">
        <Badge variant={source.source_kind === "related" ? "default" : "info"}>{source.source_kind ?? "direct"}</Badge>
        <Badge variant="info">{source.source}</Badge>
        <Badge>{source.type}</Badge>
        <Badge variant="success">score {source.score.toFixed(2)}</Badge>
      </div>
      <h4 className="mt-2 text-xs font-semibold text-app-text">{source.title}</h4>
      <p className="mt-1 text-xs leading-5 text-app-muted">{source.match_reason}</p>
      {source.content_preview ? <p className="mt-2 text-xs leading-5 text-app-muted">{source.content_preview}</p> : null}
    </div>
  );
}
