import axios from "axios";
import { Cable, FolderOpen, RefreshCw, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "../components/shared/Badge";
import { Button } from "../components/shared/Button";
import { Card } from "../components/shared/Card";
import { Input } from "../components/shared/Input";
import { getConnectors, importFiles, previewFileImport } from "../services/api";
import type { Connector, FileImportPayload, FileImportResult, FilePreviewResult } from "../types";

const emptyForm = {
  folderPath: "",
  recursive: true,
  maxFiles: 100,
  maxFileSizeKb: 256,
  allowedExtensions: "",
};

type ImportForm = typeof emptyForm;

export function ConnectorsPage() {
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [panelOpen, setPanelOpen] = useState(false);
  const [form, setForm] = useState<ImportForm>(emptyForm);
  const [preview, setPreview] = useState<FilePreviewResult | null>(null);
  const [result, setResult] = useState<FileImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
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

  async function handleImport() {
    setLoading("import");
    setError(null);
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
  const otherConnectors = connectors.filter((connector) => connector.name !== "file_system");

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

      <div className="grid grid-cols-[1fr_420px] gap-4">
        <div className="space-y-4">
          {fileSystem ? (
            <ConnectorCard connector={fileSystem} active onImport={() => setPanelOpen(true)} />
          ) : (
            <Card>
              <p className="text-sm text-app-muted">File System connector is unavailable.</p>
            </Card>
          )}

          <div className="grid grid-cols-2 gap-4">
            {otherConnectors.map((connector) => (
              <ConnectorCard key={connector.name} connector={connector} />
            ))}
          </div>
        </div>

        {panelOpen ? (
          <ImportPanel
            form={form}
            setForm={setForm}
            loading={loading}
            preview={preview}
            result={result}
            onClose={() => setPanelOpen(false)}
            onPreview={handlePreview}
            onImport={handleImport}
          />
        ) : (
          <Card className="min-h-72">
            <div className="flex h-full flex-col items-center justify-center text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-md border border-violet-500/30 bg-violet-500/10 text-violet-300">
                <Cable size={24} />
              </div>
              <h2 className="mt-4 text-base font-semibold text-app-text">No connector selected</h2>
              <p className="mt-2 max-w-sm text-sm leading-6 text-app-muted">Start with a manual File System import.</p>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}

function ConnectorCard({ connector, active = false, onImport }: { connector: Connector; active?: boolean; onImport?: () => void }) {
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
          <Badge variant="info">events: {connector.events_count ?? 0}</Badge>
          {connector.last_event_at ? <Badge>last: {formatTimestamp(connector.last_event_at)}</Badge> : null}
          <Button variant="primary" onClick={onImport}>
            Import Folder
          </Button>
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
