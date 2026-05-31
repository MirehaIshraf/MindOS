import {
  Code2,
  FileText,
  FolderOpen,
  GitBranch,
  Github,
  Globe,
  Mail,
  RefreshCw,
  Ticket,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { Dispatch, ReactNode, SetStateAction } from "react";

import { Badge } from "../components/shared/Badge";
import { Button } from "../components/shared/Button";
import { Card } from "../components/shared/Card";
import { Input } from "../components/shared/Input";
import {
  clearConnectorSourceEvents,
  clearFileSystemEvents,
  clearGitEvents,
  clearLogEvents,
  createConnectorSource,
  deleteConnectorSource,
  getApiErrorMessage,
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
  toggleConnector,
  updateConnectorSource,
} from "../services/api";
import type {
  Connector,
  ConnectorSource,
  ConnectorSourceUpdateRequest,
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
} from "../types";

const connectorOrder = ["vscode", "browser", "github", "jira", "email", "file_system", "logs", "git"];

const emptyFileForm = { folderPath: "", recursive: true, maxFiles: 100, maxFileSizeKb: 256, allowedExtensions: "" };
const emptyLogForm = { filePath: "", maxLines: 1000, onlyErrors: false, groupSimilar: true };
const emptyGitForm = { repoPath: "", maxCommits: 50, includeDiffSummary: true, includeStatus: true };
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

type FileForm = typeof emptyFileForm;
type LogForm = typeof emptyLogForm;
type GitForm = typeof emptyGitForm;
type SavedSourceForm = typeof emptySavedSourceForm;
type PanelId = Connector["id"] | "save" | null;

export function ConnectorsPage() {
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [selectedPanel, setSelectedPanel] = useState<PanelId>(null);
  const [savedSources, setSavedSources] = useState<ConnectorSource[]>([]);
  const [importRuns, setImportRuns] = useState<ImportRun[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [fileForm, setFileForm] = useState<FileForm>(emptyFileForm);
  const [logForm, setLogForm] = useState<LogForm>(emptyLogForm);
  const [gitForm, setGitForm] = useState<GitForm>(emptyGitForm);
  const [saveForm, setSaveForm] = useState<SavedSourceForm>(emptySavedSourceForm);
  const [saveType, setSaveType] = useState<"file_system" | "logs" | "git">("file_system");
  const [editingSource, setEditingSource] = useState<ConnectorSource | null>(null);
  const [filePreview, setFilePreview] = useState<FilePreviewResult | null>(null);
  const [fileResult, setFileResult] = useState<FileImportResult | null>(null);
  const [logPreview, setLogPreview] = useState<LogPreviewResult | null>(null);
  const [logResult, setLogResult] = useState<LogImportResult | null>(null);
  const [gitPreview, setGitPreview] = useState<GitPreviewResult | null>(null);
  const [gitResult, setGitResult] = useState<GitImportResult | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void refresh();
    const intervalId = window.setInterval(() => {
      void refresh(false);
    }, 12_000);
    return () => window.clearInterval(intervalId);
  }, []);

  const orderedConnectors = useMemo(
    () => [...connectors].sort((a, b) => connectorOrder.indexOf(a.id) - connectorOrder.indexOf(b.id)),
    [connectors],
  );
  const selectedConnector = selectedPanel && selectedPanel !== "save" ? connectors.find((connector) => connector.id === selectedPanel) : null;

  async function refresh(showLoading = true) {
    if (showLoading) {
      setLoading("connectors");
      setError(null);
    }
    try {
      const [connectorResponse, sourceResponse, runsResponse] = await Promise.all([
        getConnectors(),
        getConnectorSources(),
        getImportRuns({ limit: 20 }),
      ]);
      setConnectors(connectorResponse.connectors);
      setSavedSources(sourceResponse.sources);
      setImportRuns(runsResponse.runs);
    } catch (caughtError) {
      if (showLoading) {
        setError(getApiErrorMessage(caughtError));
      }
    } finally {
      if (showLoading) {
        setLoading(null);
      }
    }
  }

  async function handleToggle(connector: Connector, enabled: boolean) {
    if (!connector.configured && enabled && !["vscode", "browser", "file_system", "logs", "git"].includes(connector.id)) {
      setSelectedPanel(connector.id);
      return;
    }
    setLoading(`toggle:${connector.id}`);
    setError(null);
    try {
      const response = await toggleConnector(connector.id, enabled);
      setNotice(response.message);
      await refresh();
    } catch (caughtError) {
      setError(getApiErrorMessage(caughtError));
    } finally {
      setLoading(null);
    }
  }

  async function handleFilePreview() {
    setLoading("filePreview");
    setError(null);
    try {
      setFilePreview(await previewFileImport(toFilePayload(fileForm)));
      setFileResult(null);
    } catch (caughtError) {
      setFilePreview(null);
      setError(getApiErrorMessage(caughtError));
    } finally {
      setLoading(null);
    }
  }

  async function handleFileImport() {
    setLoading("fileImport");
    setError(null);
    try {
      setFileResult(await importFiles(toFilePayload(fileForm)));
      setFilePreview(null);
      await refresh();
    } catch (caughtError) {
      setError(getApiErrorMessage(caughtError));
    } finally {
      setLoading(null);
    }
  }

  async function handleLogPreview() {
    setLoading("logPreview");
    setError(null);
    try {
      setLogPreview(await previewLogImport(toLogPayload(logForm)));
      setLogResult(null);
    } catch (caughtError) {
      setLogPreview(null);
      setError(getApiErrorMessage(caughtError));
    } finally {
      setLoading(null);
    }
  }

  async function handleLogImport() {
    setLoading("logImport");
    setError(null);
    try {
      setLogResult(await importLogs(toLogPayload(logForm)));
      setLogPreview(null);
      await refresh();
    } catch (caughtError) {
      setError(getApiErrorMessage(caughtError));
    } finally {
      setLoading(null);
    }
  }

  async function handleGitPreview() {
    setLoading("gitPreview");
    setError(null);
    try {
      setGitPreview(await previewGitImport(toGitPayload(gitForm)));
      setGitResult(null);
    } catch (caughtError) {
      setGitPreview(null);
      setError(getApiErrorMessage(caughtError));
    } finally {
      setLoading(null);
    }
  }

  async function handleGitImport() {
    setLoading("gitImport");
    setError(null);
    try {
      setGitResult(await importGitRepo(toGitPayload(gitForm)));
      setGitPreview(null);
      await refresh();
    } catch (caughtError) {
      setError(getApiErrorMessage(caughtError));
    } finally {
      setLoading(null);
    }
  }

  async function handleClearEvents(connectorId: "file_system" | "logs" | "git") {
    const labels = { file_system: "file/folder", logs: "log", git: "Git" };
    if (!window.confirm(`This will remove imported ${labels[connectorId]} events from MindOS memory. Other memory will not be deleted. Continue?`)) {
      return;
    }
    setLoading(`clear:${connectorId}`);
    setError(null);
    try {
      const response =
        connectorId === "file_system"
          ? await clearFileSystemEvents()
          : connectorId === "logs"
            ? await clearLogEvents()
            : await clearGitEvents();
      setNotice(response.deleted_events === 0 ? "No events to clear." : `Cleared ${response.deleted_events} events.`);
      await refresh();
    } catch (caughtError) {
      setError(getApiErrorMessage(caughtError));
    } finally {
      setLoading(null);
    }
  }

  function openSavePanel(connectorType: "file_system" | "logs" | "git", source?: ConnectorSource) {
    setSaveType(connectorType);
    setEditingSource(source ?? null);
    setSaveForm(sourceToForm(source));
    setSelectedPanel("save");
  }

  async function handleSaveSource() {
    setLoading("saveSource");
    setError(null);
    try {
      const payload = sourcePayload(saveType, saveForm);
      if (editingSource) {
        await updateConnectorSource(editingSource.id, updateSourcePayload(payload));
        setNotice("Saved source updated.");
      } else {
        await createConnectorSource(payload);
        setNotice("Saved source created.");
      }
      setSelectedPanel(saveType);
      setEditingSource(null);
      await refresh();
    } catch (caughtError) {
      setError(getApiErrorMessage(caughtError));
    } finally {
      setLoading(null);
    }
  }

  async function handleRunSource(source: ConnectorSource) {
    setLoading(`run:${source.id}`);
    setError(null);
    try {
      const response = await runConnectorSourceImport(source.id);
      setNotice(response.import_run.message);
      await refresh();
    } catch (caughtError) {
      setError(getApiErrorMessage(caughtError));
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
      await refresh();
    } catch (caughtError) {
      setError(getApiErrorMessage(caughtError));
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
      setNotice(response.deleted_events === 0 ? "No events to clear for this source." : `Cleared ${response.deleted_events} source events.`);
      await refresh();
    } catch (caughtError) {
      setError(getApiErrorMessage(caughtError));
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-app-text">Connectors</h1>
          <p className="mt-1 text-sm text-app-muted">Choose what MindOS can learn from.</p>
        </div>
        <Button variant="ghost" onClick={() => void refresh()} loading={loading === "connectors"}>
          <RefreshCw size={16} />
          Refresh
        </Button>
      </header>

      {error ? <StatusMessage message={error} variant="danger" /> : null}
      {notice ? <StatusMessage message={notice} variant="success" /> : null}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-4">
          {orderedConnectors.map((connector) => (
            <ConnectorCard
              key={connector.id}
              connector={connector}
              loading={loading}
              selected={selectedPanel === connector.id}
              onToggle={(enabled) => void handleToggle(connector, enabled)}
              onConfigure={() => setSelectedPanel(connector.id)}
            />
          ))}
        </div>

        <aside>
          {selectedPanel === "save" ? (
            <SaveSourcePanel
              connectorType={saveType}
              form={saveForm}
              setForm={setSaveForm}
              editing={Boolean(editingSource)}
              loading={loading === "saveSource"}
              onClose={() => {
                setSelectedPanel(saveType);
                setEditingSource(null);
              }}
              onSave={handleSaveSource}
            />
          ) : selectedConnector ? (
            <ConfigurePanel
              connector={selectedConnector}
              savedSources={savedSources.filter((source) => source.connector_type === selectedConnector.id)}
              importRuns={importRuns.filter((run) => run.connector_type === selectedConnector.id)}
              showHistory={showHistory}
              setShowHistory={setShowHistory}
              loading={loading}
              fileForm={fileForm}
              setFileForm={setFileForm}
              filePreview={filePreview}
              fileResult={fileResult}
              logForm={logForm}
              setLogForm={setLogForm}
              logPreview={logPreview}
              logResult={logResult}
              gitForm={gitForm}
              setGitForm={setGitForm}
              gitPreview={gitPreview}
              gitResult={gitResult}
              onClose={() => setSelectedPanel(null)}
              onToggleConnector={(enabled) => void handleToggle(selectedConnector, enabled)}
              onFilePreview={handleFilePreview}
              onFileImport={handleFileImport}
              onLogPreview={handleLogPreview}
              onLogImport={handleLogImport}
              onGitPreview={handleGitPreview}
              onGitImport={handleGitImport}
              onClearEvents={() => void handleClearEvents(selectedConnector.id as "file_system" | "logs" | "git")}
              onSaveSource={() => openSavePanel(selectedConnector.id as "file_system" | "logs" | "git")}
              onRunSource={(source) => void handleRunSource(source)}
              onEditSource={(source) => openSavePanel(source.connector_type as "file_system" | "logs" | "git", source)}
              onDeleteSource={(source) => void handleDeleteSource(source)}
              onClearSource={(source) => void handleClearSourceEvents(source)}
            />
          ) : (
            <Card className="sticky top-4">
              <h2 className="text-base font-semibold text-app-text">Select a connector</h2>
              <p className="mt-2 text-sm leading-6 text-app-muted">Configure imports, saved sources, and connector status from one place.</p>
            </Card>
          )}
        </aside>
      </div>
    </div>
  );
}

function ConnectorCard({
  connector,
  loading,
  selected,
  onToggle,
  onConfigure,
}: {
  connector: Connector;
  loading: string | null;
  selected: boolean;
  onToggle: (enabled: boolean) => void;
  onConfigure: () => void;
}) {
  const Icon = connectorIcon(connector.id);
  const toggleDisabled = !connector.supports_toggle || (!connector.configured && !["vscode", "browser", "file_system", "logs", "git"].includes(connector.id));
  return (
    <Card className={`min-h-56 ${selected ? "border-violet-500/60" : ""}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-app-border bg-zinc-950 text-app-text">
            <Icon size={20} />
          </div>
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold text-app-text">{connector.name}</h2>
            <p className="mt-1 truncate text-sm text-app-muted">{connector.description}</p>
          </div>
        </div>
        <Toggle checked={connector.enabled} disabled={toggleDisabled || loading === `toggle:${connector.id}`} onChange={onToggle} />
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <StatusBadge status={connector.status} />
        {connector.supports_live_events ? <Badge>live</Badge> : null}
        {connector.supports_manual_import ? <Badge>manual</Badge> : null}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 text-xs text-app-muted">
        <div>
          <span className="block uppercase">Events</span>
          <span className="mt-1 block text-sm font-medium text-app-text">{connector.event_count}</span>
        </div>
        <div>
          <span className="block uppercase">{connector.supports_live_events ? "Last seen" : "Last sync"}</span>
          <span className="mt-1 block truncate text-sm font-medium text-app-text">{formatDate(connector.last_seen_at ?? connector.last_event_at)}</span>
        </div>
      </div>

      <Button className="mt-5 w-full" variant="secondary" onClick={onConfigure}>
        Configure
      </Button>
    </Card>
  );
}

function ConfigurePanel(props: {
  connector: Connector;
  savedSources: ConnectorSource[];
  importRuns: ImportRun[];
  showHistory: boolean;
  setShowHistory: (show: boolean) => void;
  loading: string | null;
  fileForm: FileForm;
  setFileForm: Dispatch<SetStateAction<FileForm>>;
  filePreview: FilePreviewResult | null;
  fileResult: FileImportResult | null;
  logForm: LogForm;
  setLogForm: Dispatch<SetStateAction<LogForm>>;
  logPreview: LogPreviewResult | null;
  logResult: LogImportResult | null;
  gitForm: GitForm;
  setGitForm: Dispatch<SetStateAction<GitForm>>;
  gitPreview: GitPreviewResult | null;
  gitResult: GitImportResult | null;
  onClose: () => void;
  onToggleConnector: (enabled: boolean) => void;
  onFilePreview: () => void;
  onFileImport: () => void;
  onLogPreview: () => void;
  onLogImport: () => void;
  onGitPreview: () => void;
  onGitImport: () => void;
  onClearEvents: () => void;
  onSaveSource: () => void;
  onRunSource: (source: ConnectorSource) => void;
  onEditSource: (source: ConnectorSource) => void;
  onDeleteSource: (source: ConnectorSource) => void;
  onClearSource: (source: ConnectorSource) => void;
}) {
  const { connector } = props;
  return (
    <Card className="sticky top-4 max-h-[calc(100vh-7rem)] overflow-y-auto">
      <PanelHeader title={connector.name} onClose={props.onClose} />
      <div className="mt-3 flex flex-wrap gap-2">
        <StatusBadge status={connector.status} />
        <Badge>events: {connector.event_count}</Badge>
        <Badge>{connector.supports_live_events ? `last seen: ${formatDate(connector.last_seen_at)}` : `last sync: ${formatDate(connector.last_event_at)}`}</Badge>
      </div>

      {connector.id === "vscode" ? (
        <VSCodePanel connector={connector} onToggle={props.onToggleConnector} />
      ) : connector.id === "browser" ? (
        <BrowserPanel connector={connector} onToggle={props.onToggleConnector} />
      ) : connector.id === "file_system" ? (
        <FileSystemPanel {...props} />
      ) : connector.id === "logs" ? (
        <LogsPanel {...props} />
      ) : connector.id === "git" ? (
        <GitPanel {...props} />
      ) : (
        <PlaceholderConfig connector={connector} />
      )}
    </Card>
  );
}

function VSCodePanel({ connector, onToggle }: { connector: Connector; onToggle: (enabled: boolean) => void }) {
  const [showInstall, setShowInstall] = useState(false);
  return (
    <div className="mt-5 space-y-4">
      {connector.enabled && connector.status === "disconnected" ? (
        <StatusMessage message="Extension installed? Open VSCode or check backend URL." variant="warning" />
      ) : null}
      <div className="flex items-center justify-between rounded-md border border-app-border bg-zinc-950 px-4 py-3">
        <div>
          <p className="text-sm font-medium text-app-text">Collect VSCode events</p>
          <p className="mt-1 text-xs text-app-muted">Install once. After that, this toggle controls collection.</p>
        </div>
        <Toggle checked={connector.enabled} disabled={false} onChange={onToggle} />
      </div>
      <KeyValue label="Backend URL" value="http://localhost:8000" />
      <button type="button" className="text-sm font-medium text-violet-300 hover:text-violet-200" onClick={() => setShowInstall(!showInstall)}>
        {showInstall ? "Hide install steps" : "Install extension manually"}
      </button>
      {showInstall ? (
        <div className="rounded-md border border-app-border bg-zinc-950 p-4 text-sm text-app-muted">
          <ol className="list-decimal space-y-2 pl-5">
            <li>Open <code>extensions/vscode</code>.</li>
            <li><code>npm install</code></li>
            <li><code>npm run compile</code></li>
            <li><code>npm run package</code></li>
            <li><code>code --install-extension mindos-vscode-0.1.0.vsix</code></li>
          </ol>
        </div>
      ) : null}
    </div>
  );
}

function BrowserPanel({ connector, onToggle }: { connector: Connector; onToggle: (enabled: boolean) => void }) {
  const [showInstall, setShowInstall] = useState(false);
  return (
    <div className="mt-5 space-y-4">
      {connector.enabled && connector.status === "disconnected" ? (
        <StatusMessage message="Extension installed? Open the browser popup or check the backend URL." variant="warning" />
      ) : null}
      <div className="flex items-center justify-between rounded-md border border-app-border bg-zinc-950 px-4 py-3">
        <div>
          <p className="text-sm font-medium text-app-text">Save browser research</p>
          <p className="mt-1 text-xs text-app-muted">Install once. Use the extension popup to save pages manually.</p>
        </div>
        <Toggle checked={connector.enabled} disabled={false} onChange={onToggle} />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <KeyValue label="Backend URL" value="http://localhost:8000" />
        <KeyValue label="Capture mode" value="Manual" />
      </div>
      <button type="button" className="text-sm font-medium text-violet-300 hover:text-violet-200" onClick={() => setShowInstall(!showInstall)}>
        {showInstall ? "Hide install steps" : "Install extension manually"}
      </button>
      {showInstall ? (
        <div className="rounded-md border border-app-border bg-zinc-950 p-4 text-sm text-app-muted">
          <ol className="list-decimal space-y-2 pl-5">
            <li>Open <code>extensions/browser</code>.</li>
            <li><code>npm install</code></li>
            <li><code>npm run build</code></li>
            <li>Open Chrome or Edge Extensions.</li>
            <li>Choose Load unpacked and select <code>extensions/browser</code>.</li>
          </ol>
        </div>
      ) : null}
    </div>
  );
}

function FileSystemPanel(props: Parameters<typeof ConfigurePanel>[0]) {
  return (
    <ManualConnectorPanel
      form={
        <>
          <LabeledInput label="Folder path" value={props.fileForm.folderPath} onChange={(value) => props.setFileForm((current) => ({ ...current, folderPath: value }))} />
          <div className="grid grid-cols-2 gap-3">
            <LabeledInput label="Max files" type="number" value={String(props.fileForm.maxFiles)} onChange={(value) => props.setFileForm((current) => ({ ...current, maxFiles: Number(value) }))} />
            <LabeledInput label="Max KB" type="number" value={String(props.fileForm.maxFileSizeKb)} onChange={(value) => props.setFileForm((current) => ({ ...current, maxFileSizeKb: Number(value) }))} />
          </div>
          <Checkbox label="Recursive" checked={props.fileForm.recursive} onChange={(checked) => props.setFileForm((current) => ({ ...current, recursive: checked }))} />
          <LabeledInput label="Extensions" value={props.fileForm.allowedExtensions} placeholder=".py,.ts,.md" onChange={(value) => props.setFileForm((current) => ({ ...current, allowedExtensions: value }))} />
        </>
      }
      preview={props.filePreview ? <FilePreviewBlock preview={props.filePreview} /> : null}
      result={props.fileResult ? <ImportResult result={props.fileResult} /> : null}
      previewLoading={props.loading === "filePreview"}
      importLoading={props.loading === "fileImport"}
      clearLoading={props.loading === "clear:file_system"}
      savedSources={props.savedSources}
      importRuns={props.importRuns}
      showHistory={props.showHistory}
      setShowHistory={props.setShowHistory}
      onPreview={props.onFilePreview}
      onImport={props.onFileImport}
      onClearEvents={props.onClearEvents}
      onSaveSource={props.onSaveSource}
      onRunSource={props.onRunSource}
      onEditSource={props.onEditSource}
      onDeleteSource={props.onDeleteSource}
      onClearSource={props.onClearSource}
      loading={props.loading}
    />
  );
}

function LogsPanel(props: Parameters<typeof ConfigurePanel>[0]) {
  return (
    <ManualConnectorPanel
      form={
        <>
          <LabeledInput label="Log file path" value={props.logForm.filePath} onChange={(value) => props.setLogForm((current) => ({ ...current, filePath: value }))} />
          <LabeledInput label="Max lines" type="number" value={String(props.logForm.maxLines)} onChange={(value) => props.setLogForm((current) => ({ ...current, maxLines: Number(value) }))} />
          <Checkbox label="Only errors" checked={props.logForm.onlyErrors} onChange={(checked) => props.setLogForm((current) => ({ ...current, onlyErrors: checked }))} />
          <Checkbox label="Group similar" checked={props.logForm.groupSimilar} onChange={(checked) => props.setLogForm((current) => ({ ...current, groupSimilar: checked }))} />
        </>
      }
      preview={props.logPreview ? <LogPreviewBlock preview={props.logPreview} /> : null}
      result={props.logResult ? <ImportResult result={props.logResult} /> : null}
      previewLoading={props.loading === "logPreview"}
      importLoading={props.loading === "logImport"}
      clearLoading={props.loading === "clear:logs"}
      savedSources={props.savedSources}
      importRuns={props.importRuns}
      showHistory={props.showHistory}
      setShowHistory={props.setShowHistory}
      onPreview={props.onLogPreview}
      onImport={props.onLogImport}
      onClearEvents={props.onClearEvents}
      onSaveSource={props.onSaveSource}
      onRunSource={props.onRunSource}
      onEditSource={props.onEditSource}
      onDeleteSource={props.onDeleteSource}
      onClearSource={props.onClearSource}
      loading={props.loading}
    />
  );
}

function GitPanel(props: Parameters<typeof ConfigurePanel>[0]) {
  return (
    <ManualConnectorPanel
      form={
        <>
          <LabeledInput label="Repository path" value={props.gitForm.repoPath} onChange={(value) => props.setGitForm((current) => ({ ...current, repoPath: value }))} />
          <LabeledInput label="Max commits" type="number" value={String(props.gitForm.maxCommits)} onChange={(value) => props.setGitForm((current) => ({ ...current, maxCommits: Number(value) }))} />
          <Checkbox label="Include diff summary" checked={props.gitForm.includeDiffSummary} onChange={(checked) => props.setGitForm((current) => ({ ...current, includeDiffSummary: checked }))} />
          <Checkbox label="Include status" checked={props.gitForm.includeStatus} onChange={(checked) => props.setGitForm((current) => ({ ...current, includeStatus: checked }))} />
        </>
      }
      preview={props.gitPreview ? <GitPreviewBlock preview={props.gitPreview} /> : null}
      result={props.gitResult ? <ImportResult result={props.gitResult} /> : null}
      previewLoading={props.loading === "gitPreview"}
      importLoading={props.loading === "gitImport"}
      clearLoading={props.loading === "clear:git"}
      savedSources={props.savedSources}
      importRuns={props.importRuns}
      showHistory={props.showHistory}
      setShowHistory={props.setShowHistory}
      onPreview={props.onGitPreview}
      onImport={props.onGitImport}
      onClearEvents={props.onClearEvents}
      onSaveSource={props.onSaveSource}
      onRunSource={props.onRunSource}
      onEditSource={props.onEditSource}
      onDeleteSource={props.onDeleteSource}
      onClearSource={props.onClearSource}
      loading={props.loading}
    />
  );
}

function ManualConnectorPanel({
  form,
  preview,
  result,
  previewLoading,
  importLoading,
  clearLoading,
  savedSources,
  importRuns,
  showHistory,
  setShowHistory,
  onPreview,
  onImport,
  onClearEvents,
  onSaveSource,
  onRunSource,
  onEditSource,
  onDeleteSource,
  onClearSource,
  loading,
}: {
  form: ReactNode;
  preview: ReactNode;
  result: ReactNode;
  previewLoading: boolean;
  importLoading: boolean;
  clearLoading: boolean;
  savedSources: ConnectorSource[];
  importRuns: ImportRun[];
  showHistory: boolean;
  setShowHistory: (show: boolean) => void;
  onPreview: () => void;
  onImport: () => void;
  onClearEvents: () => void;
  onSaveSource: () => void;
  onRunSource: (source: ConnectorSource) => void;
  onEditSource: (source: ConnectorSource) => void;
  onDeleteSource: (source: ConnectorSource) => void;
  onClearSource: (source: ConnectorSource) => void;
  loading: string | null;
}) {
  return (
    <div className="mt-5 space-y-5">
      <div className="space-y-3">{form}</div>
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" onClick={onPreview} loading={previewLoading}>
          Preview
        </Button>
        <Button variant="primary" onClick={onImport} loading={importLoading}>
          Import
        </Button>
        <Button variant="secondary" onClick={onSaveSource}>
          Save Source
        </Button>
        <Button variant="danger" onClick={onClearEvents} loading={clearLoading}>
          Clear Events
        </Button>
      </div>
      {preview}
      {result}

      <div className="border-t border-app-border pt-4">
        <h3 className="text-sm font-semibold text-app-text">Saved Sources</h3>
        <div className="mt-3 space-y-2">
          {savedSources.length === 0 ? (
            <p className="text-sm text-app-muted">No saved sources.</p>
          ) : (
            savedSources.map((source) => (
              <SavedSourceRow
                key={source.id}
                source={source}
                loading={loading}
                onRun={() => onRunSource(source)}
                onEdit={() => onEditSource(source)}
                onDelete={() => onDeleteSource(source)}
                onClear={() => onClearSource(source)}
              />
            ))
          )}
        </div>
      </div>

      <div className="border-t border-app-border pt-4">
        <button type="button" className="text-sm font-medium text-violet-300 hover:text-violet-200" onClick={() => setShowHistory(!showHistory)}>
          {showHistory ? "Hide import history" : "View import history"}
        </button>
        {showHistory ? (
          <div className="mt-3 space-y-2">
            {importRuns.length === 0 ? (
              <p className="text-sm text-app-muted">No import runs.</p>
            ) : (
              importRuns.map((run) => <ImportRunRow key={run.id} run={run} />)
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function PlaceholderConfig({ connector }: { connector: Connector }) {
  return (
    <div className="mt-5 rounded-md border border-app-border bg-zinc-950 p-4">
      <p className="text-sm leading-6 text-app-muted">Configuration will be added when this connector is implemented.</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Badge>{connector.configured ? "configured" : "needs setup"}</Badge>
        <Badge>events: {connector.event_count}</Badge>
      </div>
    </div>
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
  setForm: Dispatch<SetStateAction<SavedSourceForm>>;
  editing: boolean;
  loading: boolean;
  onClose: () => void;
  onSave: () => void;
}) {
  return (
    <Card className="sticky top-4 max-h-[calc(100vh-7rem)] overflow-y-auto">
      <PanelHeader title={editing ? "Edit Source" : `Save ${formatConnector(connectorType)} Source`} onClose={onClose} />
      <div className="mt-5 space-y-4">
        <LabeledInput label="Name" value={form.name} onChange={(value) => setForm((current) => ({ ...current, name: value }))} />
        <LabeledInput label={connectorType === "logs" ? "Log file path" : connectorType === "git" ? "Repository path" : "Folder path"} value={form.path} onChange={(value) => setForm((current) => ({ ...current, path: value }))} />
        <Checkbox label="Enabled" checked={form.enabled} onChange={(checked) => setForm((current) => ({ ...current, enabled: checked }))} />
        {connectorType === "file_system" ? (
          <>
            <Checkbox label="Recursive" checked={form.recursive} onChange={(checked) => setForm((current) => ({ ...current, recursive: checked }))} />
            <div className="grid grid-cols-2 gap-3">
              <LabeledInput label="Max files" type="number" value={String(form.maxFiles)} onChange={(value) => setForm((current) => ({ ...current, maxFiles: Number(value) }))} />
              <LabeledInput label="Max KB" type="number" value={String(form.maxFileSizeKb)} onChange={(value) => setForm((current) => ({ ...current, maxFileSizeKb: Number(value) }))} />
            </div>
            <LabeledInput label="Extensions" value={form.allowedExtensions} onChange={(value) => setForm((current) => ({ ...current, allowedExtensions: value }))} />
          </>
        ) : null}
        {connectorType === "logs" ? (
          <>
            <LabeledInput label="Max lines" type="number" value={String(form.maxLines)} onChange={(value) => setForm((current) => ({ ...current, maxLines: Number(value) }))} />
            <Checkbox label="Only errors" checked={form.onlyErrors} onChange={(checked) => setForm((current) => ({ ...current, onlyErrors: checked }))} />
            <Checkbox label="Group similar" checked={form.groupSimilar} onChange={(checked) => setForm((current) => ({ ...current, groupSimilar: checked }))} />
          </>
        ) : null}
        {connectorType === "git" ? (
          <>
            <LabeledInput label="Max commits" type="number" value={String(form.maxCommits)} onChange={(value) => setForm((current) => ({ ...current, maxCommits: Number(value) }))} />
            <Checkbox label="Include diff summary" checked={form.includeDiffSummary} onChange={(checked) => setForm((current) => ({ ...current, includeDiffSummary: checked }))} />
            <Checkbox label="Include status" checked={form.includeStatus} onChange={(checked) => setForm((current) => ({ ...current, includeStatus: checked }))} />
          </>
        ) : null}
        <div className="flex gap-2">
          <Button variant="primary" onClick={onSave} loading={loading} disabled={!form.name.trim() || !form.path.trim()}>
            Save
          </Button>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </div>
    </Card>
  );
}

function PanelHeader({ title, onClose }: { title: string; onClose: () => void }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <h2 className="text-base font-semibold text-app-text">{title}</h2>
      <button type="button" onClick={onClose} className="rounded-md p-1 text-app-muted hover:bg-zinc-800 hover:text-app-text">
        <X size={18} />
      </button>
    </div>
  );
}

function SavedSourceRow({ source, loading, onRun, onEdit, onDelete, onClear }: {
  source: ConnectorSource;
  loading: string | null;
  onRun: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onClear: () => void;
}) {
  return (
    <div className="rounded-md border border-app-border bg-zinc-950 px-3 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-app-text">{source.name}</p>
          <p className="mt-1 truncate text-xs text-app-muted">{source.path}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            <Badge>{source.last_import_status ?? "not imported"}</Badge>
            {source.last_import_at ? <Badge>{formatDate(source.last_import_at)}</Badge> : null}
          </div>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button className="h-8 px-3 text-xs" variant="primary" onClick={onRun} loading={loading === `run:${source.id}`}>
          Re-import
        </Button>
        <Button className="h-8 px-3 text-xs" variant="secondary" onClick={onEdit}>
          Edit
        </Button>
        <Button className="h-8 px-3 text-xs" variant="secondary" onClick={onClear} loading={loading === `clearSource:${source.id}`}>
          Clear
        </Button>
        <Button className="h-8 px-3 text-xs" variant="danger" onClick={onDelete} loading={loading === `delete:${source.id}`}>
          Delete
        </Button>
      </div>
    </div>
  );
}

function ImportRunRow({ run }: { run: ImportRun }) {
  return (
    <div className="rounded-md border border-app-border bg-zinc-950 px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={run.status === "success" ? "success" : run.status === "partial" ? "warning" : "danger"}>{run.status}</Badge>
        <span className="text-xs text-app-muted">{formatDate(run.completed_at)}</span>
      </div>
      <p className="mt-1 truncate text-xs text-app-muted">{run.path}</p>
      <p className="mt-1 text-xs text-app-muted">
        imported {run.imported_count}, skipped {run.skipped_count}, failed {run.failed_count}
      </p>
    </div>
  );
}

function FilePreviewBlock({ preview }: { preview: FilePreviewResult }) {
  return (
    <CompactBlock title="Preview">
      <Badge variant="info">candidates: {preview.total_candidates}</Badge>
      <Badge>shown: {preview.preview_files.length}</Badge>
      <Badge>skipped: {preview.skipped.length}</Badge>
    </CompactBlock>
  );
}

function LogPreviewBlock({ preview }: { preview: LogPreviewResult }) {
  return (
    <CompactBlock title="Preview">
      <Badge variant="info">scanned: {preview.total_lines_scanned}</Badge>
      <Badge variant="success">matched: {preview.matched_lines}</Badge>
    </CompactBlock>
  );
}

function GitPreviewBlock({ preview }: { preview: GitPreviewResult }) {
  return (
    <CompactBlock title="Preview">
      <Badge variant="info">{preview.repo_name}</Badge>
      <Badge>branch: {preview.current_branch ?? "detached"}</Badge>
      <Badge>commits: {preview.recent_commits.length}</Badge>
    </CompactBlock>
  );
}

function ImportResult({ result }: { result: { imported_count: number; skipped_count: number; failed_count: number; message: string } }) {
  return (
    <CompactBlock title="Result">
      <StatusMessage message={result.message} variant={result.failed_count > 0 ? "warning" : "success"} />
      <Badge variant="success">imported: {result.imported_count}</Badge>
      <Badge>skipped: {result.skipped_count}</Badge>
      <Badge variant={result.failed_count > 0 ? "danger" : "default"}>failed: {result.failed_count}</Badge>
    </CompactBlock>
  );
}

function CompactBlock({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-md border border-app-border bg-zinc-950 p-3">
      <h3 className="mb-2 text-xs font-medium uppercase text-app-muted">{title}</h3>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  );
}

function LabeledInput({ label, value, onChange, placeholder, type = "text" }: {
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

function Checkbox({ label, checked, onChange }: { label: string; checked: boolean; onChange: (checked: boolean) => void }) {
  return (
    <label className="flex items-center gap-3 text-sm text-app-text">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} className="h-4 w-4 accent-violet-600" />
      {label}
    </label>
  );
}

function Toggle({ checked, disabled, onChange }: { checked: boolean; disabled: boolean; onChange: (checked: boolean) => void }) {
  return (
    <button
      type="button"
      disabled={disabled}
      aria-pressed={checked}
      onClick={() => onChange(!checked)}
      className={`relative h-6 w-11 rounded-full transition disabled:cursor-not-allowed disabled:opacity-50 ${checked ? "bg-violet-600" : "bg-zinc-700"}`}
    >
      <span className={`absolute top-1 h-4 w-4 rounded-full bg-white transition ${checked ? "left-6" : "left-1"}`} />
    </button>
  );
}

function StatusBadge({ status }: { status: string }) {
  const label = status === "needs_configuration" ? "Needs setup" : status.charAt(0).toUpperCase() + status.slice(1);
  const variant = status === "connected" ? "success" : status === "disconnected" || status === "needs_configuration" ? "warning" : status === "error" ? "danger" : "default";
  return <Badge variant={variant}>{label}</Badge>;
}

function KeyValue({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase text-app-muted">{label}</p>
      <p className="mt-1 text-sm text-app-text">{value}</p>
    </div>
  );
}

function connectorIcon(id: string) {
  return {
    vscode: Code2,
    browser: Globe,
    github: Github,
    jira: Ticket,
    email: Mail,
    file_system: FolderOpen,
    logs: FileText,
    git: GitBranch,
  }[id] ?? FolderOpen;
}

function toFilePayload(form: FileForm): FileImportPayload {
  return {
    folder_path: form.folderPath.trim(),
    recursive: form.recursive,
    max_files: clampNumber(form.maxFiles, 1, 1000),
    max_file_size_kb: clampNumber(form.maxFileSizeKb, 1, 2048),
    allowed_extensions: parseExtensions(form.allowedExtensions),
  };
}

function toLogPayload(form: LogForm): LogImportPayload {
  return {
    file_path: form.filePath.trim(),
    max_lines: clampNumber(form.maxLines, 1, 10000),
    only_errors: form.onlyErrors,
    group_similar: form.groupSimilar,
  };
}

function toGitPayload(form: GitForm): GitImportPayload {
  return {
    repo_path: form.repoPath.trim(),
    max_commits: clampNumber(form.maxCommits, 1, 500),
    include_diff_summary: form.includeDiffSummary,
    include_status: form.includeStatus,
  };
}

function sourceToForm(source?: ConnectorSource): SavedSourceForm {
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
  };
}

function sourcePayload(connectorType: "file_system" | "logs" | "git", form: SavedSourceForm) {
  const base = { connector_type: connectorType, name: form.name.trim(), path: form.path.trim(), enabled: form.enabled };
  if (connectorType === "file_system") {
    return { ...base, config: { recursive: form.recursive, max_files: clampNumber(form.maxFiles, 1, 1000), max_file_size_kb: clampNumber(form.maxFileSizeKb, 1, 2048), allowed_extensions: parseExtensions(form.allowedExtensions) } };
  }
  if (connectorType === "logs") {
    return { ...base, config: { max_lines: clampNumber(form.maxLines, 1, 10000), only_errors: form.onlyErrors, group_similar: form.groupSimilar } };
  }
  return { ...base, config: { max_commits: clampNumber(form.maxCommits, 1, 500), include_diff_summary: form.includeDiffSummary, include_status: form.includeStatus } };
}

function updateSourcePayload(payload: ReturnType<typeof sourcePayload>): ConnectorSourceUpdateRequest {
  return { name: payload.name, path: payload.path, config: payload.config, enabled: payload.enabled };
}

function parseExtensions(value: string) {
  const extensions = value.split(",").map((extension) => extension.trim()).filter(Boolean);
  return extensions.length ? extensions : null;
}

function numberConfig(value: unknown, fallback: number) {
  return typeof value === "number" ? value : fallback;
}

function booleanConfig(value: unknown, fallback: boolean) {
  return typeof value === "boolean" ? value : fallback;
}

function clampNumber(value: number, min: number, max: number) {
  return Number.isNaN(value) ? min : Math.max(min, Math.min(max, value));
}

function formatConnector(value: string) {
  if (value === "file_system") return "File System";
  if (value === "git") return "Local Git";
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function formatDate(value?: string | null) {
  if (!value) {
    return "--";
  }
  return new Date(value).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function StatusMessage({ message, variant }: { message: string; variant: "success" | "warning" | "danger" }) {
  const classes = {
    success: "border-emerald-500/30 bg-emerald-500/10 text-emerald-200",
    warning: "border-amber-500/30 bg-amber-500/10 text-amber-100",
    danger: "border-red-500/30 bg-red-500/10 text-red-200",
  };
  return <div className={`rounded-md border px-4 py-3 text-sm ${classes[variant]}`}>{message}</div>;
}
