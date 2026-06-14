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
  addTrackedFolder,
  clearConnectorSourceEvents,
  clearEmailEvents,
  clearFileSystemEvents,
  clearGitEvents,
  clearGitHubEvents,
  clearLogEvents,
  createConnectorSource,
  deleteConnectorSource,
  connectEmail,
  connectGmail,
  createGmailDraft,
  createGmailTestDraft,
  disconnectEmail,
  disconnectGmail,
  getApiErrorMessage,
  getConnectors,
  getConnectorConfig,
  getConnectorSources,
  getEmailStatus,
  getGmailStatus,
  getGitHubStatus,
  getImportRuns,
  listGitHubRepos,
  importFiles,
  importGitRepo,
  importLogs,
  previewFileImport,
  previewGitImport,
  previewLogImport,
  reindexTrackedFolder,
  runConnectorSourceImport,
  saveEmailConfig,
  saveGitHubConfig,
  saveGitHubSelection,
  removeGmailCredentials,
  sendGmailDraft,
  syncEmailMessages,
  syncGitHubRepos,
  testEmailConnection,
  testGmailConnection,
  testGitHubConnection,
  toggleConnector,
  updateConnectorConfig,
  updateConnectorSource,
  uploadGmailCredentials,
} from "../services/api";
import type {
  Connector,
  ConnectorSource,
  ConnectorSourceUpdateRequest,
  EmailStatusResponse,
  EmailSyncResponse,
  FileImportPayload,
  FileImportResult,
  FilePreviewResult,
  GitImportPayload,
  GitImportResult,
  GitPreviewResult,
  GitHubRepo,
  GitHubStatusResponse,
  GitHubSyncResponse,
  GmailDraftResponse,
  GmailStatusResponse,
  ImportRun,
  LogImportPayload,
  LogImportResult,
  LogPreviewResult,
} from "../types";

const connectorOrder = ["vscode", "browser", "github", "gmail", "jira", "email", "file_system", "logs", "git"];

const defaultIndexedExtensions = ".txt,.md,.log,.json,.csv,.xml,.yaml,.yml,.pdf,.docx,.py,.java,.js,.ts,.tsx,.jsx,.html,.css,.sql";
const emptyFileForm = { folderPath: "", recursive: true, maxFiles: 2000, maxDepth: 5, maxFileSizeMb: 5, maxFileSizeKb: 2048, allowedExtensions: defaultIndexedExtensions, indexingEnabled: true };
const emptyLogForm = { filePath: "", maxLines: 1000, onlyErrors: false, groupSimilar: true };
const emptyGitForm = { repoPath: "", maxCommits: 50, includeDiffSummary: true, includeStatus: true };
const emptySavedSourceForm = {
  name: "",
  path: "",
  recursive: true,
  maxFiles: 2000,
  maxDepth: 5,
  maxFileSizeMb: 5,
  maxFileSizeKb: 256,
  allowedExtensions: defaultIndexedExtensions,
  indexingEnabled: true,
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
type BrowserCaptureMode = "manual" | "smart" | "off";
type BrowserConfigForm = {
  capture_mode: BrowserCaptureMode;
  capture_search_queries: boolean;
  capture_important_pages: boolean;
  capture_page_context: boolean;
  capture_full_page_text: boolean;
  max_page_text_chars: number;
  minimum_active_seconds: number;
  ignored_domains: string;
  important_domains: string;
  history_retention_days: number;
};

const defaultBrowserConfigForm: BrowserConfigForm = {
  capture_mode: "manual",
  capture_search_queries: true,
  capture_important_pages: false,
  capture_page_context: true,
  capture_full_page_text: false,
  max_page_text_chars: 6000,
  minimum_active_seconds: 8,
  ignored_domains: "",
  important_domains: "",
  history_retention_days: 30,
};

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

  async function handleAddTrackedFolder() {
    setLoading("addTrackedFolder");
    setError(null);
    try {
      const folder = await addTrackedFolder(toTrackedFolderPayload(fileForm));
      setNotice(`${folder.name} connected. MindOS will index readable files in the background.`);
      setFileForm(emptyFileForm);
      setFilePreview(null);
      setFileResult(null);
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
      if (isTrackedFileSource(source)) {
        const job = await reindexTrackedFolder(source.id);
        setNotice(job.status === "running" ? "Folder indexing is running." : "Folder reindex queued.");
      } else {
        const response = await runConnectorSourceImport(source.id);
        setNotice(response.import_run.message);
      }
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
              onAddTrackedFolder={handleAddTrackedFolder}
              onLogPreview={handleLogPreview}
              onLogImport={handleLogImport}
              onGitPreview={handleGitPreview}
              onGitImport={handleGitImport}
              onClearEvents={() => void handleClearEvents(selectedConnector.id as "file_system" | "logs" | "git")}
              onRefresh={() => void refresh()}
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
  const toggleDisabled = connector.id === "gmail" || !connector.supports_toggle || (!connector.configured && !["vscode", "browser", "file_system", "logs", "git"].includes(connector.id));
  const githubRepoCount = Number(connector.config_summary?.selected_repos_count ?? connector.config_summary?.repo_count ?? 0);
  const githubLastSync = typeof connector.config_summary?.last_sync_at === "string" ? connector.config_summary.last_sync_at : connector.last_event_at;
  const gmailEmail = typeof connector.config_summary?.email_address === "string" ? connector.config_summary.email_address : null;
  const gmailConnectedAt = typeof connector.config_summary?.connected_at === "string" ? connector.config_summary.connected_at : null;
  const emailProvider = typeof connector.config_summary?.provider_name === "string" ? connector.config_summary.provider_name : null;
  const emailAccount = typeof connector.config_summary?.account_label === "string" ? connector.config_summary.account_label : null;
  const emailLastSync = typeof connector.config_summary?.last_sync_at === "string" ? connector.config_summary.last_sync_at : connector.last_event_at;
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

      {connector.id === "github" ? (
        <div className="mt-4 grid grid-cols-2 gap-3 text-xs text-app-muted">
          <div>
            <span className="block uppercase">Repos</span>
            <span className="mt-1 block text-sm font-medium text-app-text">{githubRepoCount}</span>
          </div>
          <div>
            <span className="block uppercase">Last sync</span>
            <span className="mt-1 block truncate text-sm font-medium text-app-text">{formatDate(githubLastSync)}</span>
          </div>
        </div>
      ) : connector.id === "gmail" ? (
        <div className="mt-4 grid grid-cols-2 gap-3 text-xs text-app-muted">
          <div>
            <span className="block uppercase">Account</span>
            <span className="mt-1 block truncate text-sm font-medium text-app-text">{gmailEmail || "--"}</span>
          </div>
          <div>
            <span className="block uppercase">Connected</span>
            <span className="mt-1 block truncate text-sm font-medium text-app-text">{formatDate(gmailConnectedAt)}</span>
          </div>
        </div>
      ) : connector.id === "email" ? (
        <div className="mt-4 grid grid-cols-2 gap-3 text-xs text-app-muted">
          <div>
            <span className="block uppercase">Account</span>
            <span className="mt-1 block truncate text-sm font-medium text-app-text">{emailAccount || emailProvider || "--"}</span>
          </div>
          <div>
            <span className="block uppercase">Last sync</span>
            <span className="mt-1 block truncate text-sm font-medium text-app-text">{formatDate(emailLastSync)}</span>
          </div>
        </div>
      ) : (
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
      )}

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
  onAddTrackedFolder: () => void;
  onLogPreview: () => void;
  onLogImport: () => void;
  onGitPreview: () => void;
  onGitImport: () => void;
  onClearEvents: () => void;
  onRefresh: () => void;
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
        {connector.id === "github" ? (
          <>
            <Badge>repos: {Number(connector.config_summary?.selected_repos_count ?? connector.config_summary?.repo_count ?? 0)}</Badge>
            <Badge>last sync: {formatDate(typeof connector.config_summary?.last_sync_at === "string" ? connector.config_summary.last_sync_at : connector.last_event_at)}</Badge>
          </>
        ) : connector.id === "gmail" ? (
          <>
            <Badge>{typeof connector.config_summary?.email_address === "string" ? connector.config_summary.email_address : "local OAuth"}</Badge>
            <Badge>connected: {formatDate(typeof connector.config_summary?.connected_at === "string" ? connector.config_summary.connected_at : null)}</Badge>
          </>
        ) : connector.id === "email" ? (
          <>
            <Badge>events: {connector.event_count}</Badge>
            <Badge>last sync: {formatDate(typeof connector.config_summary?.last_sync_at === "string" ? connector.config_summary.last_sync_at : connector.last_event_at)}</Badge>
          </>
        ) : (
          <>
            <Badge>events: {connector.event_count}</Badge>
            <Badge>{connector.supports_live_events ? `last seen: ${formatDate(connector.last_seen_at)}` : `last sync: ${formatDate(connector.last_event_at)}`}</Badge>
          </>
        )}
      </div>

      {connector.id === "vscode" ? (
        <VSCodePanel connector={connector} onToggle={props.onToggleConnector} />
      ) : connector.id === "browser" ? (
        <BrowserPanel connector={connector} onToggle={props.onToggleConnector} />
      ) : connector.id === "github" ? (
        <GitHubPanel connector={connector} onToggle={props.onToggleConnector} onRefresh={props.onRefresh} />
      ) : connector.id === "gmail" ? (
        <GmailPanel onRefresh={props.onRefresh} />
      ) : connector.id === "email" ? (
        <EmailPanel connector={connector} onToggle={props.onToggleConnector} onRefresh={props.onRefresh} />
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
  const [config, setConfig] = useState<BrowserConfigForm>(defaultBrowserConfigForm);
  const [loadingConfig, setLoadingConfig] = useState(true);
  const [savingConfig, setSavingConfig] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadConfig() {
      setLoadingConfig(true);
      try {
        const response = await getConnectorConfig("browser");
        if (!cancelled) {
          setConfig(browserConfigToForm(response.config));
        }
      } catch (error) {
        if (!cancelled) {
          setMessage(getApiErrorMessage(error));
        }
      } finally {
        if (!cancelled) {
          setLoadingConfig(false);
        }
      }
    }
    void loadConfig();
    return () => {
      cancelled = true;
    };
  }, []);

  async function saveConfig() {
    setSavingConfig(true);
    setMessage(null);
    try {
      await updateConnectorConfig("browser", browserFormToConfig(config));
      setMessage("Browser capture settings saved.");
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    } finally {
      setSavingConfig(false);
    }
  }

  return (
    <div className="mt-5 space-y-4">
      {connector.enabled && connector.status === "disconnected" ? (
        <StatusMessage message="Extension installed? Open the browser popup or check the backend URL." variant="warning" />
      ) : null}
      <div className="flex items-center justify-between rounded-md border border-app-border bg-zinc-950 px-4 py-3">
        <div>
          <p className="text-sm font-medium text-app-text">Browser collection</p>
          <p className="mt-1 text-xs text-app-muted">Manual by default. Smart capture stores only work/research-like pages.</p>
        </div>
        <Toggle checked={connector.enabled} disabled={false} onChange={onToggle} />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <KeyValue label="Backend URL" value="http://localhost:8000" />
        <KeyValue label="Capture mode" value={config.capture_mode === "smart" ? "Smart" : config.capture_mode === "off" ? "Off" : "Manual"} />
      </div>
      <div className="rounded-md border border-app-border bg-zinc-950 p-4">
        <div className="space-y-4">
          <label className="block text-xs font-medium uppercase text-app-muted">
            Capture mode
            <select
              className="mt-2 w-full rounded-md border border-app-border bg-zinc-900 px-3 py-2 text-sm normal-case text-app-text"
              value={config.capture_mode}
              disabled={loadingConfig}
              onChange={(event) => {
                const mode = event.target.value as BrowserCaptureMode;
                setConfig((current) => ({
                  ...current,
                  capture_mode: mode,
                  capture_important_pages: mode === "smart" ? true : current.capture_important_pages,
                  capture_page_context: mode === "smart" ? true : current.capture_page_context,
                }));
              }}
            >
              <option value="manual">Manual only</option>
              <option value="smart">Smart capture</option>
              <option value="off">Off</option>
            </select>
          </label>
          <div className="space-y-2">
            <Checkbox label="Capture search queries" checked={config.capture_search_queries} onChange={(checked) => setConfig((current) => ({ ...current, capture_search_queries: checked }))} />
            <Checkbox label="Capture important pages" checked={config.capture_important_pages} onChange={(checked) => setConfig((current) => ({ ...current, capture_important_pages: checked }))} />
            <Checkbox label="Capture page context" checked={config.capture_page_context} onChange={(checked) => setConfig((current) => ({ ...current, capture_page_context: checked }))} />
            <Checkbox label="Capture readable page text" checked={config.capture_full_page_text} onChange={(checked) => setConfig((current) => ({ ...current, capture_full_page_text: checked }))} />
          </div>
          <p className="text-xs leading-5 text-app-muted">
            Readable text stores trimmed visible page text for important pages. It does not store forms, passwords, or raw HTML.
          </p>
          <div className="grid grid-cols-2 gap-3">
            <LabeledInput
              label="Max context chars"
              type="number"
              value={String(config.max_page_text_chars)}
              onChange={(value) => setConfig((current) => ({ ...current, max_page_text_chars: Number(value) }))}
            />
            <LabeledInput
              label="Active seconds"
              type="number"
              value={String(config.minimum_active_seconds)}
              onChange={(value) => setConfig((current) => ({ ...current, minimum_active_seconds: Number(value) }))}
            />
          </div>
          <LabeledInput
            label="History retention days"
            type="number"
            value={String(config.history_retention_days)}
            onChange={(value) => setConfig((current) => ({ ...current, history_retention_days: Number(value) }))}
          />
          <LabeledTextarea
            label="Ignored domains"
            value={config.ignored_domains}
            placeholder="youtube.com, facebook.com"
            onChange={(value) => setConfig((current) => ({ ...current, ignored_domains: value }))}
          />
          <LabeledTextarea
            label="Important domains"
            value={config.important_domains}
            placeholder="docs.example.com, internal.wiki"
            onChange={(value) => setConfig((current) => ({ ...current, important_domains: value }))}
          />
          <p className="text-xs leading-5 text-app-muted">
            Smart capture ignores private/login/payment pages and noisy domains by default. You can still manually save useful pages.
          </p>
          <Button className="w-full" variant="secondary" onClick={() => void saveConfig()} loading={savingConfig} disabled={loadingConfig}>
            Save Browser Settings
          </Button>
          {message ? <p className="text-sm text-app-muted">{message}</p> : null}
        </div>
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

function browserConfigToForm(config: Record<string, unknown>): BrowserConfigForm {
  return {
    capture_mode: ["manual", "smart", "off"].includes(String(config.capture_mode)) ? (String(config.capture_mode) as BrowserCaptureMode) : "manual",
    capture_search_queries: browserBooleanConfig(config.capture_search_queries, true),
    capture_important_pages: browserBooleanConfig(config.capture_important_pages, false),
    capture_page_context: browserBooleanConfig(config.capture_page_context, true),
    capture_full_page_text: browserBooleanConfig(config.capture_full_page_text, false),
    max_page_text_chars: browserNumberConfig(config.max_page_text_chars, 6000),
    minimum_active_seconds: browserNumberConfig(config.minimum_active_seconds, 8),
    ignored_domains: listConfig(config.ignored_domains).join(", "),
    important_domains: listConfig(config.important_domains).join(", "),
    history_retention_days: browserNumberConfig(config.history_retention_days, 30),
  };
}

function browserFormToConfig(form: BrowserConfigForm): Record<string, unknown> {
  return {
    capture_mode: form.capture_mode,
    capture_search_queries: form.capture_search_queries,
    capture_important_pages: form.capture_important_pages,
    capture_page_context: form.capture_page_context,
    capture_full_page_text: form.capture_full_page_text,
    max_page_text_chars: browserClampNumber(form.max_page_text_chars, 500, 20000, 6000),
    minimum_active_seconds: browserClampNumber(form.minimum_active_seconds, 3, 120, 8),
    ignored_domains: splitDomainList(form.ignored_domains),
    important_domains: splitDomainList(form.important_domains),
    history_retention_days: browserClampNumber(form.history_retention_days, 1, 365, 30),
  };
}

function browserBooleanConfig(value: unknown, fallback: boolean): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function browserNumberConfig(value: unknown, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function listConfig(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

function splitDomainList(value: string): string[] {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
}

function browserClampNumber(value: number, min: number, max: number, fallback: number): number {
  if (!Number.isFinite(value)) {
    return fallback;
  }
  return Math.max(min, Math.min(max, Math.round(value)));
}

function GitHubPanel({ connector, onToggle, onRefresh }: { connector: Connector; onToggle: (enabled: boolean) => void; onRefresh: () => void }) {
  const [status, setStatus] = useState<GitHubStatusResponse | null>(null);
  const [repos, setRepos] = useState<GitHubRepo[]>([]);
  const [selectedRepos, setSelectedRepos] = useState<string[]>([]);
  const [token, setToken] = useState("");
  const [apiBaseUrl, setApiBaseUrl] = useState("https://api.github.com");
  const [includeCommits, setIncludeCommits] = useState(true);
  const [includeIssues, setIncludeIssues] = useState(true);
  const [includePullRequests, setIncludePullRequests] = useState(true);
  const [maxItems, setMaxItems] = useState(30);
  const [syncResult, setSyncResult] = useState<GitHubSyncResponse | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadStatus() {
      setLoading("githubStatus");
      try {
        const response = await getGitHubStatus();
        if (!cancelled) {
          setStatus(response);
          setApiBaseUrl(response.api_base_url || "https://api.github.com");
          setSelectedRepos(response.selected_repos ?? []);
          setIncludeCommits(response.sync_settings?.commits ?? true);
          setIncludeIssues(response.sync_settings?.issues ?? true);
          setIncludePullRequests(response.sync_settings?.pull_requests ?? true);
          setMaxItems(response.sync_settings?.max_items_per_type ?? 30);
        }
      } catch (error) {
        if (!cancelled) setMessage(getApiErrorMessage(error));
      } finally {
        if (!cancelled) setLoading(null);
      }
    }
    void loadStatus();
    return () => {
      cancelled = true;
    };
  }, []);

  async function saveToken() {
    setLoading("githubSave");
    setMessage(null);
    try {
      const response = await saveGitHubConfig({ token, api_base_url: apiBaseUrl });
      setStatus(response);
      setRepos([]);
      setSelectedRepos(response.selected_repos ?? []);
      setToken("");
      setMessage(response.configured ? "GitHub token saved locally." : "GitHub token cleared.");
      onRefresh();
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    } finally {
      setLoading(null);
    }
  }

  async function clearToken() {
    if (!window.confirm("Clear the saved GitHub token? Synced memory events will remain.")) return;
    setToken("");
    setLoading("githubClearToken");
    setMessage(null);
    try {
      const response = await saveGitHubConfig({ token: "", api_base_url: apiBaseUrl });
      setStatus(response);
      setRepos([]);
      setSelectedRepos([]);
      setMessage("GitHub token cleared.");
      onRefresh();
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    } finally {
      setLoading(null);
    }
  }

  async function testConnection() {
    setLoading("githubTest");
    setMessage(null);
    try {
      if (token.trim()) {
        await saveGitHubConfig({ token, api_base_url: apiBaseUrl });
        setToken("");
      }
      const response = await testGitHubConnection();
      setMessage(response.message);
      setStatus(await getGitHubStatus());
      onRefresh();
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    } finally {
      setLoading(null);
    }
  }

  async function loadRepos() {
    if (!isConnected()) {
      setMessage("Connect GitHub before loading repositories.");
      return;
    }
    setLoading("githubRepos");
    setMessage(null);
    try {
      const response = await listGitHubRepos();
      setRepos(response.repos);
      setMessage(`Loaded ${response.total} repositories.`);
      setStatus(await getGitHubStatus());
      onRefresh();
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    } finally {
      setLoading(null);
    }
  }

  async function syncSelectedRepos() {
    if (!isConnected()) {
      setMessage("Connect GitHub before syncing repositories.");
      return;
    }
    setLoading("githubSync");
    setMessage(null);
    setSyncResult(null);
    try {
      const response = await syncGitHubRepos({
        repo_full_names: selectedRepos.slice(0, 5),
        include_commits: includeCommits,
        include_issues: includeIssues,
        include_pull_requests: includePullRequests,
        max_items_per_type: maxItems,
      });
      setSyncResult(response);
      setMessage(response.message);
      setStatus(await getGitHubStatus());
      onRefresh();
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    } finally {
      setLoading(null);
    }
  }

  async function clearEvents() {
    if (!window.confirm("Clear GitHub memory events? The saved token and repo selection will remain.")) return;
    setLoading("githubClearEvents");
    setMessage(null);
    try {
      const response = await clearGitHubEvents();
      setMessage(response.deleted_events === 0 ? "No GitHub events to clear." : `Cleared ${response.deleted_events} GitHub events.`);
      setStatus(await getGitHubStatus());
      onRefresh();
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    } finally {
      setLoading(null);
    }
  }

  function toggleRepo(fullName: string) {
    setSelectedRepos((current) => {
      if (current.includes(fullName)) return current.filter((repo) => repo !== fullName);
      return [...current, fullName].slice(0, 5);
    });
  }

  async function saveRepositories() {
    if (!isConnected()) {
      setMessage("Connect GitHub before saving repositories.");
      return;
    }
    setLoading("githubSaveRepos");
    setMessage(null);
    try {
      const response = await saveGitHubSelection(selectedRepos, {
        commits: includeCommits,
        issues: includeIssues,
        pull_requests: includePullRequests,
        max_items_per_type: maxItems,
      });
      setStatus(response);
      setMessage(selectedRepos.length ? "Repositories saved." : "Repository selection cleared.");
      onRefresh();
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    } finally {
      setLoading(null);
    }
  }

  function toggleConnection() {
    if (!configured && !token.trim()) {
      setMessage("Save a GitHub token before connecting.");
      return;
    }
    const nextEnabled = !currentEnabled;
    onToggle(nextEnabled);
    setStatus((current) => current ? { ...current, enabled: nextEnabled, connected: nextEnabled && Boolean(current.username), status: nextEnabled && current.username ? "connected" : nextEnabled ? "configured" : "off" } : current);
  }

  function isConnected() {
    return Boolean((status?.enabled ?? connector.enabled) && status?.connected);
  }

  const configured = status?.configured ?? connector.configured;
  const currentEnabled = status?.enabled ?? connector.enabled;
  const connected = isConnected();
  const selectedCount = selectedRepos.length;
  return (
    <div className="mt-5 space-y-4">
      <div>
        <p className="text-sm font-medium text-app-text">GitHub</p>
        <p className="mt-1 text-sm text-app-muted">Connect GitHub so MindOS can read selected repositories when needed.</p>
      </div>

      <div className="flex flex-wrap gap-2">
        <StatusBadge status={connected ? "connected" : currentEnabled && status?.last_error ? "error" : currentEnabled && configured ? "configured" : configured ? "configured" : "off"} />
        <Badge>Repositories: {selectedCount || status?.repo_count || 0}</Badge>
        <Badge>Last sync: {formatDate(status?.last_sync_at ?? connector.last_event_at)}</Badge>
      </div>
      {connected && status?.username ? <p className="text-sm text-app-muted">Connected as {status.username}</p> : null}
      {status?.last_error ? <StatusMessage message={status.last_error} variant="warning" /> : null}

      <div className="rounded-md border border-app-border bg-zinc-950 p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-app-text">Connection</p>
            <p className="mt-1 text-xs text-app-muted">{configured ? "Token saved. Enter a new token to replace it." : "Add a personal access token to configure GitHub."}</p>
          </div>
          <Toggle checked={currentEnabled} disabled={!configured} onChange={toggleConnection} />
        </div>
        <div className="mt-4 space-y-3">
          <label className="block text-xs font-medium uppercase text-app-muted">
            Personal access token
            <Input
              className="mt-2"
              type="password"
              value={token}
              placeholder={configured ? "Token saved. Enter a new token to replace it." : "github_pat_..."}
              onChange={(event) => setToken(event.target.value)}
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => void saveToken()} loading={loading === "githubSave"} disabled={!token.trim() && configured}>
              Save token
            </Button>
            <Button variant="secondary" onClick={() => void testConnection()} loading={loading === "githubTest"} disabled={!configured && !token.trim()}>
              Test connection
            </Button>
            <Button variant={currentEnabled ? "secondary" : "primary"} onClick={toggleConnection} disabled={!configured}>
              {currentEnabled ? "Disconnect" : "Connect"}
            </Button>
            <Button variant="danger" onClick={() => void clearToken()} loading={loading === "githubClearToken"} disabled={!configured}>
              Clear token
            </Button>
          </div>
        </div>
      </div>

      {connected ? (
        <div className="rounded-md border border-app-border bg-zinc-950 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-app-text">Repositories</p>
              <p className="mt-1 text-xs text-app-muted">Choose repositories MindOS can use for GitHub context. Select up to 5 repositories.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" onClick={() => void loadRepos()} loading={loading === "githubRepos"}>
                Load repositories
              </Button>
              <Button variant="primary" onClick={() => void saveRepositories()} loading={loading === "githubSaveRepos"}>
                Save repositories
              </Button>
            </div>
          </div>
          <div className="mt-3 max-h-72 space-y-2 overflow-y-auto">
            {repos.length === 0 ? (
              <p className="text-sm text-app-muted">Load repositories to choose what MindOS can use.</p>
            ) : (
              repos.map((repo) => (
                <label key={repo.full_name} className="flex cursor-pointer items-start gap-3 rounded-md border border-app-border bg-zinc-900/60 px-3 py-2 text-sm">
                  <input
                    type="checkbox"
                    checked={selectedRepos.includes(repo.full_name)}
                    onChange={() => toggleRepo(repo.full_name)}
                    className="mt-1 h-4 w-4 accent-violet-600"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium text-app-text">{repo.full_name}</span>
                    <span className="mt-1 block truncate text-xs text-app-muted">{repo.description || "No description"}</span>
                    <span className="mt-1 block text-xs text-app-muted">Updated {formatDate(repo.updated_at)}</span>
                  </span>
                  <Badge>{repo.private ? "private" : "public"}</Badge>
                </label>
              ))
            )}
          </div>
        </div>
      ) : (
        <div className="rounded-md border border-app-border bg-zinc-950 p-4 text-sm text-app-muted">
          Connect GitHub to load and choose repositories.
        </div>
      )}

      <details className="rounded-md border border-app-border bg-zinc-950 p-4">
        <summary className="cursor-pointer text-sm font-medium text-app-text">Advanced sync settings</summary>
        <div className="mt-4 space-y-3">
          <LabeledInput label="API base URL" value={apiBaseUrl} onChange={setApiBaseUrl} placeholder="https://api.github.com" />
          <Checkbox label="Sync recent commits" checked={includeCommits} onChange={setIncludeCommits} />
          <Checkbox label="Sync open issues" checked={includeIssues} onChange={setIncludeIssues} />
          <Checkbox label="Sync open pull requests" checked={includePullRequests} onChange={setIncludePullRequests} />
          <LabeledInput label="Max items per type" type="number" value={String(maxItems)} onChange={(value) => setMaxItems(Math.max(1, Math.min(100, Number(value) || 30)))} />
          <div className="flex flex-wrap gap-2">
            {connected && selectedRepos.length > 0 ? (
              <Button variant="secondary" onClick={() => void syncSelectedRepos()} loading={loading === "githubSync"}>
                Sync now
              </Button>
            ) : null}
            <Button variant="danger" onClick={() => void clearEvents()} loading={loading === "githubClearEvents"}>
              Clear GitHub events
            </Button>
          </div>
        </div>
      </details>

      {syncResult ? (
        <CompactBlock title="Sync result">
          <Badge variant={syncResult.status === "success" ? "success" : "warning"}>{syncResult.status}</Badge>
          <Badge>imported: {syncResult.imported_count}</Badge>
          <Badge>updated: {syncResult.updated_count}</Badge>
          <Badge>skipped: {syncResult.skipped_count}</Badge>
          <Badge variant={syncResult.failed_count ? "danger" : "default"}>failed: {syncResult.failed_count}</Badge>
        </CompactBlock>
      ) : null}
      {syncResult?.warnings.length ? <StatusMessage message={syncResult.warnings.join(" ")} variant="warning" /> : null}
      {message ? <p className="text-sm text-app-muted">{message}</p> : null}
    </div>
  );
}

function GmailPanel({ onRefresh }: { onRefresh: () => void }) {
  const [status, setStatus] = useState<GmailStatusResponse | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [draftTo, setDraftTo] = useState("");
  const [draftSubject, setDraftSubject] = useState("MindOS Gmail draft");
  const [draftBody, setDraftBody] = useState("Draft created by MindOS.");
  const [lastDraft, setLastDraft] = useState<(GmailDraftResponse & { to: string; subject: string; body: string }) | null>(null);
  const [confirmSend, setConfirmSend] = useState(false);

  useEffect(() => {
    void loadStatus();
  }, []);

  async function loadStatus() {
    setLoading("gmailStatus");
    try {
      const response = await getGmailStatus();
      setStatus(response);
      if (response.email_address && !draftTo) {
        setDraftTo(response.email_address);
      }
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    } finally {
      setLoading(null);
    }
  }

  async function handleUpload(file: File | undefined) {
    if (!file) return;
    setLoading("gmailUpload");
    setMessage(null);
    setLastDraft(null);
    try {
      const response = await uploadGmailCredentials(file);
      setStatus(response);
      setMessage("OAuth credentials added.");
      onRefresh();
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    } finally {
      setLoading(null);
    }
  }

  async function handleConnect() {
    setLoading("gmailConnect");
    setMessage(null);
    try {
      const response = await connectGmail();
      window.open(response.auth_url, "_blank", "noopener,noreferrer");
      setMessage("Google sign-in opened. Return here after Gmail says connected.");
      setTimeout(() => void loadStatus(), 3000);
      onRefresh();
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    } finally {
      setLoading(null);
    }
  }

  async function handleTest() {
    setLoading("gmailTest");
    setMessage(null);
    try {
      const response = await testGmailConnection();
      setMessage(response.message);
      await loadStatus();
      onRefresh();
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    } finally {
      setLoading(null);
    }
  }

  async function handleTestDraft() {
    setLoading("gmailTestDraft");
    setMessage(null);
    try {
      const response = await createGmailTestDraft();
      setLastDraft({ ...response, to: status?.email_address || "", subject: "MindOS Gmail test draft", body: "This is a test draft created by MindOS." });
      setMessage(response.message);
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    } finally {
      setLoading(null);
    }
  }

  async function handleCreateDraft() {
    setLoading("gmailDraft");
    setMessage(null);
    try {
      const response = await createGmailDraft({ to: draftTo, subject: draftSubject, body: draftBody });
      setLastDraft({ ...response, to: draftTo, subject: draftSubject, body: draftBody });
      setMessage(response.message);
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    } finally {
      setLoading(null);
    }
  }

  async function handleSendDraft() {
    if (!lastDraft) return;
    setLoading("gmailSend");
    setMessage(null);
    try {
      const response = await sendGmailDraft(lastDraft.draft_id);
      setMessage(response.message);
      setLastDraft(null);
      setConfirmSend(false);
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    } finally {
      setLoading(null);
    }
  }

  async function handleDisconnect() {
    setLoading("gmailDisconnect");
    setMessage(null);
    try {
      const response = await disconnectGmail();
      setStatus(response);
      setLastDraft(null);
      setMessage("Gmail disconnected. OAuth credentials remain saved.");
      onRefresh();
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    } finally {
      setLoading(null);
    }
  }

  async function handleRemoveCredentials() {
    if (!window.confirm("Remove Gmail OAuth credentials and token from this computer?")) return;
    setLoading("gmailRemove");
    setMessage(null);
    try {
      const response = await removeGmailCredentials();
      setStatus(response);
      setLastDraft(null);
      setMessage("Gmail credentials removed.");
      onRefresh();
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    } finally {
      setLoading(null);
    }
  }

  const configured = Boolean(status?.credentials_configured);
  const connected = Boolean(status?.connected);
  const busy = Boolean(loading);
  return (
    <div className="mt-5 space-y-4">
      <div>
        <p className="text-sm font-medium text-app-text">Gmail</p>
        <p className="mt-1 text-sm text-app-muted">Connect Gmail using your own Google OAuth credentials.</p>
      </div>

      <div className="flex flex-wrap gap-2">
        <StatusBadge status={connected ? "connected" : configured ? "configured" : "needs_configuration"} />
        {status?.email_address ? <Badge>{status.email_address}</Badge> : null}
        {status?.credential_file_name ? <Badge>{status.credential_file_name}</Badge> : null}
      </div>
      {status?.last_error ? <StatusMessage message={status.last_error} variant="warning" /> : null}

      <div className="rounded-md border border-app-border bg-zinc-950 p-4">
        <p className="text-sm font-medium text-app-text">Connection</p>
        <p className="mt-1 text-xs text-app-muted">
          Upload a Google OAuth desktop client credentials file. MindOS stores it locally and never shows the secret after upload.
        </p>
        <label className="mt-4 block text-xs font-medium uppercase text-app-muted">
          OAuth credentials
          <Input
            className="mt-2"
            type="file"
            accept="application/json,.json"
            disabled={busy}
            onChange={(event) => void handleUpload(event.target.files?.[0])}
          />
        </label>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button variant="primary" onClick={() => void handleConnect()} loading={loading === "gmailConnect"} disabled={!configured || busy}>
            Connect Gmail
          </Button>
          <Button variant="secondary" onClick={() => void handleTest()} loading={loading === "gmailTest"} disabled={!connected || busy}>
            Test connection
          </Button>
          <Button variant="secondary" onClick={() => void handleDisconnect()} loading={loading === "gmailDisconnect"} disabled={!configured || busy}>
            Disconnect Gmail
          </Button>
          <Button variant="danger" onClick={() => void handleRemoveCredentials()} loading={loading === "gmailRemove"} disabled={!configured || busy}>
            Remove credentials
          </Button>
        </div>
      </div>

      {connected ? (
        <>
          <CompactBlock title="Granted scopes">
            {(status?.scopes.length ? status.scopes : status?.required_scopes || []).map((scope) => (
              <Badge key={scope}>{scope.replace("https://www.googleapis.com/auth/", "")}</Badge>
            ))}
          </CompactBlock>

          <div className="rounded-md border border-app-border bg-zinc-950 p-4">
            <p className="text-sm font-medium text-app-text">Draft tools</p>
            <p className="mt-1 text-xs text-app-muted">MindOS can create drafts. Sending always requires confirmation.</p>
            <div className="mt-4 grid gap-3">
              <LabeledInput label="To" value={draftTo} onChange={setDraftTo} placeholder={status?.email_address || "you@example.com"} />
              <LabeledInput label="Subject" value={draftSubject} onChange={setDraftSubject} />
              <LabeledTextarea label="Body" value={draftBody} onChange={setDraftBody} />
              <div className="flex flex-wrap gap-2">
                <Button variant="secondary" onClick={() => void handleTestDraft()} loading={loading === "gmailTestDraft"} disabled={busy}>
                  Create test draft
                </Button>
                <Button variant="primary" onClick={() => void handleCreateDraft()} loading={loading === "gmailDraft"} disabled={busy}>
                  Create draft
                </Button>
                {lastDraft ? (
                  <Button variant="danger" onClick={() => setConfirmSend(true)} disabled={busy}>
                    Send draft
                  </Button>
                ) : null}
              </div>
            </div>
          </div>
        </>
      ) : null}

      {lastDraft ? (
        <CompactBlock title="Draft ready">
          <Badge>draft: {lastDraft.draft_id}</Badge>
          <Badge>{lastDraft.subject}</Badge>
          <Badge>{lastDraft.to}</Badge>
        </CompactBlock>
      ) : null}

      {confirmSend && lastDraft ? (
        <div className="rounded-md border border-red-500/40 bg-red-950/20 p-4">
          <p className="text-sm font-medium text-app-text">Send this email?</p>
          <div className="mt-3 space-y-2 text-sm text-app-muted">
            <p><span className="text-app-text">To:</span> {lastDraft.to}</p>
            <p><span className="text-app-text">Subject:</span> {lastDraft.subject}</p>
            <p className="whitespace-pre-wrap rounded-md border border-app-border bg-zinc-950 p-3">{lastDraft.body}</p>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => setConfirmSend(false)} disabled={busy}>
              Cancel
            </Button>
            <Button variant="danger" onClick={() => void handleSendDraft()} loading={loading === "gmailSend"} disabled={busy}>
              Send email
            </Button>
          </div>
        </div>
      ) : null}

      {message ? <p className="text-sm text-app-muted">{message}</p> : null}
    </div>
  );
}


function EmailPanel({ connector, onToggle, onRefresh }: { connector: Connector; onToggle: (enabled: boolean) => void; onRefresh: () => void }) {
  const [status, setStatus] = useState<EmailStatusResponse | null>(null);
  const [providerName, setProviderName] = useState("Corporate Email MCP");
  const [apiBaseUrl, setApiBaseUrl] = useState("mock");
  const [authType, setAuthType] = useState<"bearer" | "api_key_header" | "none">("none");
  const [authHeaderName, setAuthHeaderName] = useState("Authorization");
  const [apiKey, setApiKey] = useState("");
  const [accountLabel, setAccountLabel] = useState("");
  const [testTool, setTestTool] = useState("email.test");
  const [searchTool, setSearchTool] = useState("email.search");
  const [getTool, setGetTool] = useState("email.get");
  const [foldersTool, setFoldersTool] = useState("email.list_folders");
  const [scope, setScope] = useState<"recent" | "unread" | "search">("recent");
  const [query, setQuery] = useState("");
  const [maxItems, setMaxItems] = useState(25);
  const [syncResult, setSyncResult] = useState<EmailSyncResponse | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadStatus() {
      setLoading("emailStatus");
      try {
        const response = await getEmailStatus();
        if (!cancelled) {
          setStatus(response);
          setProviderName(response.provider_name || "Corporate Email MCP");
          setApiBaseUrl(response.api_base_url || "mock");
          setAuthType(response.auth_type || "none");
          setAuthHeaderName(response.auth_header_name || "Authorization");
          setAccountLabel(response.account_label || "");
          if (response.selected_scope === "recent" || response.selected_scope === "unread" || response.selected_scope === "search") setScope(response.selected_scope);
        }
      } catch (error) {
        if (!cancelled) setMessage(getApiErrorMessage(error));
      } finally {
        if (!cancelled) setLoading(null);
      }
    }
    void loadStatus();
    return () => { cancelled = true; };
  }, []);

  async function saveConfig() {
    setLoading("emailSave");
    setMessage(null);
    try {
      const response = await saveEmailConfig({
        provider_type: "email_mcp",
        provider_name: providerName,
        api_base_url: apiBaseUrl,
        auth_type: authType,
        auth_header_name: authHeaderName,
        api_key: apiKey || undefined,
        account_label: accountLabel,
        tool_mapping: {
          test: testTool,
          search: searchTool,
          get: getTool,
          list_folders: foldersTool,
        },
      });
      setStatus(response);
      setApiKey("");
      setMessage("Email MCP provider saved.");
      onRefresh();
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    } finally {
      setLoading(null);
    }
  }

  async function testConnection() {
    setLoading("emailTest");
    setMessage(null);
    try {
      if (apiKey.trim() || !status?.configured) {
        await saveConfig();
      }
      const response = await testEmailConnection();
      setStatus(await getEmailStatus());
      setMessage(response.message);
      onRefresh();
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    } finally {
      setLoading(null);
    }
  }

  async function connectProvider() {
    setLoading("emailConnect");
    setMessage(null);
    try {
      const response = await connectEmail();
      setStatus(await getEmailStatus());
      setMessage(response.message);
      onRefresh();
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    } finally {
      setLoading(null);
    }
  }

  async function handleDisconnect() {
    if (!window.confirm("Disconnect Email? Synced memory events will remain.")) return;
    setLoading("emailDisconnect");
    setMessage(null);
    try {
      await disconnectEmail();
      setStatus(await getEmailStatus());
      setMessage("Email connector disconnected.");
      onRefresh();
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    } finally {
      setLoading(null);
    }
  }

  async function syncNow() {
    if (!connected) {
      setMessage("Connect Email before syncing.");
      return;
    }
    setLoading("emailSync");
    setMessage(null);
    setSyncResult(null);
    try {
      const response = await syncEmailMessages({ scope, query: scope === "search" ? query : undefined, max_items: maxItems });
      setSyncResult(response);
      setMessage(response.message);
      setStatus(await getEmailStatus());
      onRefresh();
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    } finally {
      setLoading(null);
    }
  }

  async function handleClearEvents() {
    if (!window.confirm("Clear email memory events? Email provider configuration will remain.")) return;
    setLoading("emailClearEvents");
    setMessage(null);
    try {
      const response = await clearEmailEvents();
      setMessage(response.deleted_events === 0 ? "No email events to clear." : `Cleared ${response.deleted_events} email events.`);
      setStatus(await getEmailStatus());
      onRefresh();
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    } finally {
      setLoading(null);
    }
  }

  const connected = Boolean(status?.connected ?? connector.connected);
  const configured = Boolean(status?.configured ?? connector.configured);
  const currentProviderName = status?.provider_name ?? (typeof connector.config_summary?.provider_name === "string" ? connector.config_summary.provider_name : null);
  const currentAccountLabel = status?.account_label ?? (typeof connector.config_summary?.account_label === "string" ? connector.config_summary.account_label : null);
  const capabilities = status?.capabilities;
  const currentEnabled = status?.enabled ?? connector.enabled;

  return (
    <div className="mt-5 space-y-4">
      <div>
        <p className="text-sm font-medium text-app-text">Email</p>
        <p className="mt-1 text-sm text-app-muted">Connect an email MCP provider so MindOS can read email context.</p>
      </div>

      <div className="flex flex-wrap gap-2">
        <StatusBadge status={connected ? "connected" : status?.last_error ? "error" : configured ? "configured" : "off"} />
        <Badge>events: {status?.event_count ?? connector.event_count}</Badge>
        <Badge>last sync: {formatDate(status?.last_sync_at ?? connector.last_event_at)}</Badge>
      </div>
      {connected ? <p className="text-sm text-app-muted">Connected to {currentProviderName || "Email MCP"}{currentAccountLabel ? ` (${currentAccountLabel})` : ""}</p> : null}
      {status?.last_error ? <StatusMessage message={status.last_error} variant="warning" /> : null}

      <div className="rounded-md border border-app-border bg-zinc-950 p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-app-text">Connection</p>
            <p className="mt-1 text-xs text-app-muted">Use a managed, internal, local, or custom email MCP endpoint. Mock provider is available for demos.</p>
          </div>
          <Toggle checked={currentEnabled} disabled={!configured} onChange={onToggle} />
        </div>
        <div className="mt-4 space-y-3">
          <LabeledInput label="Provider name" value={providerName} placeholder="Corporate Email MCP" onChange={setProviderName} />
          <LabeledInput label="MCP/API base URL" value={apiBaseUrl} placeholder="https://email-mcp.company.com or mock" onChange={setApiBaseUrl} />
          <label className="block text-xs font-medium uppercase text-app-muted">
            Authentication type
            <select
              className="mt-2 w-full rounded-md border border-app-border bg-zinc-900 px-3 py-2 text-sm normal-case text-app-text"
              value={authType}
              onChange={(event) => setAuthType(event.target.value as typeof authType)}
            >
              <option value="bearer">Bearer token</option>
              <option value="api_key_header">API key header</option>
              <option value="none">No auth</option>
            </select>
          </label>
          {authType !== "none" ? (
            <>
              <LabeledInput label="Header name" value={authHeaderName} placeholder="Authorization" onChange={setAuthHeaderName} />
              <label className="block text-xs font-medium uppercase text-app-muted">
                Token / API key
                <Input
                  className="mt-2"
                  type="password"
                  value={apiKey}
                  placeholder={status?.has_api_key ? "Key saved. Enter a new key to replace it." : "Paste token or API key"}
                  onChange={(event) => setApiKey(event.target.value)}
                />
              </label>
            </>
          ) : null}
          <LabeledInput label="Account label" value={accountLabel} placeholder="work email / personal gmail" onChange={setAccountLabel} />
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => void saveConfig()} loading={loading === "emailSave"}>
              Save
            </Button>
            <Button variant="secondary" onClick={() => void testConnection()} loading={loading === "emailTest"} disabled={!configured && !providerName.trim()}>
              Test connection
            </Button>
            {connected ? (
              <Button variant="secondary" onClick={() => void handleDisconnect()} loading={loading === "emailDisconnect"}>
                Disconnect
              </Button>
            ) : (
              <Button variant="primary" onClick={() => void connectProvider()} loading={loading === "emailConnect"} disabled={!configured}>
                Connect
              </Button>
            )}
            <Button variant="danger" onClick={() => void clearCredentials()} loading={loading === "emailClearCredentials"} disabled={!configured}>
              Clear credentials
            </Button>
          </div>
        </div>
      </div>

      {capabilities ? (
        <div className="rounded-md border border-app-border bg-zinc-950 p-4">
          <p className="text-sm font-medium text-app-text">Capabilities</p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            <CapabilityRow label="Search emails" enabled={capabilities.search_email || capabilities.search_emails} />
            <CapabilityRow label="Read email" enabled={capabilities.read_email} />
            <CapabilityRow label="List labels/folders" enabled={capabilities.list_folders} />
            <CapabilityRow label="Send email" enabled={capabilities.send_email} note={capabilities.send_email ? "Requires preview and confirmation in Tasks" : undefined} />
            <CapabilityRow label="Delete/modify email" enabled={false} note={capabilities.delete_email || capabilities.modify_email ? "Provider exposes it; disabled in MindOS" : undefined} />
          </div>
        </div>
      ) : null}

      {connected ? (
        <div className="rounded-md border border-app-border bg-zinc-950 p-4">
          <p className="text-sm font-medium text-app-text">Sync</p>
          <p className="mt-1 text-xs text-app-muted">Fetch read-only email context into MindOS memory. Attachments are listed but not downloaded.</p>
          <div className="mt-3 space-y-3">
            <label className="block text-xs font-medium uppercase text-app-muted">
              Scope
              <select
                className="mt-2 w-full rounded-md border border-app-border bg-zinc-900 px-3 py-2 text-sm normal-case text-app-text"
                value={scope}
                onChange={(event) => setScope(event.target.value as typeof scope)}
              >
                <option value="recent">Recent emails</option>
                <option value="unread">Unread emails</option>
                <option value="search">Search query</option>
              </select>
            </label>
            {scope === "search" ? <LabeledInput label="Search query" value={query} placeholder="deployment" onChange={setQuery} /> : null}
            <LabeledInput
              label="Max emails"
              type="number"
              value={String(maxItems)}
              onChange={(value) => setMaxItems(Math.max(1, Math.min(100, Number(value) || 25)))}
            />
            <Button variant="primary" onClick={() => void syncNow()} loading={loading === "emailSync"}>
              Sync now
            </Button>
          </div>
        </div>
      ) : null}

      <details className="rounded-md border border-app-border bg-zinc-950 p-4">
        <summary className="cursor-pointer text-sm font-medium text-app-text">Advanced tool mapping</summary>
        <div className="mt-4 space-y-3">
          <p className="text-xs leading-5 text-app-muted">
            MindOS calls read-only tools only. If your provider uses custom MCP tool names, map them here.
          </p>
          <LabeledInput label="Test tool" value={testTool} onChange={setTestTool} />
          <LabeledInput label="Search tool" value={searchTool} onChange={setSearchTool} />
          <LabeledInput label="Read tool" value={getTool} onChange={setGetTool} />
          <LabeledInput label="List folders tool" value={foldersTool} onChange={setFoldersTool} />
          <Button variant="danger" onClick={() => void handleClearEvents()} loading={loading === "emailClearEvents"}>
            Clear email events
          </Button>
        </div>
      </details>

      {syncResult ? (
        <CompactBlock title="Sync result">
          <Badge variant={syncResult.status === "success" ? "success" : "warning"}>{syncResult.status}</Badge>
          <Badge>seen: {syncResult.emails_seen}</Badge>
          <Badge>imported: {syncResult.imported_count}</Badge>
          <Badge>updated: {syncResult.updated_count}</Badge>
          <Badge variant={syncResult.failed_count ? "danger" : "default"}>failed: {syncResult.failed_count}</Badge>
        </CompactBlock>
      ) : null}
      {syncResult?.warnings.length ? <StatusMessage message={syncResult.warnings.slice(0, 2).join(" ")} variant="warning" /> : null}
      {message ? <p className="text-sm text-app-muted">{message}</p> : null}
    </div>
  );

  async function clearCredentials() {
    if (!window.confirm("Clear Email MCP credentials and configuration? Synced memory events will remain.")) return;
    setLoading("emailClearCredentials");
    setMessage(null);
    try {
      await disconnectEmail();
      const response = await saveEmailConfig({
        provider_type: "email_mcp",
        provider_name: providerName,
        api_base_url: apiBaseUrl,
        auth_type: authType,
        auth_header_name: authHeaderName,
        api_key: "",
        account_label: accountLabel,
        tool_mapping: {
          test: testTool,
          search: searchTool,
          get: getTool,
          list_folders: foldersTool,
        },
      });
      setStatus(response);
      setApiKey("");
      setMessage("Email MCP credentials cleared.");
      onRefresh();
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    } finally {
      setLoading(null);
    }
  }
}

function CapabilityRow({ label, enabled, note }: { label: string; enabled: boolean; note?: string }) {
  return (
    <div className="rounded-md border border-app-border bg-zinc-900/60 px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm text-app-text">{label}</span>
        <Badge variant={enabled ? "success" : "default"}>{enabled ? "available" : "disabled"}</Badge>
      </div>
      {note ? <p className="mt-1 text-xs text-app-muted">{note}</p> : null}
    </div>
  );
}

function FileSystemPanel(props: Parameters<typeof ConfigurePanel>[0]) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  return (
    <div className="mt-5 space-y-5">
      <div className="rounded-md border border-app-border bg-zinc-950 p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-app-text">Connected folders</h3>
            <p className="mt-1 text-sm text-app-muted">Add a folder once. MindOS indexes readable files in the background and keeps them searchable.</p>
          </div>
          <Badge>background indexing</Badge>
        </div>
        <div className="mt-4 space-y-3">
          <LabeledInput label="Folder path" value={props.fileForm.folderPath} placeholder="D:\\Projects\\MindOS" onChange={(value) => props.setFileForm((current) => ({ ...current, folderPath: value }))} />
          <div className="grid grid-cols-2 gap-3">
            <LabeledInput label="Max files" type="number" value={String(props.fileForm.maxFiles)} onChange={(value) => props.setFileForm((current) => ({ ...current, maxFiles: Number(value) }))} />
            <LabeledInput label="Max depth" type="number" value={String(props.fileForm.maxDepth)} onChange={(value) => props.setFileForm((current) => ({ ...current, maxDepth: Number(value) }))} />
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Checkbox label="Recursive" checked={props.fileForm.recursive} onChange={(checked) => props.setFileForm((current) => ({ ...current, recursive: checked }))} />
            <Checkbox label="Index readable files" checked={props.fileForm.indexingEnabled} onChange={(checked) => props.setFileForm((current) => ({ ...current, indexingEnabled: checked }))} />
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="primary" onClick={props.onAddTrackedFolder} loading={props.loading === "addTrackedFolder"}>
              Add folder
            </Button>
            <Button variant="secondary" onClick={props.onClearEvents} loading={props.loading === "clear:file_system"}>
              Clear file memory
            </Button>
          </div>
          <p className="text-xs text-app-muted">Only folders you add here are indexed. Search reads indexed memory, not the live filesystem.</p>
        </div>
      </div>

      <div className="space-y-2">
        {props.savedSources.length === 0 ? (
          <div className="rounded-md border border-dashed border-app-border px-3 py-4 text-sm text-app-muted">No connected folders yet.</div>
        ) : (
          props.savedSources.map((source) => (
            <SavedSourceRow
              key={source.id}
              source={source}
              loading={props.loading}
              runLabel="Reindex"
              onRun={() => props.onRunSource(source)}
              onEdit={() => props.onEditSource(source)}
              onDelete={() => props.onDeleteSource(source)}
              onClear={() => props.onClearSource(source)}
            />
          ))
        )}
      </div>

      <div className="border-t border-app-border pt-4">
        <button type="button" className="text-sm font-medium text-violet-300 hover:text-violet-200" onClick={() => setShowAdvanced(!showAdvanced)}>
          {showAdvanced ? "Hide advanced import tools" : "Advanced import tools"}
        </button>
        {showAdvanced ? (
          <div className="mt-4 space-y-4">
            <LabeledInput label="Max MB per file" type="number" value={String(props.fileForm.maxFileSizeMb)} onChange={(value) => props.setFileForm((current) => ({ ...current, maxFileSizeMb: Number(value) }))} />
            <LabeledInput label="Extensions" value={props.fileForm.allowedExtensions} placeholder=".py,.ts,.md" onChange={(value) => props.setFileForm((current) => ({ ...current, allowedExtensions: value }))} />
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" onClick={props.onFilePreview} loading={props.loading === "filePreview"}>
                Preview old import
              </Button>
              <Button variant="secondary" onClick={props.onFileImport} loading={props.loading === "fileImport"}>
                Import once
              </Button>
              <Button variant="secondary" onClick={props.onSaveSource}>
                Save source manually
              </Button>
            </div>
            {props.filePreview ? <FilePreviewBlock preview={props.filePreview} /> : null}
            {props.fileResult ? <ImportResult result={props.fileResult} /> : null}
          </div>
        ) : null}
      </div>

      <div className="border-t border-app-border pt-4">
        <button type="button" className="text-sm font-medium text-violet-300 hover:text-violet-200" onClick={() => props.setShowHistory(!props.showHistory)}>
          {props.showHistory ? "Hide index history" : "View index history"}
        </button>
        {props.showHistory ? (
          <div className="mt-3 space-y-2">
            {props.importRuns.length === 0 ? (
              <p className="text-sm text-app-muted">No index runs.</p>
            ) : (
              props.importRuns.map((run) => <ImportRunRow key={run.id} run={run} />)
            )}
          </div>
        ) : null}
      </div>
    </div>
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
  sourceTitle = "Saved Sources",
  runLabel = "Re-import",
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
  sourceTitle?: string;
  runLabel?: string;
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
        <h3 className="text-sm font-semibold text-app-text">{sourceTitle}</h3>
        <div className="mt-3 space-y-2">
          {savedSources.length === 0 ? (
            <p className="text-sm text-app-muted">No saved sources.</p>
          ) : (
            savedSources.map((source) => (
              <SavedSourceRow
                key={source.id}
                source={source}
                loading={loading}
                runLabel={runLabel}
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
            <Checkbox label="Recursive indexing" checked={form.recursive} onChange={(checked) => setForm((current) => ({ ...current, recursive: checked }))} />
            <Checkbox label="Index readable files" checked={form.indexingEnabled} onChange={(checked) => setForm((current) => ({ ...current, indexingEnabled: checked }))} />
            <div className="grid grid-cols-2 gap-3">
              <LabeledInput label="Max files" type="number" value={String(form.maxFiles)} onChange={(value) => setForm((current) => ({ ...current, maxFiles: Number(value) }))} />
              <LabeledInput label="Max depth" type="number" value={String(form.maxDepth)} onChange={(value) => setForm((current) => ({ ...current, maxDepth: Number(value) }))} />
            </div>
            <LabeledInput label="Max MB per file" type="number" value={String(form.maxFileSizeMb)} onChange={(value) => setForm((current) => ({ ...current, maxFileSizeMb: Number(value) }))} />
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

function SavedSourceRow({ source, loading, runLabel = "Re-import", onRun, onEdit, onDelete, onClear }: {
  source: ConnectorSource;
  loading: string | null;
  runLabel?: string;
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
            {isTrackedFileSource(source) ? (
              <>
                <Badge variant={source.config?.index_status === "error" ? "danger" : source.config?.index_status === "indexing" || source.config?.index_status === "queued" ? "warning" : "success"}>
                  {String(source.config?.index_status ?? "idle")}
                </Badge>
                <Badge>files {Number(source.config?.file_count ?? 0)}</Badge>
                <Badge>inventory {Number(source.config?.inventory_count ?? source.config?.file_count ?? 0)}</Badge>
                <Badge>content indexed {Number(source.config?.content_indexed_count ?? source.config?.indexed_count ?? 0)}</Badge>
                {Number(source.config?.content_failed_count ?? 0) > 0 ? <Badge variant="warning">content failed {Number(source.config?.content_failed_count ?? 0)}</Badge> : null}
                <Badge>skipped {Number(source.config?.skipped_count ?? 0)}</Badge>
                {Number(source.config?.missing_count ?? 0) > 0 ? <Badge variant="warning">missing {Number(source.config?.missing_count ?? 0)}</Badge> : null}
                {typeof source.config?.next_index_after === "string" ? <Badge>next {formatDate(source.config.next_index_after)}</Badge> : null}
              </>
            ) : null}
          </div>
          {isTrackedFileSource(source) && typeof source.config?.last_error === "string" && source.config.last_error ? (
            <p className="mt-2 text-xs text-red-200">{source.config.last_error}</p>
          ) : null}
          {isTrackedFileSource(source) ? <ContentFailedFilesDetails source={source} /> : null}
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button className="h-8 px-3 text-xs" variant="primary" onClick={onRun} loading={loading === `run:${source.id}`}>
          {isTrackedFileSource(source) ? "Reindex" : runLabel}
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

function ContentFailedFilesDetails({ source }: { source: ConnectorSource }) {
  const failedFiles = contentFailedFiles(source);
  if (!failedFiles.length) return null;
  return (
    <details className="mt-3 rounded-md border border-amber-500/20 bg-amber-500/5 px-3 py-2">
      <summary className="cursor-pointer text-xs font-medium text-amber-100">Content extraction failed</summary>
      <div className="mt-2 space-y-2">
        {failedFiles.slice(0, 8).map((file, index) => (
          <div key={`${file.relative_path}-${index}`} className="text-xs">
            <p className="truncate text-app-text">{file.file_name || file.relative_path}</p>
            <p className="mt-0.5 text-app-muted">
              {file.reason || "Content extraction failed."}
              {file.is_attachable ? " File is still searchable by name and attachable." : ""}
            </p>
          </div>
        ))}
        {failedFiles.length > 8 ? <p className="text-xs text-app-muted">+ {failedFiles.length - 8} more</p> : null}
      </div>
    </details>
  );
}

function contentFailedFiles(source: ConnectorSource) {
  const raw = source.config?.content_failed_files;
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
    .map((item) => ({
      relative_path: String(item.relative_path ?? ""),
      file_name: String(item.file_name ?? item.relative_path ?? ""),
      reason: String(item.reason ?? ""),
      is_attachable: Boolean(item.is_attachable),
    }));
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

function LabeledTextarea({ label, value, onChange, placeholder }: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="block text-xs font-medium uppercase text-app-muted">
      {label}
      <textarea
        className="mt-2 min-h-20 w-full rounded-md border border-app-border bg-zinc-900 px-3 py-2 text-sm normal-case text-app-text placeholder:text-app-muted"
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
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
  const variant = status === "connected" ? "success" : status === "configured" ? "warning" : status === "disconnected" || status === "needs_configuration" ? "warning" : status === "error" ? "danger" : "default";
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
    gmail: Mail,
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

function toTrackedFolderPayload(form: FileForm) {
  return {
    path: form.folderPath.trim(),
    indexing_enabled: form.indexingEnabled,
    recursive: form.recursive,
    max_files: clampNumber(form.maxFiles, 1, 5000),
    max_depth: clampNumber(form.maxDepth, 0, 10),
    max_file_size_mb: clampNumber(form.maxFileSizeMb, 1, 25),
    allowed_extensions: parseExtensions(form.allowedExtensions) ?? defaultIndexedExtensions.split(","),
    exclude_patterns: ["node_modules", ".git", "dist", "build", "__pycache__"],
    index_interval_minutes: 20,
    enabled: true,
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
    maxFiles: numberConfig(config.max_files, 2000),
    maxDepth: numberConfig(config.max_depth, 5),
    maxFileSizeMb: numberConfig(config.max_file_size_mb, 5),
    maxFileSizeKb: numberConfig(config.max_file_size_kb, 256),
    allowedExtensions: Array.isArray(config.include_patterns)
      ? config.include_patterns.join(",")
      : Array.isArray(config.allowed_extensions)
        ? config.allowed_extensions.join(",")
        : defaultIndexedExtensions,
    indexingEnabled: booleanConfig(config.indexing_enabled, true),
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
    return {
      ...base,
      config: {
        indexing_enabled: form.indexingEnabled,
        recursive: form.recursive,
        max_files: clampNumber(form.maxFiles, 1, 5000),
        max_depth: clampNumber(form.maxDepth, 0, 10),
        max_file_size_mb: clampNumber(form.maxFileSizeMb, 1, 25),
        max_file_size_kb: clampNumber(form.maxFileSizeKb, 1, 2048),
        include_patterns: parseExtensions(form.allowedExtensions),
        allowed_extensions: parseExtensions(form.allowedExtensions),
        exclude_patterns: ["node_modules", ".git", "dist", "build", "__pycache__"],
      },
    };
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

function isTrackedFileSource(source: ConnectorSource) {
  return source.connector_type === "file_system" && source.config?.indexing_enabled === true;
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
