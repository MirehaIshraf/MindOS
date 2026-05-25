import axios from "axios";
import { Cable, FolderOpen, RefreshCw, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "../components/shared/Badge";
import { Button } from "../components/shared/Button";
import { Card } from "../components/shared/Card";
import { Input } from "../components/shared/Input";
import {
  clearLogEvents,
  getConnectors,
  importFiles,
  importGitRepo,
  importLogs,
  previewFileImport,
  previewGitImport,
  previewLogImport,
} from "../services/api";
import type {
  Connector,
  FileImportPayload,
  FileImportResult,
  FilePreviewResult,
  GitImportPayload,
  GitImportResult,
  GitPreviewResult,
  LogImportPayload,
  LogImportResult,
  LogPreviewResult,
} from "../types";

const emptyForm = {
  folderPath: "",
  recursive: true,
  maxFiles: 100,
  maxFileSizeKb: 256,
  allowedExtensions: "",
};

type ImportForm = typeof emptyForm;

const emptyLogForm = {
  filePath: "",
  maxLines: 1000,
  onlyErrors: false,
  groupSimilar: true,
};

type LogImportForm = typeof emptyLogForm;

const emptyGitForm = {
  repoPath: "",
  maxCommits: 50,
  includeDiffSummary: true,
  includeStatus: true,
};

type GitImportForm = typeof emptyGitForm;

export function ConnectorsPage() {
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [panelOpen, setPanelOpen] = useState<"files" | "logs" | "git" | null>(null);
  const [form, setForm] = useState<ImportForm>(emptyForm);
  const [logForm, setLogForm] = useState<LogImportForm>(emptyLogForm);
  const [gitForm, setGitForm] = useState<GitImportForm>(emptyGitForm);
  const [preview, setPreview] = useState<FilePreviewResult | null>(null);
  const [result, setResult] = useState<FileImportResult | null>(null);
  const [logPreview, setLogPreview] = useState<LogPreviewResult | null>(null);
  const [logResult, setLogResult] = useState<LogImportResult | null>(null);
  const [gitPreview, setGitPreview] = useState<GitPreviewResult | null>(null);
  const [gitResult, setGitResult] = useState<GitImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState<string | null>(null);

  useEffect(() => {
    void refreshConnectors();
  }, []);

  async function refreshConnectors() {
    setLoading("connectors");
    setError(null);
    try {
      const response = await getConnectors();
      setConnectors(response.connectors);
    } catch {
      setError("Could not load connectors. Backend may be offline.");
    } finally {
      setLoading(null);
    }
  }

  async function handlePreview() {
    setLoading("preview");
    setError(null);
    setNotice(null);
    setResult(null);
    try {
      setPreview(await previewFileImport(toPayload(form)));
    } catch (caughtError) {
      setError(errorMessage(caughtError, "Preview failed."));
      setPreview(null);
    } finally {
      setLoading(null);
    }
  }

  async function handleLogPreview() {
    setLoading("logPreview");
    setError(null);
    setNotice(null);
    setLogResult(null);
    try {
      setLogPreview(await previewLogImport(toLogPayload(logForm)));
    } catch (caughtError) {
      setError(errorMessage(caughtError, "Log preview failed."));
      setLogPreview(null);
    } finally {
      setLoading(null);
    }
  }

  async function handleLogImport() {
    setLoading("logImport");
    setError(null);
    setNotice(null);
    try {
      const response = await importLogs(toLogPayload(logForm));
      setLogResult(response);
      setLogPreview(null);
      await refreshConnectors();
    } catch (caughtError) {
      setError(errorMessage(caughtError, "Log import failed."));
    } finally {
      setLoading(null);
    }
  }

  async function handleClearLogEvents() {
    const confirmed = window.confirm(
      "This will remove imported log events from MindOS memory. Other memory will not be deleted. Continue?",
    );
    if (!confirmed) {
      return;
    }
    setLoading("clearLogs");
    setError(null);
    setNotice(null);
    try {
      const response = await clearLogEvents();
      setLogPreview(null);
      setLogResult(null);
      await refreshConnectors();
      setNotice(response.deleted_events === 0 ? "No log events to clear." : `Cleared ${response.deleted_events} log events.`);
    } catch (caughtError) {
      setError(errorMessage(caughtError, "Could not clear log events."));
    } finally {
      setLoading(null);
    }
  }

  async function handleGitPreview() {
    setLoading("gitPreview");
    setError(null);
    setNotice(null);
    setGitResult(null);
    try {
      setGitPreview(await previewGitImport(toGitPayload(gitForm)));
    } catch (caughtError) {
      setError(errorMessage(caughtError, "Git preview failed."));
      setGitPreview(null);
    } finally {
      setLoading(null);
    }
  }

  async function handleGitImport() {
    setLoading("gitImport");
    setError(null);
    setNotice(null);
    try {
      const response = await importGitRepo(toGitPayload(gitForm));
      setGitResult(response);
      setGitPreview(null);
      await refreshConnectors();
    } catch (caughtError) {
      setError(errorMessage(caughtError, "Git import failed."));
    } finally {
      setLoading(null);
    }
  }

  async function handleImport() {
    setLoading("import");
    setError(null);
    setNotice(null);
    try {
      const response = await importFiles(toPayload(form));
      setResult(response);
      setPreview(null);
      await refreshConnectors();
    } catch (caughtError) {
      setError(errorMessage(caughtError, "Import failed."));
    } finally {
      setLoading(null);
    }
  }

  const fileSystem = connectors.find((connector) => connector.name === "file_system");
  const logs = connectors.find((connector) => connector.name === "logs");
  const git = connectors.find((connector) => connector.name === "git");
  const otherConnectors = connectors.filter((connector) => !["file_system", "logs", "git"].includes(connector.name));

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-app-text">Connectors</h1>
          <p className="mt-2 text-sm text-app-muted">Choose what local sources MindOS can learn from.</p>
        </div>
        <Button variant="ghost" onClick={() => void refreshConnectors()} loading={loading === "connectors"}>
          <RefreshCw size={16} />
          Refresh
        </Button>
      </header>

      {error ? <StatusMessage message={error} variant="danger" /> : null}
      {notice ? <StatusMessage message={notice} variant="success" /> : null}

      <div className="grid grid-cols-[1fr_420px] gap-4">
        <div className="space-y-4">
          {fileSystem ? (
            <ConnectorCard connector={fileSystem} active actionLabel="Import Folder" onImport={() => setPanelOpen("files")} />
          ) : (
            <Card>
              <p className="text-sm text-app-muted">File System connector is unavailable.</p>
            </Card>
          )}

          {logs ? (
            <ConnectorCard
              connector={logs}
              active
              actionLabel="Import Log File"
              onImport={() => setPanelOpen("logs")}
              clearLabel="Clear Log Events"
              onClear={() => void handleClearLogEvents()}
              clearLoading={loading === "clearLogs"}
              zeroStateLabel="No log events imported yet."
            />
          ) : null}

          {git ? (
            <ConnectorCard connector={git} active actionLabel="Import Repository" onImport={() => setPanelOpen("git")} />
          ) : null}

          <div className="grid grid-cols-2 gap-4">
            {otherConnectors.map((connector) => (
              <ConnectorCard key={connector.name} connector={connector} />
            ))}
          </div>
        </div>

        {panelOpen === "files" ? (
          <ImportPanel
            form={form}
            setForm={setForm}
            loading={loading}
            preview={preview}
            result={result}
            onClose={() => setPanelOpen(null)}
            onPreview={handlePreview}
            onImport={handleImport}
          />
        ) : panelOpen === "logs" ? (
          <LogImportPanel
            form={logForm}
            setForm={setLogForm}
            loading={loading}
            preview={logPreview}
            result={logResult}
            onClose={() => setPanelOpen(null)}
            onPreview={handleLogPreview}
            onImport={handleLogImport}
          />
        ) : panelOpen === "git" ? (
          <GitImportPanel
            form={gitForm}
            setForm={setGitForm}
            loading={loading}
            preview={gitPreview}
            result={gitResult}
            onClose={() => setPanelOpen(null)}
            onPreview={handleGitPreview}
            onImport={handleGitImport}
          />
        ) : (
          <Card className="min-h-72">
            <div className="flex h-full flex-col items-center justify-center text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-md border border-violet-500/30 bg-violet-500/10 text-violet-300">
                <Cable size={24} />
              </div>
              <h2 className="mt-4 text-base font-semibold text-app-text">No connector selected</h2>
              <p className="mt-2 max-w-sm text-sm leading-6 text-app-muted">Start with a manual File System, Logs, or Local Git import.</p>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}

function ConnectorCard({
  connector,
  active = false,
  actionLabel = "Import",
  onImport,
  clearLabel,
  onClear,
  clearLoading = false,
  zeroStateLabel,
}: {
  connector: Connector;
  active?: boolean;
  actionLabel?: string;
  onImport?: () => void;
  clearLabel?: string;
  onClear?: () => void;
  clearLoading?: boolean;
  zeroStateLabel?: string;
}) {
  const eventsCount = connector.events_count ?? 0;

  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-md border border-violet-500/30 bg-violet-500/10 text-violet-300">
            <FolderOpen size={20} />
          </div>
          <div>
            <h2 className="text-base font-semibold text-app-text">{connector.display_name ?? connector.name}</h2>
            <p className="mt-2 text-sm leading-6 text-app-muted">{connector.description}</p>
          </div>
        </div>
        <Badge variant={connector.status === "available" ? "success" : "default"}>{connector.status}</Badge>
      </div>

      {active ? (
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <Badge variant="info">events: {eventsCount}</Badge>
          {connector.last_event_at && eventsCount > 0 ? <Badge>last: {formatTimestamp(connector.last_event_at)}</Badge> : null}
          {eventsCount === 0 && zeroStateLabel ? <span className="text-xs text-app-muted">{zeroStateLabel}</span> : null}
          <Button variant="primary" onClick={onImport}>
            {actionLabel}
          </Button>
          {onClear && clearLabel ? (
            <Button variant="danger" onClick={onClear} loading={clearLoading}>
              {clearLabel}
            </Button>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}

function ImportPanel({
  form,
  setForm,
  loading,
  preview,
  result,
  onClose,
  onPreview,
  onImport,
}: {
  form: ImportForm;
  setForm: (updater: ImportForm | ((current: ImportForm) => ImportForm)) => void;
  loading: string | null;
  preview: FilePreviewResult | null;
  result: FileImportResult | null;
  onClose: () => void;
  onPreview: () => void;
  onImport: () => void;
}) {
  return (
    <Card className="max-h-[calc(100vh-7rem)] overflow-auto">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-app-text">Import Folder</h2>
          <p className="mt-2 text-sm leading-6 text-app-muted">
            MindOS will only read files from the folder path you provide. Files stay local and are stored in your local
            MindOS database.
          </p>
        </div>
        <button type="button" onClick={onClose} className="rounded-md p-1 text-app-muted hover:bg-zinc-800 hover:text-app-text">
          <X size={18} />
        </button>
      </div>

      <div className="mt-5 space-y-4">
        <LabeledInput
          label="Folder path"
          value={form.folderPath}
          placeholder="C:\\Users\\YourName\\Projects\\my-project"
          onChange={(value) => setForm((current) => ({ ...current, folderPath: value }))}
        />
        <label className="flex items-center gap-3 text-sm text-app-text">
          <input
            type="checkbox"
            checked={form.recursive}
            onChange={(event) => setForm((current) => ({ ...current, recursive: event.target.checked }))}
            className="h-4 w-4 accent-violet-600"
          />
          Recursive
        </label>
        <div className="grid grid-cols-2 gap-3">
          <LabeledInput
            label="Max files"
            type="number"
            value={String(form.maxFiles)}
            onChange={(value) => setForm((current) => ({ ...current, maxFiles: Number(value) }))}
          />
          <LabeledInput
            label="Max file size KB"
            type="number"
            value={String(form.maxFileSizeKb)}
            onChange={(value) => setForm((current) => ({ ...current, maxFileSizeKb: Number(value) }))}
          />
        </div>
        <LabeledInput
          label="Allowed extensions"
          value={form.allowedExtensions}
          placeholder=".py,.ts,.tsx,.md,.json"
          onChange={(value) => setForm((current) => ({ ...current, allowedExtensions: value }))}
        />

        <div className="flex gap-3">
          <Button variant="secondary" onClick={onPreview} loading={loading === "preview"} disabled={!form.folderPath.trim()}>
            Preview
          </Button>
          <Button variant="primary" onClick={onImport} loading={loading === "import"} disabled={!form.folderPath.trim()}>
            Import
          </Button>
        </div>
      </div>

      {preview ? <PreviewBlock preview={preview} /> : null}
      {result ? <ResultBlock result={result} /> : null}
    </Card>
  );
}

function LogImportPanel({
  form,
  setForm,
  loading,
  preview,
  result,
  onClose,
  onPreview,
  onImport,
}: {
  form: LogImportForm;
  setForm: (updater: LogImportForm | ((current: LogImportForm) => LogImportForm)) => void;
  loading: string | null;
  preview: LogPreviewResult | null;
  result: LogImportResult | null;
  onClose: () => void;
  onPreview: () => void;
  onImport: () => void;
}) {
  return (
    <Card className="max-h-[calc(100vh-7rem)] overflow-auto">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-app-text">Import Log File</h2>
          <p className="mt-2 text-sm leading-6 text-app-muted">
            MindOS reads only the log file path you provide. Logs stay local and are stored in your local MindOS database.
          </p>
        </div>
        <button type="button" onClick={onClose} className="rounded-md p-1 text-app-muted hover:bg-zinc-800 hover:text-app-text">
          <X size={18} />
        </button>
      </div>

      <div className="mt-5 space-y-4">
        <LabeledInput
          label="Log file path"
          value={form.filePath}
          placeholder="C:\\Users\\YourName\\logs\\application.log"
          onChange={(value) => setForm((current) => ({ ...current, filePath: value }))}
        />
        <LabeledInput
          label="Max lines"
          type="number"
          value={String(form.maxLines)}
          onChange={(value) => setForm((current) => ({ ...current, maxLines: Number(value) }))}
        />
        <label className="flex items-center gap-3 text-sm text-app-text">
          <input
            type="checkbox"
            checked={form.onlyErrors}
            onChange={(event) => setForm((current) => ({ ...current, onlyErrors: event.target.checked }))}
            className="h-4 w-4 accent-violet-600"
          />
          Only errors
        </label>
        <label className="flex items-center gap-3 text-sm text-app-text">
          <input
            type="checkbox"
            checked={form.groupSimilar}
            onChange={(event) => setForm((current) => ({ ...current, groupSimilar: event.target.checked }))}
            className="h-4 w-4 accent-violet-600"
          />
          Group similar logs
        </label>

        <div className="flex gap-3">
          <Button variant="secondary" onClick={onPreview} loading={loading === "logPreview"} disabled={!form.filePath.trim()}>
            Preview
          </Button>
          <Button variant="primary" onClick={onImport} loading={loading === "logImport"} disabled={!form.filePath.trim()}>
            Import
          </Button>
        </div>
      </div>

      {preview ? <LogPreviewBlock preview={preview} /> : null}
      {result ? <LogResultBlock result={result} /> : null}
    </Card>
  );
}

function GitImportPanel({
  form,
  setForm,
  loading,
  preview,
  result,
  onClose,
  onPreview,
  onImport,
}: {
  form: GitImportForm;
  setForm: (updater: GitImportForm | ((current: GitImportForm) => GitImportForm)) => void;
  loading: string | null;
  preview: GitPreviewResult | null;
  result: GitImportResult | null;
  onClose: () => void;
  onPreview: () => void;
  onImport: () => void;
}) {
  return (
    <Card className="max-h-[calc(100vh-7rem)] overflow-auto">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-app-text">Import Git Repository</h2>
          <p className="mt-2 text-sm leading-6 text-app-muted">
            MindOS only runs read-only Git commands for import. It will not commit, push, pull, checkout, reset, or modify your repository.
          </p>
        </div>
        <button type="button" onClick={onClose} className="rounded-md p-1 text-app-muted hover:bg-zinc-800 hover:text-app-text">
          <X size={18} />
        </button>
      </div>

      <div className="mt-5 space-y-4">
        <LabeledInput
          label="Repository path"
          value={form.repoPath}
          placeholder="C:\\Users\\YourName\\Projects\\my-project"
          onChange={(value) => setForm((current) => ({ ...current, repoPath: value }))}
        />
        <LabeledInput
          label="Max commits"
          type="number"
          value={String(form.maxCommits)}
          onChange={(value) => setForm((current) => ({ ...current, maxCommits: Number(value) }))}
        />
        <label className="flex items-center gap-3 text-sm text-app-text">
          <input
            type="checkbox"
            checked={form.includeDiffSummary}
            onChange={(event) => setForm((current) => ({ ...current, includeDiffSummary: event.target.checked }))}
            className="h-4 w-4 accent-violet-600"
          />
          Include diff summary
        </label>
        <label className="flex items-center gap-3 text-sm text-app-text">
          <input
            type="checkbox"
            checked={form.includeStatus}
            onChange={(event) => setForm((current) => ({ ...current, includeStatus: event.target.checked }))}
            className="h-4 w-4 accent-violet-600"
          />
          Include working tree status
        </label>

        <div className="flex gap-3">
          <Button variant="secondary" onClick={onPreview} loading={loading === "gitPreview"} disabled={!form.repoPath.trim()}>
            Preview
          </Button>
          <Button variant="primary" onClick={onImport} loading={loading === "gitImport"} disabled={!form.repoPath.trim()}>
            Import
          </Button>
        </div>
      </div>

      {preview ? <GitPreviewBlock preview={preview} /> : null}
      {result ? <GitResultBlock result={result} /> : null}
    </Card>
  );
}

function PreviewBlock({ preview }: { preview: FilePreviewResult }) {
  return (
    <div className="mt-6 space-y-3">
      <div className="flex flex-wrap gap-2">
        <Badge variant="info">candidates: {preview.total_candidates}</Badge>
        <Badge>skipped: {preview.skipped.length}</Badge>
      </div>
      <CompactList title="Preview files" items={preview.preview_files} />
      <CompactList title="Skipped" items={preview.skipped.slice(0, 20)} />
    </div>
  );
}

function ResultBlock({ result }: { result: FileImportResult }) {
  return (
    <div className="mt-6 space-y-3">
      <StatusMessage message={result.message} variant={result.failed_count > 0 ? "warning" : "success"} />
      <div className="flex flex-wrap gap-2">
        <Badge variant="success">imported: {result.imported_count}</Badge>
        <Badge>skipped: {result.skipped_count}</Badge>
        <Badge variant={result.failed_count > 0 ? "danger" : "default"}>failed: {result.failed_count}</Badge>
        <Badge variant="info">event IDs: {result.events_created.length}</Badge>
      </div>
      <CompactList title="Skipped" items={result.skipped.slice(0, 20)} />
      <CompactList title="Failed" items={result.failed.slice(0, 20)} />
    </div>
  );
}

function LogPreviewBlock({ preview }: { preview: LogPreviewResult }) {
  return (
    <div className="mt-6 space-y-3">
      <div className="flex flex-wrap gap-2">
        <Badge variant="info">scanned: {preview.total_lines_scanned}</Badge>
        <Badge variant="success">matched: {preview.matched_lines}</Badge>
      </div>
      <div className="space-y-2">
        {preview.preview.map((line) => (
          <div key={line.line_number} className="rounded-md border border-app-border bg-zinc-950 px-3 py-2">
            <div className="flex items-center gap-2">
              <Badge variant={line.level === "ERROR" || line.level === "TRACEBACK" ? "danger" : line.level === "WARNING" ? "warning" : "default"}>
                {line.level}
              </Badge>
              <span className="text-xs text-app-muted">line {line.line_number}</span>
              {line.timestamp ? <span className="ml-auto text-xs text-app-muted">{line.timestamp}</span> : null}
            </div>
            <p className="mt-2 text-sm leading-6 text-app-text">{line.message}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function LogResultBlock({ result }: { result: LogImportResult }) {
  return (
    <div className="mt-6 space-y-3">
      <StatusMessage message={result.message} variant={result.failed_count > 0 ? "warning" : "success"} />
      <div className="flex flex-wrap gap-2">
        <Badge variant="success">imported: {result.imported_count}</Badge>
        <Badge>skipped: {result.skipped_count}</Badge>
        <Badge variant={result.failed_count > 0 ? "danger" : "default"}>failed: {result.failed_count}</Badge>
        <Badge variant="info">groups: {result.groups_created}</Badge>
        <Badge>event IDs: {result.events_created.length}</Badge>
      </div>
    </div>
  );
}

function GitPreviewBlock({ preview }: { preview: GitPreviewResult }) {
  return (
    <div className="mt-6 space-y-3">
      <div className="flex flex-wrap gap-2">
        <Badge variant="info">{preview.repo_name}</Badge>
        <Badge>branch: {preview.current_branch ?? "detached"}</Badge>
        <Badge>commits: {preview.recent_commits.length}</Badge>
      </div>
      <div className="flex flex-wrap gap-2">
        {Object.entries(preview.status_summary).map(([key, value]) => (
          <Badge key={key}>
            {key}: {value}
          </Badge>
        ))}
      </div>
      <div className="space-y-2">
        {preview.recent_commits.map((commit) => (
          <div key={commit.hash} className="rounded-md border border-app-border bg-zinc-950 px-3 py-2">
            <div className="flex items-center gap-2">
              <Badge variant="info">{commit.short_hash}</Badge>
              <span className="ml-auto text-xs text-app-muted">{formatTimestamp(commit.date)}</span>
            </div>
            <p className="mt-2 text-sm font-medium text-app-text">{commit.message}</p>
            <p className="mt-1 text-xs text-app-muted">{commit.author}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function GitResultBlock({ result }: { result: GitImportResult }) {
  return (
    <div className="mt-6 space-y-3">
      <StatusMessage message={result.message} variant={result.failed_count > 0 ? "warning" : "success"} />
      <div className="flex flex-wrap gap-2">
        <Badge variant="success">imported: {result.imported_count}</Badge>
        <Badge>skipped: {result.skipped_count}</Badge>
        <Badge variant={result.failed_count > 0 ? "danger" : "default"}>failed: {result.failed_count}</Badge>
        <Badge>event IDs: {result.events_created.length}</Badge>
      </div>
    </div>
  );
}

function CompactList({ title, items }: { title: string; items: Array<Record<string, string | number>> }) {
  if (items.length === 0) {
    return null;
  }
  return (
    <div>
      <h3 className="text-xs font-medium uppercase text-app-muted">{title}</h3>
      <div className="mt-2 space-y-2">
        {items.map((item, index) => (
          <div key={`${String(item.path ?? item.name)}-${index}`} className="rounded-md border border-app-border bg-zinc-950 px-3 py-2">
            <p className="truncate text-sm text-app-text">{String(item.name ?? item.path)}</p>
            <p className="mt-1 truncate text-xs text-app-muted">{String(item.path ?? "")}</p>
            {"reason" in item ? <Badge>{String(item.reason)}</Badge> : null}
            {"size_kb" in item ? <p className="mt-1 text-xs text-app-muted">{String(item.size_kb)} KB</p> : null}
          </div>
        ))}
      </div>
    </div>
  );
}

function LabeledInput({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <label className="block text-xs font-medium uppercase text-app-muted">
      {label}
      <Input className="mt-2" type={type} value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function toPayload(form: ImportForm): FileImportPayload {
  return {
    folder_path: form.folderPath.trim(),
    recursive: form.recursive,
    max_files: clampNumber(form.maxFiles, 1, 1000),
    max_file_size_kb: clampNumber(form.maxFileSizeKb, 1, 2048),
    allowed_extensions: parseExtensions(form.allowedExtensions),
  };
}

function toLogPayload(form: LogImportForm): LogImportPayload {
  return {
    file_path: form.filePath.trim(),
    max_lines: clampNumber(form.maxLines, 1, 10000),
    only_errors: form.onlyErrors,
    group_similar: form.groupSimilar,
  };
}

function toGitPayload(form: GitImportForm): GitImportPayload {
  return {
    repo_path: form.repoPath.trim(),
    max_commits: clampNumber(form.maxCommits, 1, 500),
    include_diff_summary: form.includeDiffSummary,
    include_status: form.includeStatus,
  };
}

function parseExtensions(value: string) {
  const extensions = value
    .split(",")
    .map((extension) => extension.trim())
    .filter(Boolean);
  return extensions.length > 0 ? extensions : null;
}

function clampNumber(value: number, min: number, max: number) {
  if (Number.isNaN(value)) {
    return min;
  }
  return Math.max(min, Math.min(max, value));
}

function errorMessage(error: unknown, fallback: string) {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    return typeof detail === "string" ? detail : fallback;
  }
  return fallback;
}

function StatusMessage({ message, variant }: { message: string; variant: "success" | "warning" | "danger" }) {
  const classes = {
    success: "border-emerald-500/30 bg-emerald-500/10 text-emerald-200",
    warning: "border-amber-500/30 bg-amber-500/10 text-amber-100",
    danger: "border-red-500/30 bg-red-500/10 text-red-200",
  };
  return <div className={`rounded-md border px-4 py-3 text-sm ${classes[variant]}`}>{message}</div>;
}

function formatTimestamp(value: string) {
  return new Date(value).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
