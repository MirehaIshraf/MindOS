import { useEffect, useState } from "react";
import { Check, Folder, FolderOpen, Server, Wrench, X } from "lucide-react";

import { getMcpServers, toggleMcpServer, getMcpServerTools, updateMcpServerConfig } from "../services/api";
import type { McpServerStatus, McpToolInfo } from "../types";
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
      className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${checked ? "bg-emerald-500" : "bg-app-border"} ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
    >
      <span className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${checked ? "translate-x-4" : "translate-x-0"}`} />
    </button>
  );
}

function mcpServerIcon(serverId: string) {
  if (serverId === "filesystem") return Folder;
  return Server;
}

// ---------------------------------------------------------------------------
// FileSystem Config Panel
// ---------------------------------------------------------------------------

function FileSystemConfigPanel({
  server,
  onConfigured,
}: {
  server: McpServerStatus;
  onConfigured: () => void;
}) {
  const [pathInput, setPathInput] = useState<string>((server.config.root_path as string) ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const currentRoot = (server.config.root_path as string) ?? "";

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
      await updateMcpServerConfig(server.server_id, { root_path: trimmed });
      setSuccess(true);
      onConfigured();
    } catch (err) {
      setError("Failed to save configuration. Make sure the path is a valid directory.");
    } finally {
      setSaving(false);
    }
  }

  async function handleBrowse() {
    // Try the File System Access API (Chromium browsers)
    if ("showDirectoryPicker" in window) {
      try {
        const dirHandle = await (window as unknown as { showDirectoryPicker: () => Promise<FileSystemDirectoryHandle> }).showDirectoryPicker();
        // The File System Access API doesn't expose absolute paths for security.
        // We can only get the name. Tell the user to type the path manually.
        setPathInput(dirHandle.name);
        setError(`Browser security prevents reading the full path. Please type the absolute path manually (e.g. D:\\Projects\\${dirHandle.name}).`);
        return;
      } catch {
        // User cancelled the picker
        return;
      }
    }
    setError("Your browser doesn't support directory picking. Please type the path manually.");
  }

  function handleClear() {
    setPathInput("");
    setSuccess(false);
    setError(null);
  }

  return (
    <div className="mt-4 space-y-3 border-t border-app-border pt-3" onClick={(e) => e.stopPropagation()}>
      <p className="text-xs font-medium text-app-muted uppercase">Configuration — Root Directory</p>
      <p className="text-xs text-app-muted">
        Choose a local directory as the root path. The LLM will only be able to operate inside this directory and its subdirectories recursively.
      </p>

      {currentRoot && (
        <div className="flex items-center gap-2 rounded-md bg-emerald-900/30 border border-emerald-800/40 px-3 py-2">
          <FolderOpen size={14} className="text-emerald-400 shrink-0" />
          <span className="text-xs text-emerald-300 truncate">Current: {currentRoot}</span>
        </div>
      )}

      <div className="flex gap-2">
        <input
          type="text"
          value={pathInput}
          onChange={(e) => { setPathInput(e.target.value); setSuccess(false); setError(null); }}
          placeholder="D:\Projects\MyFolder"
          className="flex-1 rounded-md border border-app-border bg-app-elevated px-3 py-1.5 text-xs text-app-text placeholder:text-app-muted focus:border-emerald-500 focus:outline-none"
          onKeyDown={(e) => { if (e.key === "Enter") void handleSave(); }}
        />
        <button
          type="button"
          onClick={handleBrowse}
          className="rounded-md border border-app-border bg-app-elevated px-3 py-1.5 text-xs text-app-muted hover:bg-app-inset hover:text-app-text transition-colors"
          title="Browse for directory (limited by browser security)"
        >
          Browse
        </button>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={saving || !pathInput.trim()}
          className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {saving ? "Saving..." : "Save Path"}
        </button>
        {pathInput && (
          <button
            type="button"
            onClick={handleClear}
            className="rounded-md border border-app-border bg-app-elevated px-2 py-1.5 text-xs text-app-muted hover:bg-app-inset hover:text-app-text transition-colors"
          >
            <X size={12} />
          </button>
        )}
        {success && (
          <span className="flex items-center gap-1 text-xs text-emerald-400">
            <Check size={12} /> Saved
          </span>
        )}
      </div>

      {error && <p className="text-xs text-red-400">{error}</p>}

      {!server.configured && !currentRoot && (
        <p className="text-xs text-amber-400">
          ⚠ Root directory is required before enabling this server. Set a path above, then toggle the server on.
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main MCP Server Section
// ---------------------------------------------------------------------------

export function McpServerSection() {
  const [servers, setServers] = useState<McpServerStatus[]>([]);
  const [expandedServer, setExpandedServer] = useState<string | null>(null);
  const [serverTools, setServerTools] = useState<Record<string, McpToolInfo[]>>({});
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      const response = await getMcpServers();
      setServers(response.servers);
    } catch {
      setError("Failed to load MCP servers.");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function handleToggle(serverId: string, enabled: boolean) {
    const server = servers.find((s) => s.server_id === serverId);
    // Block enabling an unconfigured server
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
        setServerTools((prev) => ({ ...prev, [serverId]: response.tools }));
      } catch {
        setServerTools((prev) => ({ ...prev, [serverId]: [] }));
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
          const readonlyCount = tools.filter((t) => !t.side_effect).length;
          const sideEffectCount = tools.filter((t) => t.side_effect).length;

          return (
            <Card key={server.server_id} className="cursor-pointer" onClick={() => void handleExpand(server.server_id)}>
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2">
                  <div className="flex h-8 w-8 items-center justify-center rounded-md bg-app-elevated">
                    <Icon size={16} className="text-app-muted" />
                  </div>
                  <div className="min-w-0">
                    <h3 className="truncate text-sm font-semibold text-app-text">{server.name}</h3>
                    <p className="truncate text-xs text-app-muted">{server.description}</p>
                  </div>
                </div>
                <div onClick={(e) => e.stopPropagation()}>
                  <McpToggle
                    checked={server.enabled}
                    disabled={loading === `toggle:${server.server_id}`}
                    onChange={(enabled: boolean) => void handleToggle(server.server_id, enabled)}
                  />
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Badge>{server.connected ? "connected" : "offline"}</Badge>
                {server.configured ? (
                  <Badge variant="success">configured</Badge>
                ) : (
                  <Badge variant="warning">needs config</Badge>
                )}
                <Badge>{server.tool_count} tools</Badge>
                {server.categories.map((cat) => (
                  <Badge key={cat}>{cat}</Badge>
                ))}
              </div>

              {/* Config panel for filesystem server */}
              {isExpanded && server.server_id === "filesystem" && (
                <FileSystemConfigPanel
                  server={server}
                  onConfigured={() => void refresh()}
                />
              )}

              {/* Tools list */}
              {isExpanded && tools.length > 0 && (
                <div className="mt-4 space-y-2 border-t border-app-border pt-3" onClick={(e) => e.stopPropagation()}>
                  <p className="text-xs font-medium text-app-muted uppercase">Available Tools</p>
                  {tools.map((tool) => (
                    <div key={tool.name} className="rounded-md bg-app-elevated p-2">
                      <div className="flex items-center gap-2">
                        <Wrench size={12} className="text-app-muted" />
                        <span className="text-xs font-mono font-medium text-app-text">{tool.name}</span>
                        {tool.side_effect && <Badge>requires confirmation</Badge>}
                      </div>
                      <p className="mt-1 text-xs text-app-muted">{tool.description}</p>
                    </div>
                  ))}
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
