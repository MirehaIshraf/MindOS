import axios from "axios";
import { Cable, FolderOpen, RefreshCw, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "../components/shared/Badge";
import { Button } from "../components/shared/Button";
import { Card } from "../components/shared/Card";
import { Input } from "../components/shared/Input";
import {
  clearConnectorSourceEvents,
  clearFileSystemEvents,
  clearLogEvents,
  clearGitEvents,
  createConnectorSource,
  deleteConnectorSource,
  getConnectors,
  getConnectorSources,
  getImportRuns,
  importFiles,
  importGitRepo,
  importLogs,
  previewFileImport,
  previewGitImport,
  previewLogImport,
  runConnectorSourceImport,
  updateConnectorSource,
} from "../services/api";
import type {
  Connector,
  ConnectorSource,
  FileImportPayload,
  FileImportResult,
  FilePreviewResult,
  GitImportPayload,
  GitImportResult,
  GitPreviewResult,
  ImportRun,
  LogImportPayload,
  LogImportResult,
  LogPreviewResult,
  ConnectorSourceUpdateRequest,
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

const emptySavedSourceForm = {
  name: "",
  path: "",
  recursive: true,
  maxFiles: 100,
  maxFileSizeKb: 256,
  allowedExtensions: "",
  maxLines: 1000,
  onlyErrors: false,
  groupSimilar: true,
  maxCommits: 50,
  includeDiffSummary: true,
  includeStatus: true,
  enabled: true,
};

type SavedSourceForm = typeof emptySavedSourceForm;

export function ConnectorsPage() {
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [panelOpen, setPanelOpen] = useState<"files" | "logs" | "git" | "save" | null>(null);
  const [saveType, setSaveType] = useState<"file_system" | "logs" | "git">("file_system");
  const [form, setForm] = useState<ImportForm>(emptyForm);
  const [logForm, setLogForm] = useState<LogImportForm>(emptyLogForm);
  const [gitForm, setGitForm] = useState<GitImportForm>(emptyGitForm);
  const [preview, setPreview] = useState<FilePreviewResult | null>(null);
  const [result, setResult] = useState<FileImportResult | null>(null);
  const [logPreview, setLogPreview] = useState<LogPreviewResult | null>(null);
  const [logResult, setLogResult] = useState<LogImportResult | null>(null);
  const [gitPreview, setGitPreview] = useState<GitPreviewResult | null>(null);
  const [gitResult, setGitResult] = useState<GitImportResult | null>(null);
  const [savedSources, setSavedSources] = useState<ConnectorSource[]>([]);
  const [sourceFilter, setSourceFilter] = useState("all");
  const [editingSource, setEditingSource] = useState<ConnectorSource | null>(null);
  const [importRuns, setImportRuns] = useState<ImportRun[]>([]);
  const [saveForm, setSaveForm] = useState<SavedSourceForm>(emptySavedSourceForm);
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
      const [response, sourcesResponse, runsResponse] = await Promise.all([
        getConnectors(),
        getConnectorSources(),
        getImportRuns({ limit: 20 }),
      ]);
      setConnectors(response.connectors);
      setSavedSources(sourcesResponse.sources);
      setImportRuns(runsResponse.runs);
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

  async function handleClearGitEvents() {
    const confirmed = window.confirm(
      "This will remove imported Git events from MindOS memory. Other memory will not be deleted. Continue?",
    );
    if (!confirmed) {
      return;
    }
    setLoading("clearGit");
    setError(null);
    setNotice(null);
    try {
      const response = await clearGitEvents();
      setGitPreview(null);
      setGitResult(null);
      await refreshConnectors();
      setNotice(response.deleted_events === 0 ? "No Git events to clear." : `Cleared ${response.deleted_events} Git events.`);
    } catch (caughtError) {
      setError(errorMessage(caughtError, "Could not clear Git events."));
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

  async function handleClearFileSystemEvents() {
    const confirmed = window.confirm(
      "This will remove imported file/folder events from MindOS memory. Other memory will not be deleted. Continue?",
    );
    if (!confirmed) {
      return;
    }
    setLoading("clearFiles");
    setError(null);
    setNotice(null);
    try {
      const response = await clearFileSystemEvents();
      setPreview(null);
      setResult(null);
      await refreshConnectors();
      setNotice(response.deleted_events === 0 ? "No file events to clear." : `Cleared ${response.deleted_events} file events.`);
    } catch (caughtError) {
      setError(errorMessage(caughtError, "Could not clear file events."));
    } finally {
      setLoading(null);
    }
  }

  function openSavePanel(connectorType: "file_system" | "logs" | "git", source?: ConnectorSource) {
    setSaveType(connectorType);
    setEditingSource(source ?? null);
    setSaveForm(sourceToForm(source, connectorType));
    setPanelOpen("save");
  }

  async function handleSaveSource() {
    setLoading("saveSource");
    setError(null);
    setNotice(null);
    try {
      const payload = sourcePayload(saveType, saveForm);
      if (editingSource) {
        await updateConnectorSource(editingSource.id, updateSourcePayload(payload));
        setNotice("Saved source updated.");
      } else {
        await createConnectorSource(payload);
        setNotice("Saved source created.");
      }
      setEditingSource(null);
      setPanelOpen(null);
      await refreshConnectors();
    } catch (caughtError) {
      setError(errorMessage(caughtError, "Could not save source."));
    } finally {
      setLoading(null);
    }
  }

  async function handleRunSource(source: ConnectorSource) {
    setLoading(`run:${source.id}`);
    setError(null);
    setNotice(null);
    try {
      const response = await runConnectorSourceImport(source.id);
      setNotice(response.import_run.message);
      await refreshConnectors();
    } catch (caughtError) {
      setError(errorMessage(caughtError, "Could not re-import saved source."));
    } finally {
      setLoading(null);
    }
  }

  async function handleDeleteSource(source: ConnectorSource) {
    if (!window.confirm(`Delete saved source "${source.name}"? Imported memory events will remain.`)) {
      return;
    }
    setLoading(`delete:${source.id}`);
    setError(null);
    try {
      await deleteConnectorSource(source.id);
      setNotice("Saved source deleted.");
      await refreshConnectors();
    } catch (caughtError) {
      setError(errorMessage(caughtError, "Could not delete saved source."));
    } finally {
      setLoading(null);
    }
  }

  async function handleClearSourceEvents(source: ConnectorSource) {
    if (!window.confirm(`Clear imported events for "${source.name}"? Other memory will not be deleted.`)) {
      return;
    }
    setLoading(`clearSource:${source.id}`);
    setError(null);
    try {
      const response = await clearConnectorSourceEvents(source.id);
      setNotice(response.deleted_events === 0 ? "No events to clear for this source." : `Cleared ${response.deleted_events} events for this source.`);
      await refreshConnectors();
    } catch (caughtError) {
      setError(errorMessage(caughtError, "Could not clear source events."));
    } finally {
      setLoading(null);
    }
  }

  const fileSystem = connectors.find((connector) => connector.name === "file_system");
  const logs = connectors.find((connector) => connector.name === "logs");
  const git = connectors.find((connector) => connector.name === "git");
  const otherConnectors = connectors.filter((connector) => !["file_system", "logs", "git"].includes(connector.name));
  const visibleSources = sourceFilter === "all" ? savedSources : savedSources.filter((source) => source.connector_type === sourceFilter);

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
            <ConnectorCard
              connector={fileSystem}
              active
              actionLabel="Import Folder"
              onImport={() => setPanelOpen("files")}
              clearLabel="Clear File Events"
              onClear={() => void handleClearFileSystemEvents()}
              clearLoading={loading === "clearFiles"}
              zeroStateLabel="No file events imported yet."
              saveLabel="Save Folder Source"
              onSave={() => openSavePanel("file_system")}
            />
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
              saveLabel="Save Log Source"
              onSave={() => openSavePanel("logs")}
            />
          ) : null}

          {git ? (
            <ConnectorCard
              connector={git}
              active
              actionLabel="Import Repository"
              onImport={() => setPanelOpen("git")}
              clearLabel="Clear Git Events"
              onClear={() => void handleClearGitEvents()}
              clearLoading={loading === "clearGit"}
              zeroStateLabel="No Git events imported yet."
              saveLabel="Save Git Source"
              onSave={() => openSavePanel("git")}
            />
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
        ) : panelOpen === "save" ? (
          <SaveSourcePanel
            connectorType={saveType}
            form={saveForm}
            setForm={setSaveForm}
            editing={Boolean(editingSource)}
            loading={loading === "saveSource"}
            onClose={() => {
              setPanelOpen(null);
              setEditingSource(null);
            }}
            onSave={handleSaveSource}
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

        <Card>
          <h2 className="text-base font-semibold text-app-text">Upcoming Collectors</h2>
          <p className="mt-2 text-sm leading-6 text-app-muted">
            These clients will send events into MindOS through the local external ingestion API. They are planned and do not run automatically.
          </p>
          <div className="mt-4 grid gap-3 lg:grid-cols-3">
            <PlannedCollectorCard
              title="VSCode Extension"
              description="Collects file opens, saves, workspace activity, terminal commands, and debug activity."
            />
            <PlannedCollectorCard
              title="Browser Extension"
              description="Collects research pages, searches, saved tabs, and browsing context with user control."
            />
            <PlannedCollectorCard
              title="Activity Tracker"
              description="Tracks active app/window sessions locally to summarize work patterns."
            />
          </div>
        </Card>

        <Card>
          <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-app-text">Saved Sources</h2>
            <p className="mt-2 text-sm leading-6 text-app-muted">
              Saved sources are local paths stored in your local MindOS database. MindOS only imports them when you click Re-import. Live watching is not enabled yet.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {["all", "file_system", "logs", "git"].map((filter) => (
              <button key={filter} type="button" onClick={() => setSourceFilter(filter)}>
                <Badge variant={sourceFilter === filter ? "info" : "default"}>{filter === "all" ? "All" : formatConnectorType(filter)}</Badge>
              </button>
            ))}
          </div>
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          {visibleSources.length === 0 ? (
            <p className="text-sm text-app-muted">No saved sources yet.</p>
          ) : (
            visibleSources.map((source) => (
              <SavedSourceCard
                key={source.id}
                source={source}
                loading={loading}
                onRun={() => void handleRunSource(source)}
                onEdit={() => openSavePanel(source.connector_type as "file_system" | "logs" | "git", source)}
                onDelete={() => void handleDeleteSource(source)}
                onClear={() => void handleClearSourceEvents(source)}
              />
            ))
          )}
        </div>
      </Card>

      <Card>
        <h2 className="text-base font-semibold text-app-text">Recent Import Runs</h2>
        <div className="mt-4 space-y-2">
          {importRuns.length === 0 ? (
            <p className="text-sm text-app-muted">No import runs yet.</p>
          ) : (
            importRuns.map((run) => <ImportRunRow key={run.id} run={run} sources={savedSources} />)
          )}
        </div>
      </Card>
    </div>
  );
}

  function ConnectorCard({
  connector,
  active = false,
  actionLabel = "Import",
  onImport,
  saveLabel,
  onSave,
  clearLabel,
  onClear,
  clearLoading = false,
  zeroStateLabel,
}: {
  connector: Connector;
  active?: boolean;
  actionLabel?: string;
  onImport?: () => void;
  saveLabel?: string;
  onSave?: () => void;
  clearLabel?: string;
  onClear?: () => void;
  clearLoading?: boolean;
  zeroStateLabel?: string;
}) {
  const eventsCount = connector.events_count ?? 0;
  const savedSourcesCount = connector.saved_sources_count ?? 0;

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
          <Badge>saved sources: {savedSourcesCount}</Badge>
          {connector.last_event_at && eventsCount > 0 ? <Badge>last: {formatTimestamp(connector.last_event_at)}</Badge> : null}
          {connector.last_import_at ? <Badge>last import: {formatTimestamp(connector.last_import_at)}</Badge> : null}
          {connector.last_import_status ? <Badge>{connector.last_import_status}</Badge> : null}
          {eventsCount === 0 && zeroStateLabel ? <span className="text-xs text-app-muted">{zeroStateLabel}</span> : null}
          <Button variant="primary" onClick={onImport}>
            {actionLabel}
          </Button>
          {onSave && saveLabel ? (
            <Button variant="secondary" onClick={onSave}>
              {saveLabel}
            </Button>
          ) : null}
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

  function PlannedCollectorCard({ title, description }: { title: string; description: string }) {
    return (
      <div className="rounded-md border border-app-border bg-zinc-950 px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-sm font-semibold text-app-text">{title}</h3>
          <Badge variant="default">Planned</Badge>
        </div>
        <p className="mt-2 text-sm leading-6 text-app-muted">{description}</p>
      </div>
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

function SaveSourcePanel({
  connectorType,
  form,
  setForm,
  editing,
  loading,
  onClose,
  onSave,
}: {
  connectorType: "file_system" | "logs" | "git";
  form: SavedSourceForm;
  setForm: (updater: SavedSourceForm | ((current: SavedSourceForm) => SavedSourceForm)) => void;
  editing: boolean;
  loading: boolean;
  onClose: () => void;
  onSave: () => void;
}) {
  return (
    <Card className="max-h-[calc(100vh-7rem)] overflow-auto">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-app-text">{editing ? "Edit Saved Source" : `Save ${formatConnectorType(connectorType)} Source`}</h2>
          <p className="mt-2 text-sm leading-6 text-app-muted">
            Saved sources are local paths. MindOS only imports them when you click Re-import.
          </p>
        </div>
        <button type="button" onClick={onClose} className="rounded-md p-1 text-app-muted hover:bg-zinc-800 hover:text-app-text">
          <X size={18} />
        </button>
      </div>

      <div className="mt-5 space-y-4">
        <LabeledInput
          label="Name"
          value={form.name}
          placeholder={connectorType === "git" ? "MindOS Repo" : connectorType === "logs" ? "Auth Service Log" : "SonoSync Backend"}
          onChange={(value) => setForm((current) => ({ ...current, name: value }))}
        />
        <LabeledInput
          label={connectorType === "logs" ? "Log file path" : connectorType === "git" ? "Repository path" : "Folder path"}
          value={form.path}
          placeholder={connectorType === "logs" ? "C:\\Users\\YourName\\logs\\application.log" : "C:\\Users\\YourName\\Projects\\my-project"}
          onChange={(value) => setForm((current) => ({ ...current, path: value }))}
        />
        <label className="flex items-center gap-3 text-sm text-app-text">
          <input
            type="checkbox"
            checked={form.enabled}
            onChange={(event) => setForm((current) => ({ ...current, enabled: event.target.checked }))}
            className="h-4 w-4 accent-violet-600"
          />
          Enabled
        </label>

        {connectorType === "file_system" ? (
          <>
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
          </>
        ) : null}

        {connectorType === "logs" ? (
          <>
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
          </>
        ) : null}

        {connectorType === "git" ? (
          <>
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
          </>
        ) : null}

        <div className="flex gap-3">
          <Button variant="primary" onClick={onSave} loading={loading} disabled={!form.name.trim() || !form.path.trim()}>
            {editing ? "Save Changes" : "Save Source"}
          </Button>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </div>
    </Card>
  );
}

function SavedSourceCard({
  source,
  loading,
  onRun,
  onEdit,
  onDelete,
  onClear,
}: {
  source: ConnectorSource;
  loading: string | null;
  onRun: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onClear: () => void;
}) {
  return (
    <div className="rounded-md border border-app-border bg-zinc-950 px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-sm font-semibold text-app-text">{source.name}</h3>
            <Badge variant="info">{formatConnectorType(source.connector_type)}</Badge>
            <Badge variant={source.enabled ? "success" : "default"}>{source.enabled ? "enabled" : "disabled"}</Badge>
          </div>
          <p className="mt-2 truncate text-xs text-app-muted">{source.path}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {source.last_import_status ? <Badge>{source.last_import_status}</Badge> : <Badge>not imported yet</Badge>}
            {source.last_import_at ? <Badge>last: {formatTimestamp(source.last_import_at)}</Badge> : null}
          </div>
          {source.last_import_message ? <p className="mt-2 text-xs leading-5 text-app-muted">{source.last_import_message}</p> : null}
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <Button variant="primary" onClick={onRun} loading={loading === `run:${source.id}`}>
          Re-import
        </Button>
        <Button variant="secondary" onClick={onEdit}>
          Edit
        </Button>
        <Button variant="secondary" onClick={onClear} loading={loading === `clearSource:${source.id}`}>
          Clear Events
        </Button>
        <Button variant="danger" onClick={onDelete} loading={loading === `delete:${source.id}`}>
          Delete
        </Button>
      </div>
    </div>
  );
}

function ImportRunRow({ run, sources }: { run: ImportRun; sources: ConnectorSource[] }) {
  const source = run.source_id ? sources.find((item) => item.id === run.source_id) : null;
  return (
    <div className="rounded-md border border-app-border bg-zinc-950 px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={run.status === "success" ? "success" : run.status === "partial" ? "warning" : "danger"}>{run.status}</Badge>
        <Badge>{formatConnectorType(run.connector_type)}</Badge>
        <span className="text-sm font-medium text-app-text">{source?.name ?? "Direct import"}</span>
        <span className="ml-auto text-xs text-app-muted">{formatTimestamp(run.completed_at)}</span>
      </div>
      <p className="mt-2 truncate text-xs text-app-muted">{run.path}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Badge variant="success">imported: {run.imported_count}</Badge>
        <Badge>skipped: {run.skipped_count}</Badge>
        <Badge variant={run.failed_count > 0 ? "danger" : "default"}>failed: {run.failed_count}</Badge>
      </div>
      <p className="mt-2 text-xs leading-5 text-app-muted">{run.message}</p>
    </div>
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
        {preview.repo_root ? <Badge>root: {preview.repo_root}</Badge> : null}
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

function sourceToForm(source: ConnectorSource | undefined, connectorType: "file_system" | "logs" | "git"): SavedSourceForm {
  if (!source) {
    return { ...emptySavedSourceForm };
  }
  const config = source.config ?? {};
  return {
    name: source.name,
    path: source.path,
    recursive: booleanConfig(config.recursive, true),
    maxFiles: numberConfig(config.max_files, 100),
    maxFileSizeKb: numberConfig(config.max_file_size_kb, 256),
    allowedExtensions: Array.isArray(config.allowed_extensions) ? config.allowed_extensions.join(",") : "",
    maxLines: numberConfig(config.max_lines, 1000),
    onlyErrors: booleanConfig(config.only_errors, false),
    groupSimilar: booleanConfig(config.group_similar, true),
    maxCommits: numberConfig(config.max_commits, 50),
    includeDiffSummary: booleanConfig(config.include_diff_summary, true),
    includeStatus: booleanConfig(config.include_status, true),
    enabled: source.enabled,
    ...(connectorType === "file_system" ? {} : {}),
  };
}

function sourcePayload(connectorType: "file_system" | "logs" | "git", form: SavedSourceForm) {
  const base = {
    connector_type: connectorType,
    name: form.name.trim(),
    path: form.path.trim(),
    enabled: form.enabled,
  };

  if (connectorType === "file_system") {
    return {
      ...base,
      config: {
        recursive: form.recursive,
        max_files: clampNumber(form.maxFiles, 1, 1000),
        max_file_size_kb: clampNumber(form.maxFileSizeKb, 1, 2048),
        allowed_extensions: parseExtensions(form.allowedExtensions),
      },
    };
  }

  if (connectorType === "logs") {
    return {
      ...base,
      config: {
        max_lines: clampNumber(form.maxLines, 1, 10000),
        only_errors: form.onlyErrors,
        group_similar: form.groupSimilar,
      },
    };
  }

  return {
    ...base,
    config: {
      max_commits: clampNumber(form.maxCommits, 1, 500),
      include_diff_summary: form.includeDiffSummary,
      include_status: form.includeStatus,
    },
  };
}

function updateSourcePayload(payload: ReturnType<typeof sourcePayload>): ConnectorSourceUpdateRequest {
  return {
    name: payload.name,
    path: payload.path,
    config: payload.config,
    enabled: payload.enabled,
  };
}

function numberConfig(value: unknown, fallback: number) {
  return typeof value === "number" ? value : fallback;
}

function booleanConfig(value: unknown, fallback: boolean) {
  return typeof value === "boolean" ? value : fallback;
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

function formatConnectorType(value: string) {
  if (value === "file_system") {
    return "File System";
  }
  if (value === "logs") {
    return "Logs";
  }
  if (value === "git") {
    return "Git";
  }
  return value;
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
