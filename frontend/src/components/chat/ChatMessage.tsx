import { Bot, Check, X } from "lucide-react";
import { useState, type ReactNode } from "react";

import type { ChatMessage as ChatMessageRecord, ChatSource } from "../../types";
import { Badge } from "../shared/Badge";
import { Button } from "../shared/Button";
import { useTypingReveal } from "./useTypingReveal";

type ChatMessageProps = {
  message: ChatMessageRecord;
  animate?: boolean;
  isLast?: boolean;
  onContentGrow?: () => void;
  onConfirm?: () => void;
  onCancel?: () => void;
};

export function ChatMessage({ message, animate = false, isLast = false, onContentGrow, onConfirm, onCancel }: ChatMessageProps) {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [contextOpen, setContextOpen] = useState(false);
  const isUser = message.role === "user";
  const sources = message.sourcesUsed ?? [];
  const contextStats = message.contextStats;
  const { displayText, done } = useTypingReveal(message.content, !isUser && animate, onContentGrow);

  return (
    <div className={`flex items-start gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser ? (
        <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-app-primary/15 text-app-primary">
          <Bot size={16} />
        </div>
      ) : null}
      <article
        className={[
          "max-w-[78%] rounded-2xl px-4 py-3 text-sm leading-6 shadow-sm",
          isUser
            ? "rounded-br-md bg-app-primary text-white"
            : "rounded-bl-md border border-app-border bg-app-panel text-app-text",
        ].join(" ")}
      >
        {!isUser && message.answerStyle && done ? <AnswerStyleBadge message={message} /> : null}

        {isUser ? <p className="whitespace-pre-wrap">{message.content}</p> : <MarkdownText text={displayText} />}

        {done && !isUser && (message.model || message.searchMode) ? (
          <p className="mt-3 text-xs text-app-muted">
            {message.modelDisplayName ?? message.model}
            {message.model && message.searchMode ? " - " : null}
            {message.searchMode ? `${message.searchMode} memory` : null}
          </p>
        ) : null}

        {done && !isUser && message.warning ? (
          <div className="mt-3 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
            {message.warning}
          </div>
        ) : null}

        {done && !isUser && message.requiresConfirmation && isLast ? (
          <div className="mt-4 flex items-center gap-2">
            <Button className="h-9 px-4" variant="primary" onClick={() => onConfirm?.()}>
              <Check size={16} />
              Confirm
            </Button>
            <Button className="h-9 px-4" variant="secondary" onClick={() => onCancel?.()}>
              <X size={16} />
              Cancel
            </Button>
          </div>
        ) : null}

        {done && !isUser && sources.length > 0 ? (
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

        {done && !isUser && contextStats ? (
          <div className="mt-3 border-t border-app-border pt-3">
            <button
              type="button"
              onClick={() => setContextOpen((open) => !open)}
              className="text-xs font-medium text-violet-300 hover:text-violet-200"
            >
              Context used
            </button>
            {contextOpen ? (
              <div className="mt-3 space-y-2 rounded-md border border-app-border bg-app-inset p-3">
                <div className="flex flex-wrap gap-2">
                  <Badge variant="info">direct {contextStats.direct_count}</Badge>
                  <Badge variant="info">related {contextStats.related_count}</Badge>
                  <Badge>relationships {contextStats.relationship_count}</Badge>
                  <Badge>tokens ~{contextStats.token_estimate}</Badge>
                </div>
                {contextStats.sources.length > 0 ? (
                  <p className="text-xs leading-5 text-app-muted">Sources: {contextStats.sources.join(", ")}</p>
                ) : null}
                {contextStats.intent ? (
                  <div className="flex flex-wrap gap-2">
                    <Badge>intent: {contextStats.intent}</Badge>
                    {contextStats.retrieval_profile ? <Badge>profile: {contextStats.retrieval_profile}</Badge> : null}
                    {contextStats.is_follow_up ? <Badge variant="info">follow-up</Badge> : null}
                  </div>
                ) : null}
                {contextStats.resolved_query ? (
                  <p className="text-xs leading-5 text-app-muted">Resolved query: {contextStats.resolved_query}</p>
                ) : null}
                {contextStats.primary_source_title ? (
                  <p className="text-xs leading-5 text-app-muted">
                    Primary source:{" "}
                    {contextStats.primary_source_url ? (
                      <a className="text-violet-300 hover:text-violet-200" href={contextStats.primary_source_url} target="_blank" rel="noreferrer">
                        {contextStats.primary_source_title}
                      </a>
                    ) : (
                      contextStats.primary_source_title
                    )}
                  </p>
                ) : null}
                {contextStats.search_terms && contextStats.search_terms.length > 0 ? (
                  <p className="text-xs leading-5 text-app-muted">Search terms: {contextStats.search_terms.join(", ")}</p>
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
    <div className="rounded-md border border-app-border bg-app-inset p-3">
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
      {source.url ? (
        <a className="mt-2 block truncate text-xs text-violet-300 hover:text-violet-200" href={source.url} target="_blank" rel="noreferrer">
          {source.url}
        </a>
      ) : null}
      {!source.url && source.path ? <p className="mt-2 truncate text-xs text-app-muted">{source.path}</p> : null}
    </div>
  );
}

function AnswerStyleBadge({ message }: { message: ChatMessageRecord }) {
  if (message.isFollowUp || message.intent === "follow_up_summary" || message.intent === "follow_up") {
    return <Badge variant="info">Follow-up</Badge>;
  }
  if (message.answerStyle === "root_cause") {
    return <Badge variant="info">Root-cause analysis</Badge>;
  }
  if (message.answerStyle === "source_summary" || message.intent === "entity_details" || message.intent === "source_summary") {
    return <Badge variant="info">Source summary</Badge>;
  }
  if (message.answerStyle === "summary") {
    return <Badge variant="info">Summary</Badge>;
  }
  if (message.answerStyle === "memory_lookup" || message.intent === "memory_lookup") {
    return <Badge variant="info">Memory lookup</Badge>;
  }
  return null;
}

function renderInline(text: string): ReactNode[] {
  // Inline markdown: **bold**, `code`, *italic*
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/g;
  const nodes: ReactNode[] = [];
  let last = 0;
  let key = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) {
      nodes.push(text.slice(last, match.index));
    }
    const token = match[0];
    if (token.startsWith("**")) {
      nodes.push(
        <strong key={key++} className="font-semibold">
          {token.slice(2, -2)}
        </strong>,
      );
    } else if (token.startsWith("`")) {
      nodes.push(
        <code key={key++} className="rounded bg-app-inset px-1.5 py-0.5 text-[0.85em] text-app-text">
          {token.slice(1, -1)}
        </code>,
      );
    } else {
      nodes.push(<em key={key++}>{token.slice(1, -1)}</em>);
    }
    last = pattern.lastIndex;
  }
  if (last < text.length) {
    nodes.push(text.slice(last));
  }
  return nodes;
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
        if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
          return <hr key={index} className="my-2 border-app-border" />;
        }

        const heading = /^(#{1,6})\s+(.*)$/.exec(trimmed);
        if (heading) {
          const level = heading[1].length;
          const size = level <= 1 ? "text-lg" : level === 2 ? "text-base" : "text-sm";
          return (
            <p key={index} className={`pt-2 font-semibold text-app-text ${size}`}>
              {renderInline(heading[2])}
            </p>
          );
        }

        const bullet = /^[-*]\s+(.*)$/.exec(trimmed);
        if (bullet) {
          return (
            <p key={index} className="flex gap-2 pl-4 text-sm leading-6 text-app-text">
              <span className="mt-px shrink-0 text-app-muted">•</span>
              <span>{renderInline(bullet[1])}</span>
            </p>
          );
        }

        const ordered = /^(\d+\.)\s+(.*)$/.exec(trimmed);
        if (ordered) {
          return (
            <p key={index} className="flex gap-2 pl-4 text-sm leading-6 text-app-text">
              <span className="shrink-0 text-app-muted">{ordered[1]}</span>
              <span>{renderInline(ordered[2])}</span>
            </p>
          );
        }

        return (
          <p key={index} className="text-sm leading-6 text-app-text">
            {renderInline(trimmed)}
          </p>
        );
      })}
    </div>
  );
}
