import { useEffect, useState } from "react";
import { Check, ChevronLeft, Folder, FolderOpen, HardDrive, RefreshCw, Server, Wrench, X } from "lucide-react";

import { browseMcpFilesystem, getMcpServers, getMcpServerTools, toggleMcpServer, updateMcpServerConfig } from "../services/api";
import type { McpFilesystemBrowseResponse, McpServerStatus, McpToolInfo } from "../types";
import { Badge } from "./shared/Badge";
import { Card } from "./shared/Card";

function McpToggle({ checked, disabled, onChange }: { checked: boolean; disabled: boolean; onChange: (checked: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${checked ? "bg-emerald-500" : "bg-app-border"} ${disabled ? "cursor-not-allowed opacity-50" : ""}`}
    >
      <span className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${checked ? "translate-x-4" : "translate-x-0"}`} />
    </button>
  );
}

function mcpServerIcon(serverId: string) {
  if (serverId === "filesystem") return Folder;
  return Server;
}

function FileSystemConfigPanel({
  server,
  onConfigured,
}: {
  server: McpServerStatus;
  onConfigured: () => void;
}) {
  const [pathInput, setPathInput] = useState<string>((server.config.root_path as string) ?? "");
  const [maxDepth, setMaxDepth] = useState<number>(Number(server.config.max_depth ?? 5));
  const [maxFiles, setMaxFiles] = useState<number>(Number(server.config.max_files ?? 2000));
  const [recursive, setRecursive] = useState<boolean>(Boolean(server.config.recursive ?? true));
  const [indexReadableFiles, setIndexReadableFiles] = useState<boolean>(Boolean(server.config.index_readable_files ?? true));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [browseOpen, setBrowseOpen] = useState(false);
  const [browseData, setBrowseData] = useState<McpFilesystemBrowseResponse | null>(null);
  const [browseLoading, setBrowseLoading] = useState(false);
  const [browseError, setBrowseError] = useState<string | null>(null);

  const currentRoot = (server.config.root_path as string) ?? "";
  const indexStatus = (server.config.index_status as string) ?? "idle";
  const watchStatus = (server.config.watch_status as string) ?? "idle";
  const indexedCount = Number(server.config.indexed_count ?? 0);
  const inventoryCount = Number(server.config.inventory_count ?? 0);
  const missingCount = Number(server.config.missing_count ?? 0);
  const lastIndexedAt = (server.config.last_indexed_at as string | undefined) ?? "";
  const lastError = server.config.last_error ? String(server.config.last_error) : "";

  useEffect(() => {
    setPathInput((server.config.root_path as string) ?? "");
    setMaxDepth(Number(server.config.max_depth ?? 5));
    setMaxFiles(Number(server.config.max_files ?? 2000));
    setRecursive(Boolean(server.config.recursive ?? true));
    setIndexReadableFiles(Boolean(server.config.index_readable_files ?? true));
  }, [server.config]);

  async function handleSave() {
    const trimmed = pathInput.trim();
    if (!trimmed) {
      setError("Please enter a directory path.");
      return;
    }
    setSaving(true);
    setError(null);
    setSuccess(false);
    try {
      await updateMcpServerConfig(server.server_id, {
        root_path: trimmed,
        max_depth: maxDepth,
        max_files: maxFiles,
        recursive,
        index_readable_files: indexReadableFiles,
      });
      setSuccess(true);
      onConfigured();
    } catch {
      setError("Failed to save configuration. Make sure the path is a valid directory.");
    } finally {
      setSaving(false);
    }
  }

  async function loadBrowse(path?: string) {
    setBrowseOpen(true);
    setBrowseLoading(true);
    setBrowseError(null);
    try {
      const response = await browseMcpFilesystem(path);
      setBrowseData(response);
    } catch {
      setBrowseError("Could not open that folder.");
    } finally {
      setBrowseLoading(false);
    }
  }

  function handleClear() {
    setPathInput("");
    setSuccess(false);
    setError(null);
  }

  function formatDate(value: string) {
    if (!value) return "--";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
  }

  return (
    <div className="mt-4 space-y-4 border-t border-app-border pt-4" onClick={(event) => event.stopPropagation()}>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="space-y-3">
          <div>
            <p className="text-xs font-medium uppercase text-app-muted">Configuration - Root Directory</p>
            <p className="mt-1 text-xs text-app-muted">This MCP server uses its own saved root folder for chat tools, indexing, and watching.</p>
          </div>

          {currentRoot && (
            <div className="flex items-center gap-2 rounded-md border border-emerald-800/40 bg-emerald-900/20 px-3 py-2">
              <FolderOpen size={14} className="shrink-0 text-emerald-400" />
              <span className="truncate text-xs text-emerald-300">Current: {currentRoot}</span>
            </div>
          )}

          <div className="flex flex-col gap-2 sm:flex-row">
            <input
              type="text"
              value={pathInput}
              onChange={(event) => {
                setPathInput(event.target.value);
                setSuccess(false);
                setError(null);
              }}
              placeholder={"D:\\Projects\\MyFolder"}
              className="min-w-0 flex-1 rounded-md border border-app-border bg-app-elevated px-3 py-2 text-sm text-app-text placeholder:text-app-muted focus:border-emerald-500 focus:outline-none"
              onKeyDown={(event) => {
                if (event.key === "Enter") void handleSave();
              }}
            />
            <button
              type="button"
              onClick={() => void loadBrowse(pathInput.trim() || currentRoot || undefined)}
              className="inline-flex items-center justify-center gap-2 rounded-md border border-app-border bg-app-elevated px-3 py-2 text-sm text-app-muted transition-colors hover:bg-app-inset hover:text-app-text"
              title="Browse local folders through the backend"
            >
              <Folder size={15} /> Browse
            </button>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="space-y-1 text-xs text-app-muted">
              <span className="font-medium uppercase">Max files</span>
              <input
                type="number"
                min={1}
                max={5000}
                value={maxFiles}
                onChange={(event) => setMaxFiles(Number(event.target.value))}
                className="w-full rounded-md border border-app-border bg-app-elevated px-3 py-2 text-sm text-app-text focus:border-emerald-500 focus:outline-none"
              />
            </label>
            <label className="space-y-1 text-xs text-app-muted">
              <span className="font-medium uppercase">Max depth</span>
              <input
                type="number"
                min={0}
                max={10}
                value={maxDepth}
                onChange={(event) => setMaxDepth(Number(event.target.value))}
                className="w-full rounded-md border border-app-border bg-app-elevated px-3 py-2 text-sm text-app-text focus:border-emerald-500 focus:outline-none"
              />
            </label>
          </div>

          <div className="flex flex-wrap gap-4">
            <label className="inline-flex items-center gap-2 text-sm text-app-text">
              <input type="checkbox" checked={recursive} onChange={(event) => setRecursive(event.target.checked)} />
              Recursive
            </label>
            <label className="inline-flex items-center gap-2 text-sm text-app-text">
              <input type="checkbox" checked={indexReadableFiles} onChange={(event) => setIndexReadableFiles(event.target.checked)} />
              Index readable files
            </label>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => void handleSave()}
              disabled={saving || !pathInput.trim()}
              className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saving ? "Saving..." : "Save MCP Root"}
            </button>
            {pathInput && (
              <button
                type="button"
                onClick={handleClear}
                className="rounded-md border border-app-border bg-app-elevated px-3 py-2 text-sm text-app-muted transition-colors hover:bg-app-inset hover:text-app-text"
                title="Clear path"
              >
                <X size={14} />
              </button>
            )}
            {success && (
              <span className="flex items-center gap-1 text-xs text-emerald-400">
                <Check size={12} /> Saved
              </span>
            )}
          </div>

          {error && <p className="text-xs text-red-400">{error}</p>}

          {!server.configured && !currentRoot && <p className="text-xs text-amber-400">Root directory is required before enabling this server.</p>}
        </div>

        <div className="rounded-md border border-app-border bg-app-elevated p-3">
          <p className="text-xs font-medium uppercase text-app-muted">Index Status</p>
          <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
            <span className="text-app-muted">Index</span>
            <span className="text-right text-app-text">{indexStatus}</span>
            <span className="text-app-muted">Watcher</span>
            <span className="text-right text-app-text">{watchStatus}</span>
            <span className="text-app-muted">Indexed</span>
            <span className="text-right text-app-text">{indexedCount}</span>
            <span className="text-app-muted">Inventory</span>
            <span className="text-right text-app-text">{inventoryCount}</span>
            <span className="text-app-muted">Missing</span>
            <span className="text-right text-app-text">{missingCount}</span>
          </div>
          <p className="mt-3 text-xs text-app-muted">Last indexed: {formatDate(lastIndexedAt)}</p>
          {lastError && <p className="mt-2 text-xs text-amber-400">{lastError}</p>}
        </div>
      </div>

      {browseOpen && (
        <div className="rounded-md border border-app-border bg-app-elevated p-3">
          <div className="mb-3 flex items-center justify-between gap-2">
            <div className="min-w-0">
              <p className="text-xs font-medium uppercase text-app-muted">Browse Folders</p>
              <p className="truncate text-xs text-app-muted">{browseData?.current_path ?? "Choose a drive or folder"}</p>
            </div>
            <button type="button" onClick={() => setBrowseOpen(false)} className="rounded-md border border-app-border px-2 py-1 text-xs text-app-muted hover:text-app-text">
              Close
            </button>
          </div>

          <div className="mb-3 flex flex-wrap gap-2">
            {browseData?.parent_path && (
              <button type="button" onClick={() => void loadBrowse(browseData.parent_path ?? undefined)} className="inline-flex items-center gap-1 rounded-md border border-app-border px-2 py-1 text-xs text-app-muted hover:text-app-text">
                <ChevronLeft size={13} /> Parent
              </button>
            )}
            {browseData?.drives.map((drive) => (
              <button key={drive.path} type="button" onClick={() => void loadBrowse(drive.path)} className="inline-flex items-center gap-1 rounded-md border border-app-border px-2 py-1 text-xs text-app-muted hover:text-app-text">
                <HardDrive size={13} /> {drive.name}
              </button>
            ))}
            <button type="button" onClick={() => void loadBrowse(browseData?.current_path ?? undefined)} className="inline-flex items-center gap-1 rounded-md border border-app-border px-2 py-1 text-xs text-app-muted hover:text-app-text">
              <RefreshCw size={13} /> Refresh
            </button>
            {browseData?.current_path && (
              <button
                type="button"
                disabled={browseData.selectable === false}
                onClick={() => {
                  if (browseData.current_path) {
                    setPathInput(browseData.current_path);
                    setBrowseOpen(false);
                    setError(null);
                  }
                }}
                className="rounded-md bg-emerald-600 px-3 py-1 text-xs font-medium text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Select current
              </button>
            )}
          </div>

          {browseLoading && <p className="text-xs text-app-muted">Loading folders...</p>}
          {browseError && <p className="text-xs text-red-400">{browseError}</p>}
          {browseData?.selection_error && <p className="mb-2 text-xs text-amber-400">{browseData.selection_error}</p>}
          {!browseLoading && browseData && (
            <div className="max-h-64 overflow-auto rounded-md border border-app-border bg-app-panel">
              {browseData.entries.length === 0 ? (
                <p className="p-3 text-xs text-app-muted">No child folders found.</p>
              ) : (
                browseData.entries.map((entry) => (
                  <button key={entry.path} type="button" onClick={() => void loadBrowse(entry.path)} className="flex w-full items-center gap-2 border-b border-app-border px-3 py-2 text-left text-sm text-app-text last:border-b-0 hover:bg-app-inset">
                    <Folder size={14} className="shrink-0 text-app-muted" />
                    <span className="truncate">{entry.name}</span>
                  </button>
                ))
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function McpServerSection() {
  const [servers, setServers] = useState<McpServerStatus[]>([]);
  const [expandedServer, setExpandedServer] = useState<string | null>(null);
  const [serverTools, setServerTools] = useState<Record<string, McpToolInfo[]>>({});
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      const response = await getMcpServers();
      setServers(response.servers.filter((server) => server.server_id !== "gmail"));
    } catch {
      setError("Failed to load MCP servers.");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function handleToggle(serverId: string, enabled: boolean) {
    const server = servers.find((item) => item.server_id === serverId);
    if (enabled && server && !server.configured) {
      setError(`Configure ${server.name} before enabling it.`);
      return;
    }
    setLoading(`toggle:${serverId}`);
    setError(null);
    try {
      await toggleMcpServer(serverId, enabled);
      await refresh();
    } catch {
      setError("Failed to toggle MCP server.");
    } finally {
      setLoading(null);
    }
  }

  async function handleExpand(serverId: string) {
    if (expandedServer === serverId) {
      setExpandedServer(null);
      return;
    }
    setExpandedServer(serverId);
    if (!serverTools[serverId]) {
      try {
        const response = await getMcpServerTools(serverId);
        setServerTools((previous) => ({ ...previous, [serverId]: response.tools }));
      } catch {
        setServerTools((previous) => ({ ...previous, [serverId]: [] }));
      }
    }
  }

  if (servers.length === 0) return null;

  return (
    <div className="mt-8">
      <div className="mb-4 flex items-center gap-2">
        <Server size={18} className="text-app-muted" />
        <h2 className="text-lg font-semibold text-app-text">MCP Servers</h2>
        <span className="text-xs text-app-muted">Model Context Protocol tools for the LLM</span>
      </div>
      {error && <p className="mb-3 text-sm text-red-400">{error}</p>}
      <div className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-4">
        {servers.map((server) => {
          const Icon = mcpServerIcon(server.server_id);
          const isExpanded = expandedServer === server.server_id;
          const tools = serverTools[server.server_id] ?? [];
          const readonlyCount = tools.filter((tool) => !tool.side_effect).length;
          const sideEffectCount = tools.filter((tool) => tool.side_effect).length;
          const isFilesystem = server.server_id === "filesystem";

          return (
            <Card key={server.server_id} className={`cursor-pointer ${isFilesystem ? "sm:col-span-2 2xl:col-span-4" : ""}`} onClick={() => void handleExpand(server.server_id)}>
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-center gap-3">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-app-elevated">
                    <Icon size={18} className="text-app-muted" />
                  </div>
                  <div className="min-w-0">
                    <h3 className="truncate text-base font-semibold text-app-text">{server.name}</h3>
                    <p className="truncate text-sm text-app-muted">{server.description}</p>
                  </div>
                </div>
                <div onClick={(event) => event.stopPropagation()}>
                  <McpToggle checked={server.enabled} disabled={loading === `toggle:${server.server_id}`} onChange={(enabled) => void handleToggle(server.server_id, enabled)} />
                </div>
              </div>

              <div className="mt-3 flex flex-wrap gap-2">
                <Badge>{server.connected ? "connected" : "offline"}</Badge>
                {server.configured ? <Badge variant="success">configured</Badge> : <Badge variant="warning">needs config</Badge>}
                <Badge>{server.tool_count} tools</Badge>
                {server.categories.map((category) => (
                  <Badge key={category}>{category}</Badge>
                ))}
              </div>

              {isExpanded && isFilesystem && <FileSystemConfigPanel server={server} onConfigured={() => void refresh()} />}

              {isExpanded && tools.length > 0 && (
                <div className="mt-4 space-y-3 border-t border-app-border pt-3" onClick={(event) => event.stopPropagation()}>
                  <p className="text-xs font-medium uppercase text-app-muted">Available Tools</p>
                  <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
                    {tools.map((tool) => (
                      <div key={tool.name} className="rounded-md bg-app-elevated p-3">
                        <div className="flex items-center gap-2">
                          <Wrench size={12} className="shrink-0 text-app-muted" />
                          <span className="truncate font-mono text-xs font-medium text-app-text">{tool.name}</span>
                          {tool.side_effect && <Badge>requires confirmation</Badge>}
                        </div>
                        <p className="mt-1 text-xs text-app-muted">{tool.description}</p>
                      </div>
                    ))}
                  </div>
                  <div className="flex gap-3 text-xs text-app-muted">
                    <span>{readonlyCount} read-only</span>
                    <span>{sideEffectCount} requires confirmation</span>
                  </div>
                </div>
              )}

              {isExpanded && tools.length === 0 && serverTools[server.server_id] !== undefined && (
                <div className="mt-4 border-t border-app-border pt-3">
                  <p className="text-xs text-app-muted">No tools available.</p>
                </div>
              )}
            </Card>
          );
        })}
      </div>
    </div>
  );
}
