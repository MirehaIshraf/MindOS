import * as crypto from "node:crypto";
import * as path from "node:path";
import * as vscode from "vscode";
import { EventQueue } from "./eventQueue";
import { getGitInfo } from "./gitInfo";
import { MindOSClient } from "./mindosClient";
import { containsSensitiveContent, shouldIgnoreFile } from "./privacy";
import type { MindOSConfig, MindOSEvent, VSCodeRuntime } from "./types";

const EXTENSION_VERSION = "0.1.0";
const OPEN_DEBOUNCE_MS = 60_000;
const SAVE_DEBOUNCE_MS = 10_000;
const RUNTIME_POLL_MS = 5_000;
const HEARTBEAT_MS = 30_000;

let statusBarItem: vscode.StatusBarItem;
let sessionId = "";
let runtime: VSCodeRuntime | null = null;
let backendReachable = false;
let workspaceOpenedSent = false;
let runtimePollTimer: NodeJS.Timeout | undefined;
let heartbeatTimer: NodeJS.Timeout | undefined;

const queue = new EventQueue();
const openDebounce = new Map<string, number>();
const saveDebounce = new Map<string, number>();

export function activate(context: vscode.ExtensionContext): void {
  sessionId = crypto.randomUUID();
  statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  statusBarItem.command = "mindos.showQuickActions";
  context.subscriptions.push(statusBarItem);

  context.subscriptions.push(
    vscode.commands.registerCommand("mindos.connect", enableLocalCollectionCommand),
    vscode.commands.registerCommand("mindos.disconnect", disableLocalCollectionCommand),
    vscode.commands.registerCommand("mindos.enableLocalCollection", enableLocalCollectionCommand),
    vscode.commands.registerCommand("mindos.disableLocalCollection", disableLocalCollectionCommand),
    vscode.commands.registerCommand("mindos.testConnection", testConnectionCommand),
    vscode.commands.registerCommand("mindos.openSettings", openSettingsCommand),
    vscode.commands.registerCommand("mindos.openMindOS", openMindOSCommand),
    vscode.commands.registerCommand("mindos.showQuickActions", showQuickActionsCommand),
    vscode.commands.registerCommand("mindos.enableConnector", enableLocalCollectionCommand),
    vscode.commands.registerCommand("mindos.disableConnector", disableLocalCollectionCommand),
    vscode.commands.registerCommand("mindos.flushQueue", flushQueueCommand),
    vscode.window.onDidChangeActiveTextEditor((editor) => {
      void handleActiveEditorChanged(editor);
    }),
    vscode.workspace.onDidSaveTextDocument((document) => {
      void handleDocumentSaved(document);
    }),
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (event.affectsConfiguration("mindos")) {
        void pollRuntime();
      }
    }),
  );

  startController(context);
}

export function deactivate(): void {
  if (runtimePollTimer) {
    clearInterval(runtimePollTimer);
  }
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer);
  }
  statusBarItem?.dispose();
}

function startController(context: vscode.ExtensionContext): void {
  void pollRuntime();
  runtimePollTimer = setInterval(() => void pollRuntime(), RUNTIME_POLL_MS);
  heartbeatTimer = setInterval(() => void sendHeartbeat(), HEARTBEAT_MS);
  context.subscriptions.push({
    dispose: () => {
      if (runtimePollTimer) {
        clearInterval(runtimePollTimer);
      }
      if (heartbeatTimer) {
        clearInterval(heartbeatTimer);
      }
    },
  });
}

async function pollRuntime(): Promise<void> {
  const config = getConfig();
  const previousEnabled = runtime?.enabled ?? false;
  try {
    const nextRuntime = await clientFromConfig(config).getVSCodeRuntime();
    backendReachable = true;
    runtime = nextRuntime;
    if (!nextRuntime.enabled) {
      workspaceOpenedSent = false;
    }
    await updateStatusBar();
    if (canCollect() && (!previousEnabled || !workspaceOpenedSent)) {
      await sendWorkspaceOpened();
      await maybeSendActiveEditorOpened();
    }
  } catch {
    backendReachable = false;
    await updateStatusBar();
  }
}

async function testConnectionCommand(): Promise<void> {
  const config = getConfig();
  const client = clientFromConfig(config);
  const healthOk = await client.testConnection();
  let runtimeState = "unavailable";
  try {
    runtime = await client.getVSCodeRuntime();
    backendReachable = true;
    runtimeState = runtime.enabled ? runtime.status : "off";
  } catch {
    backendReachable = healthOk;
  }
  await updateStatusBar();
  if (healthOk) {
    vscode.window.showInformationMessage(`MindOS backend connected. VSCode connector: ${runtimeState}.`);
  } else {
    vscode.window.showWarningMessage(`Could not connect to MindOS at ${config.backendUrl}`);
  }
}

async function enableLocalCollectionCommand(): Promise<void> {
  await vscode.workspace.getConfiguration("mindos").update("enabled", true, vscode.ConfigurationTarget.Global);
  vscode.window.showInformationMessage("MindOS local collection enabled. Use the MindOS Connectors page to turn VSCode collection on or off.");
  await pollRuntime();
}

async function disableLocalCollectionCommand(): Promise<void> {
  await vscode.workspace.getConfiguration("mindos").update("enabled", false, vscode.ConfigurationTarget.Global);
  vscode.window.showInformationMessage("MindOS local collection disabled.");
  await updateStatusBar();
}

async function openSettingsCommand(): Promise<void> {
  await vscode.commands.executeCommand("workbench.action.openSettings", "mindos");
}

async function openMindOSCommand(): Promise<void> {
  await vscode.env.openExternal(vscode.Uri.parse("http://localhost:5173/connectors"));
}

async function showQuickActionsCommand(): Promise<void> {
  const localEnabled = getConfig().enabled;
  const choice = await vscode.window.showQuickPick(
    [
      "Open MindOS Connector Settings",
      "Test Connection",
      "Flush Queue",
      localEnabled ? "Disable Local Collection" : "Enable Local Collection",
    ],
    { placeHolder: "MindOS" },
  );
  if (choice === "Open MindOS Connector Settings") {
    await openMindOSCommand();
  } else if (choice === "Test Connection") {
    await testConnectionCommand();
  } else if (choice === "Flush Queue") {
    await flushQueueCommand();
  } else if (choice === "Disable Local Collection") {
    await disableLocalCollectionCommand();
  } else if (choice === "Enable Local Collection") {
    await enableLocalCollectionCommand();
  }
}

async function flushQueueCommand(): Promise<void> {
  if (!canCollect()) {
    vscode.window.showWarningMessage("MindOS queue was not flushed because the connector is off or offline.");
    return;
  }
  const result = await queue.flushQueue(clientFromConfig(getConfig()));
  vscode.window.showInformationMessage(`MindOS queue flush: sent ${result.sent}, remaining ${result.remaining}`);
  await pollRuntime();
}

async function handleActiveEditorChanged(editor: vscode.TextEditor | undefined): Promise<void> {
  if (!canCollect() || !runtime?.capture_file_open || !getConfig().captureFileOpen || !editor || editor.document.uri.scheme !== "file") {
    return;
  }
  await sendFileOpened(editor.document);
}

async function handleDocumentSaved(document: vscode.TextDocument): Promise<void> {
  if (!canCollect() || !runtime?.capture_file_save || !getConfig().captureFileSave || document.uri.scheme !== "file") {
    return;
  }
  const config = getConfig();
  const filePath = document.uri.fsPath;
  if (shouldIgnoreFile(filePath, config.excludeGlobs) || isDebounced(saveDebounce, filePath, SAVE_DEBOUNCE_MS)) {
    return;
  }
  saveDebounce.set(filePath, Date.now());

  const metadata = await fileMetadata(document.uri, document.languageId);
  let contentIncluded = false;
  let content = `Saved file ${metadata.relative_path}`;
  if (runtime.include_file_content_on_save && config.includeFileContentOnSave) {
    const text = document.getText();
    if (!containsSensitiveContent(text)) {
      const snippet = text.slice(0, Math.max(0, runtime.max_content_chars ?? config.maxContentChars));
      content = `${content}\n\n${snippet}`;
      contentIncluded = snippet.length > 0;
    }
  }

  await sendOrQueue({
    source: "vscode_extension",
    type: "editor_file_saved",
    title: `Saved ${metadata.file_name}`,
    content,
    metadata: { ...metadata, content_included: contentIncluded },
    timestamp: null,
    client_id: config.clientId,
    session_id: sessionId,
  });
}

async function sendWorkspaceOpened(): Promise<void> {
  if (!canCollect() || !runtime?.capture_workspace_open || !getConfig().captureWorkspaceOpen || workspaceOpenedSent) {
    return;
  }
  workspaceOpenedSent = true;
  const config = getConfig();
  const workspaceName = vscode.workspace.name ?? "Untitled Workspace";
  const folders = vscode.workspace.workspaceFolders ?? [];
  const gitInfo = await getGitInfo(folders[0]?.uri);
  await sendOrQueue({
    source: "vscode_extension",
    type: "editor_workspace_opened",
    title: `Opened workspace: ${workspaceName}`,
    content: "VSCode workspace opened.",
    metadata: {
      workspace_name: workspaceName,
      workspace_folders: folders.map((folder) => folder.uri.fsPath),
      git_branch: gitInfo.branch,
      repo_name: gitInfo.repoName,
      repo_root: gitInfo.repoRoot,
      extension_version: EXTENSION_VERSION,
    },
    timestamp: null,
    client_id: config.clientId,
    session_id: sessionId,
  });
}

async function maybeSendActiveEditorOpened(): Promise<void> {
  if (!runtime?.capture_file_open || !getConfig().captureFileOpen || !vscode.window.activeTextEditor) {
    return;
  }
  await sendFileOpened(vscode.window.activeTextEditor.document);
}

async function sendFileOpened(document: vscode.TextDocument): Promise<void> {
  const config = getConfig();
  const filePath = document.uri.fsPath;
  if (document.uri.scheme !== "file" || shouldIgnoreFile(filePath, config.excludeGlobs) || isDebounced(openDebounce, filePath, OPEN_DEBOUNCE_MS)) {
    return;
  }
  openDebounce.set(filePath, Date.now());
  const metadata = await fileMetadata(document.uri, document.languageId);
  await sendOrQueue({
    source: "vscode_extension",
    type: "editor_file_opened",
    title: `Opened ${metadata.file_name}`,
    content: `Opened file ${metadata.relative_path}`,
    metadata,
    timestamp: null,
    client_id: config.clientId,
    session_id: sessionId,
  });
}

async function sendHeartbeat(): Promise<void> {
  if (!backendReachable || !canCollect()) {
    return;
  }
  const config = getConfig();
  const folders = vscode.workspace.workspaceFolders ?? [];
  try {
    const response = await clientFromConfig(config).sendVSCodeHeartbeat({
      client_id: config.clientId,
      extension_version: EXTENSION_VERSION,
      workspace_name: vscode.workspace.name,
      workspace_folders: folders.map((folder) => folder.uri.fsPath),
      session_id: sessionId,
      status: "active",
    });
    if (!response.connector_enabled && runtime) {
      runtime = { ...runtime, enabled: false, status: "off" };
      workspaceOpenedSent = false;
    }
    await updateStatusBar();
  } catch {
    backendReachable = false;
    await updateStatusBar();
  }
}

async function sendOrQueue(event: MindOSEvent): Promise<void> {
  if (!canCollect()) {
    return;
  }
  const config = getConfig();
  try {
    await clientFromConfig(config).sendEvent(event);
    backendReachable = true;
    await updateStatusBar();
    if (queue.size() > 0) {
      void queue.flushQueue(clientFromConfig(config));
    }
  } catch {
    queue.enqueue(event);
    backendReachable = false;
    await updateStatusBar();
  }
}

function canCollect(): boolean {
  return getConfig().enabled && backendReachable && Boolean(runtime?.enabled);
}

async function updateStatusBar(): Promise<void> {
  const config = getConfig();
  if (!config.enabled || (backendReachable && runtime && !runtime.enabled)) {
    statusBarItem.text = "MindOS: Off";
  } else if (!backendReachable) {
    statusBarItem.text = "MindOS: Offline";
  } else {
    statusBarItem.text = "MindOS: Connected";
  }
  statusBarItem.tooltip = `MindOS backend: ${config.backendUrl}. Queued events: ${queue.size()}`;
  statusBarItem.show();
}

async function fileMetadata(resource: vscode.Uri, language: string): Promise<Record<string, unknown>> {
  const workspaceFolder = vscode.workspace.getWorkspaceFolder(resource);
  const relativePath = workspaceFolder ? path.relative(workspaceFolder.uri.fsPath, resource.fsPath) : path.basename(resource.fsPath);
  const gitInfo = await getGitInfo(resource);
  return {
    file_path: resource.fsPath,
    relative_path: relativePath,
    file_name: path.basename(resource.fsPath),
    language,
    workspace_name: vscode.workspace.name,
    workspace_path: workspaceFolder?.uri.fsPath,
    git_branch: gitInfo.branch,
    repo_name: gitInfo.repoName,
    repo_root: gitInfo.repoRoot,
  };
}

function clientFromConfig(config: MindOSConfig): MindOSClient {
  return new MindOSClient(config.backendUrl);
}

function getConfig(): MindOSConfig {
  const config = vscode.workspace.getConfiguration("mindos");
  return {
    backendUrl: config.get("backendUrl", "http://localhost:8000"),
    enabled: config.get("enabled", true),
    clientId: config.get("clientId", "vscode-local"),
    captureFileOpen: config.get("captureFileOpen", false),
    captureFileSave: config.get("captureFileSave", true),
    captureWorkspaceOpen: config.get("captureWorkspaceOpen", true),
    captureTerminalCommands: config.get("captureTerminalCommands", false),
    includeFileContentOnSave: config.get("includeFileContentOnSave", false),
    maxContentChars: config.get("maxContentChars", 2000),
    excludeGlobs: config.get("excludeGlobs", []),
  };
}

function isDebounced(cache: Map<string, number>, key: string, intervalMs: number): boolean {
  const previous = cache.get(key) ?? 0;
  return Date.now() - previous < intervalMs;
}
