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
        {!isUser && message.answerStyle ? <AnswerStyleBadge message={message} /> : null}

        {isUser ? <p className="whitespace-pre-wrap">{message.content}</p> : <MarkdownText text={message.content} />}

        {!isUser && (message.model || message.searchMode) ? (
          <p className="mt-3 text-xs text-app-muted">
            {message.modelDisplayName ?? message.model}
            {message.model && message.searchMode ? " - " : null}
            {message.searchMode ? `${message.searchMode} memory` : null}
          </p>
        ) : null}

        {!isUser && message.warning ? (
          <div className="mt-3 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
            {message.warning}
          </div>
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
                {contextStats.warnings && contextStats.warnings.length > 0 ? (
                  <p className="text-xs leading-5 text-amber-200">{contextStats.warnings.join("; ")}</p>
                ) : null}
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
      {source.relationship_reason ? (
        <p className="mt-1 text-xs leading-5 text-app-muted">
          {source.relationship_type}: {source.relationship_reason}
        </p>
      ) : null}
      {source.content_preview ? <p className="mt-2 text-xs leading-5 text-app-muted">{source.content_preview}</p> : null}
    </div>
  );
}

function AnswerStyleBadge({ message }: { message: ChatMessageRecord }) {
  if (message.taskHint) {
    return <Badge variant="warning">Task detected</Badge>;
  }
  if (message.answerStyle === "root_cause") {
    return <Badge variant="info">Root-cause analysis</Badge>;
  }
  if (message.answerStyle === "summary") {
    return <Badge variant="info">Summary</Badge>;
  }
  return null;
}

function MarkdownText({ text }: { text: string }) {
  const lines = text.split("\n");
  return (
    <div className="space-y-2">
      {lines.map((line, index) => {
        const trimmed = line.trim();
        if (!trimmed) {
          return <div key={index} className="h-1" />;
        }
        if (trimmed.startsWith("## ")) {
          return (
            <h3 key={index} className="pt-2 text-base font-semibold text-app-text">
              {trimmed.slice(3)}
            </h3>
          );
        }
        if (trimmed.startsWith("# ")) {
          return (
            <h2 key={index} className="pt-2 text-lg font-semibold text-app-text">
              {trimmed.slice(2)}
            </h2>
          );
        }
        if (trimmed.startsWith("- ")) {
          return (
            <p key={index} className="pl-4 text-sm leading-6 text-app-text">
              <span className="mr-2 text-app-muted">-</span>
              {trimmed.slice(2)}
            </p>
          );
        }
        if (/^\d+\.\s/.test(trimmed)) {
          return (
            <p key={index} className="pl-4 text-sm leading-6 text-app-text">
              {trimmed}
            </p>
          );
        }
        return (
          <p key={index} className="whitespace-pre-wrap text-sm leading-6 text-app-text">
            {trimmed}
          </p>
        );
      })}
    </div>
  );
}
