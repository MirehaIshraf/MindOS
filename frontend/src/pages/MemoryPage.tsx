import { Search, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "../components/shared/Badge";
import { Button } from "../components/shared/Button";
import { Card } from "../components/shared/Card";
import { EmptyState } from "../components/shared/EmptyState";
import { Input } from "../components/shared/Input";
import { getEventDetail, getRecentEvents, getRelatedEvents, getSearchStats, searchEvents } from "../services/api";
import type { MemoryEvent, RelatedEvent, SearchResult, SearchStatsResponse } from "../types";

const categories = [
  { label: "All", value: undefined },
  { label: "Chats", value: "chat" },
  { label: "Tasks", value: "task" },
  { label: "Captured Events", value: "captured_event" },
  { label: "Reports", value: "report" },
  { label: "MindOS", value: "mindos" },
] as const;

const sources = [
  { label: "All Sources", value: undefined },
  { label: "File System", value: "file_system" },
  { label: "Manual", value: "manual" },
  { label: "VSCode", value: "vscode" },
  { label: "Browser", value: "browser" },
  { label: "Git", value: "git" },
  { label: "GitHub", value: "github" },
  { label: "Jira", value: "jira" },
  { label: "Logs", value: "logs" },
  { label: "Email", value: "email" },
] as const;

type CategoryFilter = (typeof categories)[number];
type SourceFilter = (typeof sources)[number];

type DisplayItem =
  | {
      mode: "recent";
      event: MemoryEvent;
    }
  | {
      mode: "search";
      result: SearchResult;
    };

export function MemoryPage() {
  const [query, setQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<CategoryFilter>(categories[0]);
  const [selectedSource, setSelectedSource] = useState<SourceFilter>(sources[0]);
  const [recentEvents, setRecentEvents] = useState<MemoryEvent[]>([]);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [stats, setStats] = useState<SearchStatsResponse | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<MemoryEvent | null>(null);
  const [isSearchMode, setIsSearchMode] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadRecent();
  }, []);

  async function loadRecent(category = selectedCategory, source = selectedSource) {
    setLoading(true);
    setError(null);
    try {
      const includeHidden = category.value === "chat";
      const [recentResponse, statsResponse] = await Promise.all([
        getRecentEvents(source.value, 30, category.value, includeHidden),
        getSearchStats(),
      ]);
      setRecentEvents(recentResponse.events);
      setStats(statsResponse);
      setSearchResults([]);
      setIsSearchMode(false);
    } catch {
      setError("Could not load memory. Backend may be offline.");
      setRecentEvents([]);
      setStats(null);
    } finally {
      setLoading(false);
    }
  }

  async function runSearch(category = selectedCategory, source = selectedSource) {
    const trimmedQuery = query.trim();
    if (!trimmedQuery) {
      await loadRecent(category, source);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const [searchResponse, statsResponse] = await Promise.all([
        searchEvents(trimmedQuery, source.value ? [source.value] : undefined, 30, category.value, true),
        getSearchStats(),
      ]);
      setSearchResults(searchResponse.results);
      setStats(statsResponse);
      setIsSearchMode(true);
    } catch {
      setError("Search failed. Backend may be offline.");
      setSearchResults([]);
      setIsSearchMode(true);
    } finally {
      setLoading(false);
    }
  }

  async function handleCategoryClick(category: CategoryFilter) {
    setSelectedCategory(category);
    if (query.trim()) {
      await runSearch(category, selectedSource);
      return;
    }
    await loadRecent(category, selectedSource);
  }

  async function handleSourceClick(source: SourceFilter) {
    setSelectedSource(source);
    if (query.trim()) {
      await runSearch(selectedCategory, source);
      return;
    }
    await loadRecent(selectedCategory, source);
  }

  async function handleClear() {
    setQuery("");
    setSelectedCategory(categories[0]);
    setSelectedSource(sources[0]);
    setSelectedEvent(null);
    await loadRecent(categories[0], sources[0]);
  }

  async function handleOpenDetail(item: DisplayItem) {
    const eventId = item.mode === "search" ? item.result.event_id : item.event.id;
    setError(null);
    try {
      const event = await getEventDetail(eventId);
      setSelectedEvent(event);
    } catch {
      setError("Could not load event detail.");
    }
  }

  const displayItems: DisplayItem[] = useMemo(() => {
    if (isSearchMode) {
      return searchResults.map((result) => ({ mode: "search", result }));
    }
    return recentEvents.map((event) => ({ mode: "recent", event }));
  }, [isSearchMode, recentEvents, searchResults]);

  const includesHiddenChat = isSearchMode && searchResults.some((result) => result.hidden_from_default);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-app-text">Memory</h1>
        <p className="mt-2 text-sm text-app-muted">Browse your local history, captured activity, chats, tasks, and reports.</p>
      </header>

      <Card className="space-y-4">
        <div className="flex gap-3">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-app-muted" size={17} />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  void runSearch();
                }
              }}
              className="pl-10"
              placeholder="Search memory..."
            />
          </div>
          <Button variant="primary" onClick={() => void runSearch()} disabled={!query.trim()}>
            Search
          </Button>
          <Button variant="secondary" onClick={() => void handleClear()}>
            Clear
          </Button>
        </div>

        <FilterRow items={categories} selectedLabel={selectedCategory.label} onSelect={(item) => void handleCategoryClick(item)} />
        <FilterRow items={sources} selectedLabel={selectedSource.label} onSelect={(item) => void handleSourceClick(item)} />
      </Card>

      <StatsRow stats={stats} />

      {includesHiddenChat ? (
        <p className="rounded-md border border-violet-500/30 bg-violet-500/10 px-4 py-3 text-sm text-violet-100">
          Some results are from chat history.
        </p>
      ) : null}

      {error ? <p className="rounded-md border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</p> : null}

      <div className={selectedEvent ? "grid grid-cols-[1fr_360px] gap-4" : "grid grid-cols-1"}>
        <Card>
          <div className="flex items-center justify-between gap-4">
            <h2 className="text-base font-semibold text-app-text">
              {isSearchMode ? `Search Results (${searchResults.length})` : "Unified Timeline"}
            </h2>
            <Badge variant="info">keyword</Badge>
          </div>
          <div className="mt-4 space-y-3">
            {loading ? (
              <p className="text-sm text-app-muted">Loading memory...</p>
            ) : displayItems.length === 0 ? (
              <EmptyState title={emptyTitle(selectedCategory, isSearchMode)} description={emptyDescription(selectedCategory, isSearchMode)} />
            ) : (
              displayItems.map((item) => (
                <MemoryResultCard
                  key={item.mode === "search" ? item.result.event_id : item.event.id}
                  item={item}
                  onClick={() => void handleOpenDetail(item)}
                />
              ))
            )}
          </div>
        </Card>

        {selectedEvent ? <EventDetailPanel event={selectedEvent} onClose={() => setSelectedEvent(null)} /> : null}
      </div>
    </div>
  );
}

function FilterRow<T extends { label: string }>({
  items,
  selectedLabel,
  onSelect,
}: {
  items: readonly T[];
  selectedLabel: string;
  onSelect: (item: T) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {items.map((item) => (
        <button key={item.label} type="button" className="transition hover:opacity-80" onClick={() => onSelect(item)}>
          <Badge variant={item.label === selectedLabel ? "info" : "default"}>{item.label}</Badge>
        </button>
      ))}
    </div>
  );
}

function StatsRow({ stats }: { stats: SearchStatsResponse | null }) {
  const categoryCounts = Object.entries(stats?.by_category ?? {});
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <Badge variant="success">Visible: {stats?.visible_default_events ?? 0}</Badge>
      <Badge variant="default">Hidden chat/history: {stats?.hidden_events ?? 0}</Badge>
      <Badge variant="info">Total: {stats?.total_events ?? 0}</Badge>
      {categoryCounts.map(([category, count]) => (
        <Badge key={category} variant="default">
          {formatCategoryLabel(category)}: {count}
        </Badge>
      ))}
    </div>
  );
}

function MemoryResultCard({ item, onClick }: { item: DisplayItem; onClick: () => void }) {
  const isSearch = item.mode === "search";
  const source = isSearch ? item.result.source : item.event.source;
  const type = isSearch ? item.result.type : item.event.type;
  const title = isSearch ? item.result.title : item.event.title;
  const preview = isSearch ? item.result.content_preview : item.event.content;
  const timestamp = isSearch ? item.result.timestamp : item.event.timestamp;
  const embeddingStatus = isSearch ? item.result.embedding_status : item.event.embedding_status;
  const metadata = isSearch ? item.result.metadata : item.event.metadata;
  const category = isSearch ? item.result.memory_category : item.event.memory_category;
  const hiddenFromDefault = isSearch ? item.result.hidden_from_default : item.event.hidden_from_default;
  const relatedCount = isSearch ? item.result.related_count : item.event.related_count;
  const taskType = typeof metadata.task_type === "string" ? metadata.task_type : null;

  return (
    <button
      type="button"
      onClick={onClick}
      className="block w-full rounded-md border border-app-border bg-zinc-950 px-4 py-3 text-left transition hover:border-violet-500/50"
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={source === "mindos" ? "info" : "default"}>{formatSourceLabel(source)}</Badge>
        <Badge variant={category === "chat" || category === "task" || category === "report" ? "info" : "default"}>
          {formatCategoryLabel(category)}
        </Badge>
        <Badge>{formatTypeLabel(type)}</Badge>
        {taskType ? <Badge variant="info">{taskType}</Badge> : null}
        {hiddenFromDefault ? <Badge variant="default">hidden by default</Badge> : null}
        {relatedCount ? <Badge variant="info">{relatedCount} related</Badge> : null}
        <Badge>{embeddingStatus}</Badge>
        <span className="ml-auto text-xs text-app-muted">{formatTimestamp(timestamp)}</span>
      </div>
      <h3 className="mt-3 text-sm font-semibold text-app-text">{title}</h3>
      {preview ? <p className="mt-2 text-sm leading-6 text-app-muted">{truncate(preview, 180)}</p> : null}
      {isSearch ? (
        <div className="mt-3 flex items-center gap-2 text-xs text-app-muted">
          <Badge variant="success">score {item.result.score.toFixed(2)}</Badge>
          <span>{item.result.match_reason}</span>
        </div>
      ) : null}
    </button>
  );
}

function EventDetailPanel({ event, onClose }: { event: MemoryEvent; onClose: () => void }) {
  const [related, setRelated] = useState<RelatedEvent[]>([]);
  const [loadingRelated, setLoadingRelated] = useState(true);

  useEffect(() => {
    setLoadingRelated(true);
    getRelatedEvents(event.id)
      .then((response) => setRelated(response.related))
      .catch(() => setRelated([]))
      .finally(() => setLoadingRelated(false));
  }, [event.id]);

  return (
    <Card className="sticky top-24 max-h-[calc(100vh-7rem)] overflow-auto">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-app-text">{event.title}</h2>
          <div className="mt-3 flex flex-wrap gap-2">
            <Badge variant={event.source === "mindos" ? "info" : "default"}>{formatSourceLabel(event.source)}</Badge>
            <Badge variant="info">{formatCategoryLabel(event.memory_category)}</Badge>
            <Badge>{formatTypeLabel(event.type)}</Badge>
            {typeof event.metadata.task_type === "string" ? <Badge variant="info">{event.metadata.task_type}</Badge> : null}
            {event.hidden_from_default ? <Badge>hidden by default</Badge> : null}
            <Badge>{event.embedding_status}</Badge>
          </div>
        </div>
        <button type="button" onClick={onClose} className="rounded-md p-1 text-app-muted hover:bg-zinc-800 hover:text-app-text">
          <X size={18} />
        </button>
      </div>
      <div className="mt-5 space-y-4">
        <DetailRow label="timestamp" value={formatTimestamp(event.timestamp)} />
        <DetailRow label="created" value={formatTimestamp(event.created_at)} />
        <div>
          <p className="text-xs uppercase text-app-muted">content</p>
          <p className="mt-2 whitespace-pre-wrap rounded-md border border-app-border bg-zinc-950 p-3 text-sm leading-6 text-app-text">
            {event.content || "No content"}
          </p>
        </div>
        <div>
          <p className="text-xs uppercase text-app-muted">metadata</p>
          <pre className="mt-2 overflow-auto rounded-md border border-app-border bg-zinc-950 p-3 text-xs leading-5 text-app-text">
            {JSON.stringify(event.metadata, null, 2)}
          </pre>
        </div>
        <div>
          <p className="text-xs uppercase text-app-muted">related memory</p>
          <div className="mt-2 space-y-2">
            {loadingRelated ? (
              <p className="text-sm text-app-muted">Loading related memory...</p>
            ) : related.length === 0 ? (
              <p className="text-sm text-app-muted">No related memory found.</p>
            ) : (
              related.map((item) => (
                <div key={item.relationship.id} className="rounded-md border border-app-border bg-zinc-950 p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="info">{item.relationship.relationship_type}</Badge>
                    <Badge>{item.relationship.strength.toFixed(2)}</Badge>
                    <Badge>{formatSourceLabel(item.event.source)}</Badge>
                    <Badge>{formatTypeLabel(item.event.type)}</Badge>
                  </div>
                  <h3 className="mt-2 text-sm font-semibold text-app-text">{item.event.title}</h3>
                  <p className="mt-1 text-xs leading-5 text-app-muted">{item.relationship.reason}</p>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 text-sm">
      <span className="text-app-muted">{label}</span>
      <span className="text-app-text">{value}</span>
    </div>
  );
}

function emptyTitle(category: CategoryFilter, isSearchMode: boolean) {
  if (isSearchMode) {
    return "No matching memory found.";
  }
  if (category.value === "chat") {
    return "No chat history yet. Start a conversation in Chat.";
  }
  if (category.value === "task") {
    return "No task history yet. Prepare a task from Chat or Tasks.";
  }
  return "No visible memory yet. Seed sample data or complete a task.";
}

function emptyDescription(category: CategoryFilter, isSearchMode: boolean) {
  if (isSearchMode) {
    return "Try a different query, category, or source filter.";
  }
  if (category.value === "chat") {
    return "Saved chat events will appear here.";
  }
  if (category.value === "task") {
    return "Prepared and completed tasks will appear here.";
  }
  return "Default memory hides raw chat events to keep the timeline clean.";
}

function truncate(value: string, maxLength: number) {
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, maxLength)}...`;
}

function formatSourceLabel(source: string) {
  if (source === "mindos") {
    return "MindOS";
  }
  if (source === "file_system") {
    return "File System";
  }
  if (source === "git") {
    return "Git";
  }
  return source;
}

function formatCategoryLabel(category: string) {
  const labels: Record<string, string> = {
    chat: "Chat",
    task: "Task",
    report: "Report",
    captured_event: "Captured",
    mindos: "MindOS",
    unknown: "Unknown",
  };
  return labels[category] ?? category;
}

function formatTypeLabel(type: string) {
  if (type === "chat_message") {
    return "Chat Message";
  }
  if (type === "chat_response") {
    return "Chat Response";
  }
  return type;
}

function formatTimestamp(value: string) {
  return new Date(value).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
