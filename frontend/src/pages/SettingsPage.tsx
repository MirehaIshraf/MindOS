import { Cloud, Cpu, DatabaseZap, KeyRound, RefreshCw, Settings } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "../components/shared/Badge";
import { Button } from "../components/shared/Button";
import { Card } from "../components/shared/Card";
import { Input } from "../components/shared/Input";
import { getEmbeddingStatus, getErrorMessage, getModelSettings, selectChatModel, setModelEnabled, updateProviderConfig } from "../services/api";
import type { EmbeddingStatusResponse, ModelConfig, ModelProvider, ModelSettingsResponse } from "../types";

const installCommands: Record<string, string> = {
  "ollama-llama3.2": "ollama pull llama3.2",
  "ollama-qwen3": "ollama pull qwen3:8b",
  "ollama-mistral": "ollama pull mistral",
};

export function SettingsPage() {
  const [settings, setSettings] = useState<ModelSettingsResponse | null>(null);
  const [embeddingStatus, setEmbeddingStatus] = useState<EmbeddingStatusResponse | null>(null);
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({});
  const [baseUrls, setBaseUrls] = useState<Record<string, string>>({});
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void refreshSettings();
  }, []);

  const enabledChatModels = useMemo(
    () => settings?.models.filter((model) => model.enabled && model.configured) ?? [],
    [settings],
  );
  const localModels = settings?.models.filter((model) => model.type === "local") ?? [];
  const cloudProviders = settings?.providers.filter((provider) => provider.type === "cloud") ?? [];

  async function refreshSettings() {
    setLoadingAction("refresh");
    setError(null);
    try {
      const [modelSettings, embeddings] = await Promise.all([getModelSettings(), getEmbeddingStatus()]);
      setSettings(modelSettings);
      setEmbeddingStatus(embeddings);
    } catch (caughtError) {
      console.error("SettingsPage failed to load model settings", caughtError);
      setError(getErrorMessage(caughtError));
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleSelectModel(modelId: string) {
    setLoadingAction("select");
    setError(null);
    setMessage(null);
    const previous = settings;
    setSettings((current) => (current ? { ...current, selected_chat_model: modelId } : current));
    try {
      await selectChatModel(modelId);
      setSettings(await getModelSettings());
      setMessage("Default chat model updated.");
    } catch (caughtError) {
      console.error("SettingsPage failed to select model", caughtError);
      setSettings(previous);
      setError(getErrorMessage(caughtError));
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleToggleModel(model: ModelConfig, enabled: boolean) {
    setLoadingAction(model.id);
    setError(null);
    setMessage(null);
    try {
      await setModelEnabled(model.id, enabled);
      setSettings(await getModelSettings());
      setMessage(`${model.display_name} ${enabled ? "enabled" : "disabled"}.`);
    } catch (caughtError) {
      console.error("SettingsPage failed to toggle model", caughtError);
      setError(getErrorMessage(caughtError));
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleSaveProvider(provider: ModelProvider) {
    setLoadingAction(provider.id);
    setError(null);
    setMessage(null);
    try {
      await updateProviderConfig({
        provider: provider.id,
        api_key: apiKeys[provider.id] ?? null,
        base_url: baseUrls[provider.id] ?? null,
        enabled: true,
      });
      setSettings(await getModelSettings());
      setApiKeys((current) => ({ ...current, [provider.id]: "" }));
      setMessage(`${provider.name} configuration saved.`);
    } catch (caughtError) {
      console.error("SettingsPage failed to save provider config", caughtError);
      setError(getErrorMessage(caughtError));
    } finally {
      setLoadingAction(null);
    }
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-app-text">Settings</h1>
          <p className="mt-2 text-sm text-app-muted">Configure which models MindOS can use for chat.</p>
        </div>
        <Button variant="secondary" onClick={refreshSettings} loading={loadingAction === "refresh"}>
          <RefreshCw size={16} />
          Refresh
        </Button>
      </header>

      {error ? <StatusMessage variant="danger" message={error} /> : null}
      {message ? <StatusMessage variant="success" message={message} /> : null}

      <Card>
        <SectionHeader icon={<Settings size={18} />} title="Default Chat Model" />
        <div className="mt-4 grid gap-4 md:grid-cols-[1fr_auto] md:items-end">
          <label className="block text-xs font-medium uppercase text-app-muted">
            Enabled models
            <select
              value={settings?.selected_chat_model ?? ""}
              onChange={(event) => void handleSelectModel(event.target.value)}
              disabled={enabledChatModels.length === 0 || loadingAction === "select"}
              className="mt-2 h-10 w-full rounded-md border border-app-border bg-zinc-950 px-3 text-sm text-app-text outline-none focus:border-app-primary"
            >
              {enabledChatModels.length === 0 ? (
                <option value="">FakeLLM fallback</option>
              ) : (
                enabledChatModels.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.display_name}
                  </option>
                ))
              )}
            </select>
          </label>
          <PrivacyBadge model={settings?.models.find((model) => model.id === settings.selected_chat_model)} />
        </div>
      </Card>

      <section className="space-y-4">
        <SectionTitle icon={<Cpu size={18} />} title="Local Models" />
        <div className="grid gap-4 lg:grid-cols-3">
          {localModels.map((model) => (
            <Card key={model.id}>
              <ModelCardHeader model={model} />
              <p className="mt-3 text-sm leading-6 text-app-muted">{model.description}</p>
              <div className="mt-4 space-y-2 text-sm">
                <Row label="model id" value={model.model_id} />
                <Row label="status" value={model.configured ? "Available in Ollama" : "Not installed"} tone={model.configured ? "success" : "warning"} />
              </div>
              {!model.configured ? (
                <p className="mt-4 rounded-md border border-app-border bg-zinc-950 px-3 py-2 font-mono text-xs text-app-muted">
                  {installCommands[model.id]}
                </p>
              ) : null}
              <ToggleRow
                checked={model.enabled}
                disabled={!model.configured || loadingAction === model.id}
                label="Enable in Chat"
                onChange={(enabled) => void handleToggleModel(model, enabled)}
              />
            </Card>
          ))}
        </div>
      </section>

      <section className="space-y-4">
        <SectionTitle icon={<Cloud size={18} />} title="Cloud Models" />
        <p className="text-sm text-amber-200">Cloud models send selected memory context to this provider.</p>
        <p className="text-xs text-app-muted">Development storage: API keys are stored locally. Later use OS keychain.</p>
        <div className="space-y-3">
          {cloudProviders.map((provider) => (
            <ProviderPanel
              key={provider.id}
              provider={provider}
              models={settings?.models.filter((model) => model.provider === provider.id) ?? []}
              apiKey={apiKeys[provider.id] ?? ""}
              baseUrl={baseUrls[provider.id] ?? ""}
              loadingAction={loadingAction}
              onApiKeyChange={(value) => setApiKeys((current) => ({ ...current, [provider.id]: value }))}
              onBaseUrlChange={(value) => setBaseUrls((current) => ({ ...current, [provider.id]: value }))}
              onSave={() => void handleSaveProvider(provider)}
              onToggle={(model, enabled) => void handleToggleModel(model, enabled)}
            />
          ))}
        </div>
      </section>

      <Card>
        <SectionHeader icon={<DatabaseZap size={18} />} title="Memory Search" />
        <div className="mt-4 space-y-3 text-sm">
          <Row label="semantic search" value={embeddingStatus?.enabled ? "enabled" : "disabled"} tone={embeddingStatus?.enabled ? "success" : "warning"} />
          <Row label="embedding model" value={embeddingStatus?.embedding_model ?? "nomic-embed-text"} />
          <Row label="Chroma" value={embeddingStatus?.chroma_available ? "available" : "unavailable"} tone={embeddingStatus?.chroma_available ? "success" : "warning"} />
          <Row label="indexed memories" value={String(embeddingStatus?.indexed_count ?? 0)} />
        </div>
        <p className="mt-4 rounded-md border border-violet-500/30 bg-violet-500/10 px-3 py-2 text-sm leading-6 text-violet-100">
          Semantic search uses local Ollama embeddings. Memory content stays on this machine.
        </p>
        <p className="mt-3 rounded-md border border-app-border bg-zinc-950 px-3 py-2 font-mono text-xs text-app-muted">
          ollama pull nomic-embed-text
        </p>
        <p className="mt-3 text-xs leading-5 text-app-muted">
          To enable semantic search, set ENABLE_EMBEDDINGS=true in backend/.env and restart the backend.
        </p>
      </Card>
    </div>
  );
}

function ProviderPanel({
  provider,
  models,
  apiKey,
  baseUrl,
  loadingAction,
  onApiKeyChange,
  onBaseUrlChange,
  onSave,
  onToggle,
}: {
  provider: ModelProvider;
  models: ModelConfig[];
  apiKey: string;
  baseUrl: string;
  loadingAction: string | null;
  onApiKeyChange: (value: string) => void;
  onBaseUrlChange: (value: string) => void;
  onSave: () => void;
  onToggle: (model: ModelConfig, enabled: boolean) => void;
}) {
  return (
    <details className="rounded-lg border border-app-border bg-app-panel p-4">
      <summary className="cursor-pointer list-none">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-md border border-violet-500/30 bg-violet-500/10 text-violet-300">
              <KeyRound size={18} />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-app-text">{provider.name}</h3>
              <p className="text-xs text-app-muted">{provider.privacy_note}</p>
            </div>
          </div>
          <Badge variant={provider.configured ? "success" : "warning"}>{provider.configured ? "configured" : "not configured"}</Badge>
        </div>
      </summary>

      <div className="mt-5 grid gap-3 md:grid-cols-[1fr_auto] md:items-end">
        <label className="block text-xs font-medium uppercase text-app-muted">
          API key
          <Input className="mt-2" type="password" value={apiKey} onChange={(event) => onApiKeyChange(event.target.value)} />
        </label>
        <Button variant="primary" onClick={onSave} loading={loadingAction === provider.id}>
          Save
        </Button>
      </div>

      {provider.id === "kimi" ? (
        <label className="mt-3 block text-xs font-medium uppercase text-app-muted">
          Base URL
          <Input className="mt-2" value={baseUrl} onChange={(event) => onBaseUrlChange(event.target.value)} />
        </label>
      ) : null}

      <div className="mt-5 space-y-3">
        {models.map((model) => (
          <div key={model.id} className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-app-border bg-zinc-950 px-3 py-2">
            <div>
              <p className="text-sm font-medium text-app-text">{model.display_name}</p>
              <p className="text-xs text-app-muted">{model.model_id}</p>
            </div>
            <ToggleRow
              checked={model.enabled}
              disabled={!provider.configured || loadingAction === model.id}
              label="Enable"
              onChange={(enabled) => onToggle(model, enabled)}
            />
          </div>
        ))}
      </div>
    </details>
  );
}

function SectionHeader({ icon, title }: { icon: ReactNode; title: string }) {
  return (
    <div className="flex items-center gap-3">
      <div className="flex h-9 w-9 items-center justify-center rounded-md border border-violet-500/30 bg-violet-500/10 text-violet-300">
        {icon}
      </div>
      <h2 className="text-base font-semibold text-app-text">{title}</h2>
    </div>
  );
}

function SectionTitle({ icon, title }: { icon: ReactNode; title: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-violet-300">{icon}</span>
      <h2 className="text-base font-semibold text-app-text">{title}</h2>
    </div>
  );
}

function ModelCardHeader({ model }: { model: ModelConfig }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div>
        <h3 className="text-base font-semibold text-app-text">{model.display_name}</h3>
        <p className="mt-1 text-xs text-app-muted">{model.privacy_level === "local_private" ? "Local/private" : "Cloud/external"}</p>
      </div>
      <Badge variant={model.enabled && model.configured ? "success" : "default"}>{model.enabled && model.configured ? "enabled" : "off"}</Badge>
    </div>
  );
}

function PrivacyBadge({ model }: { model?: ModelConfig }) {
  if (!model) {
    return <Badge variant="default">FakeLLM fallback</Badge>;
  }
  return <Badge variant={model.type === "cloud" ? "warning" : "success"}>{model.type === "cloud" ? "Cloud/external" : "Local/private"}</Badge>;
}

function ToggleRow({
  checked,
  disabled,
  label,
  onChange,
}: {
  checked: boolean;
  disabled?: boolean;
  label: string;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="mt-4 flex items-center justify-between gap-3 text-sm text-app-muted">
      <span>{label}</span>
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        className="h-4 w-4 accent-violet-500"
      />
    </label>
  );
}

function Row({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "success" | "warning" }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-app-muted">{label}</span>
      <Badge variant={tone === "success" ? "success" : tone === "warning" ? "warning" : "default"}>{value}</Badge>
    </div>
  );
}

function StatusMessage({ variant, message }: { variant: "success" | "danger"; message: string }) {
  return (
    <div
      className={`rounded-md border px-4 py-3 text-sm ${
        variant === "success"
          ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
          : "border-red-500/30 bg-red-500/10 text-red-200"
      }`}
    >
      {message}
    </div>
  );
}
