import { ChevronRight, FileText, FolderOpen, Github, ListChecks, Mail, Paperclip, Play, Search, Sparkles, X } from "lucide-react";
import { KeyboardEvent, ReactNode, RefObject, useEffect, useMemo, useRef, useState } from "react";

import { Badge } from "../components/shared/Badge";
import { Button } from "../components/shared/Button";
import { Card } from "../components/shared/Card";
import {
  clearTaskHistory,
  completeDocumentSummary,
  createGmailDraftWithAttachments,
  executeTaskAction,
  getErrorMessage,
  getGmailRecentEmails,
  getGmailStatus,
  getModelSettings,
  getTaskActionCapabilities,
  getTrackedFolders,
  prepareTaskIntent,
  prepareFileTaskPlan,
  prepareGmailDraft,
  prepareIndexedDocumentSummary,
  prepareLogAnalysisReport,
  resolveIndexedAttachments,
  saveGeneratedSummaryOutput,
  saveLogAnalysisReport,
  scanFileTask,
  searchIndexedFiles,
  sendGmailMessageWithAttachments,
} from "../services/api";
import { clearRecentTaskHistoryStorage, loadRecentTaskHistory, saveRecentTaskHistory } from "../services/taskHistoryStorage";
import {
  executeBrowserFilePlan,
  undoBrowserFilePlan,
  type BrowserExecutionProgress,
  type BrowserExecutionResult,
  type BrowserUndoResult,
} from "../services/browserFileExecutor";
import { chooseBrowserFolder, isBrowserFolderPickerSupported, type BrowserPickedFolder } from "../services/browserFolderPicker";
import { scanBrowserFolder, type BrowserFolderScanResult } from "../services/browserFolderScanner";
import { getReadableFilesFromScan, readDocumentsForSummary, type BrowserDocumentReadResult } from "../services/browserDocumentReader";
import { writeSummaryFile } from "../services/browserDocumentWriter";
import { prepareBrowserDocumentSummary } from "../services/documentSummaryPlanner";
import {
  candidatesFromManualFiles,
  detectAttachmentIntent,
  findAttachmentCandidates,
  hydrateAttachmentCandidateFiles,
  isIndexedAttachmentCandidate,
  selectedAttachmentCandidates,
  selectedAttachmentFiles,
  selectedIndexedAttachments,
  validateAttachments,
  type AttachmentCandidate,
} from "../services/attachmentFinderService";
import {
  buildExactIntentFallbackPlan,
  classifyFileTaskIntent,
  createLlmAssistedBrowserFilePlan,
  shouldUseLlmFilePlanning,
  validateBrowserFilePlan,
  type FileTaskIntent,
} from "../services/fileTaskLlmPlanner";
import type {
  ActionCapabilityRegistry,
  DocumentSummaryPrepareResponse,
  DocumentSummaryStyle,
  FileOperation,
  FileSnapshotItem,
  FileSnapshotResponse,
  FileTaskPlan,
  GmailDraftResponse,
  GmailStatusResponse,
  IndexedFileSearchMatch,
  LogAnalysisPrepareResponse,
  ModelConfig,
  NormalizedEmailMessage,
  TaskIntentPrepareResponse,
  TaskActionExecuteResponse,
} from "../types";

type TaskUiState = "resting" | "typing" | "context" | "document_options" | "plan" | "action_preview";
type TaskActionType =
  | "multi_step"
  | "file.organize"
  | "file.search"
  | "document.summary"
  | "document.summaryFromSearch"
  | "document.reportFromSearch"
  | "log.analyzeFromSearch"
  | "gmail.createDraft"
  | "gmail.sendEmail"
  | "gmail.sendGeneratedReport"
  | "gmail.replyDraft"
  | "gmail.searchEmails"
  | "gmail.summarizeEmails"
  | "memory.report"
  | "github.lookup"
  | "unsupported";

type ClassifiedTaskAction = {
  actionType: TaskActionType;
  label: string;
  supported: boolean;
  reason?: string;
};

type PreparedAction = ClassifiedTaskAction & {
  id: string;
  title: string;
  summary: string;
  riskLevel: "low" | "medium" | "high";
  requiresConfirmation: boolean;
  executionActionType?: TaskActionType;
  canExecute: boolean;
  blockedReasons: string[];
  missingRequirements: string[];
  sources: Array<{ type: string; status: "available" | "missing" | "connected" | "disconnected" }>;
  preview?: {
    to?: string;
    cc?: string;
    bcc?: string;
    subject?: string;
    body?: string;
    messageId?: string;
    note?: string;
    warning?: string;
    sourceSummary?: string;
    attachmentIntent?: boolean;
    attachmentQuery?: string;
    attachmentSearchStatus?: string;
  };
};

type CategorySummary = {
  label: string;
  count: number;
};

type ScanSource = "backend_path" | "browser_handle";
type ExecutionPhase = "idle" | "confirming" | "running" | "completed" | "undoing" | "undone";
type ActionApprovalPhase = "idle" | "confirming" | "running" | "completed";

type RecentTaskItem = {
  id: string;
  type: "file_organize" | "document_summary" | "log_analysis_report" | "gmail_draft" | "gmail_sent";
  title: string;
  summary: string;
  status: "completed" | "partial" | "failed";
  folderName?: string;
  contextName?: string;
  outputFileName?: string;
  createdAt: string;
  details: Record<string, number | string | boolean | null>;
};

type DocumentSummarySelection = {
  instruction: string;
  scan: BrowserFolderScanResult;
  candidates: FileSnapshotItem[];
  selectedPaths: string[];
  skipped: Array<{ relative_path: string; reason: string }>;
  warnings: string[];
};

type FileSearchSelection = {
  query: string;
  matches: IndexedFileSearchMatch[];
  selectedKeys: string[];
  emailRecipient: string;
  style: DocumentSummaryStyle;
  statusMessage: string;
};

type CloudSummaryWarning = {
  provider: string;
  displayName: string;
} | null;

const commandSuggestions = ["Organize Downloads", "Move PDFs", "Create project folders", "Rename screenshots"];

const folderSuggestions = [
  { label: "Downloads", path: "D:\\Downloads" },
  { label: "Documents", path: "D:\\Documents" },
  { label: "Desktop", path: "D:\\Desktop" },
  { label: "Projects", path: "D:\\Projects" },
];

const extensionCategories: Array<{ label: string; extensions: string[] }> = [
  { label: "PDFs", extensions: [".pdf"] },
  { label: "Images", extensions: [".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".bmp"] },
  { label: "Videos", extensions: [".mp4", ".mov", ".avi", ".mkv", ".webm"] },
  { label: "Audio", extensions: [".mp3", ".wav", ".m4a", ".flac", ".aac"] },
  { label: "Archives", extensions: [".zip", ".rar", ".7z", ".tar", ".gz"] },
  { label: "Installers", extensions: [".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm"] },
  { label: "Code", extensions: [".py", ".java", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".json", ".xml", ".yml", ".yaml"] },
  { label: "Documents", extensions: [".doc", ".docx", ".txt", ".md", ".rtf"] },
  { label: "Spreadsheets", extensions: [".xls", ".xlsx", ".csv"] },
  { label: "Presentations", extensions: [".ppt", ".pptx"] },
];

export function TasksPage() {
  const [uiState, setUiState] = useState<TaskUiState>("resting");
  const [command, setCommand] = useState("");
  const [rootPath, setRootPath] = useState("");
  const [scanResult, setScanResult] = useState<FileSnapshotResponse | null>(null);
  const [filePlan, setFilePlan] = useState<FileTaskPlan | null>(null);
  const [documentSelection, setDocumentSelection] = useState<DocumentSummarySelection | null>(null);
  const [documentSummary, setDocumentSummary] = useState<DocumentSummaryPrepareResponse | null>(null);
  const [documentSummarySource, setDocumentSummarySource] = useState<"browser_folder" | "indexed_search">("browser_folder");
  const [documentReadResult, setDocumentReadResult] = useState<BrowserDocumentReadResult | null>(null);
  const [fileSearchSelection, setFileSearchSelection] = useState<FileSearchSelection | null>(null);
  const [logAnalysisReport, setLogAnalysisReport] = useState<LogAnalysisPrepareResponse | null>(null);
  const [logReportOutputFilename, setLogReportOutputFilename] = useState("log-error-analysis-report.md");
  const [taskIntentPlan, setTaskIntentPlan] = useState<TaskIntentPrepareResponse | null>(null);
  const [preparedAction, setPreparedAction] = useState<PreparedAction | null>(null);
  const [actionCapabilities, setActionCapabilities] = useState<ActionCapabilityRegistry | null>(null);
  const [actionApprovalPhase, setActionApprovalPhase] = useState<ActionApprovalPhase>("idle");
  const [actionExecutionResult, setActionExecutionResult] = useState<TaskActionExecuteResponse | null>(null);
  const [gmailStatus, setGmailStatus] = useState<GmailStatusResponse | null>(null);
  const [gmailDraft, setGmailDraft] = useState({ to: "", cc: "", bcc: "", subject: "", body: "", message_id: "" });
  const [gmailDraftResult, setGmailDraftResult] = useState<GmailDraftResponse | null>(null);
  const [gmailDraftLoading, setGmailDraftLoading] = useState(false);
  const [gmailDraftMessage, setGmailDraftMessage] = useState<string | null>(null);
  const [gmailAttachmentCandidates, setGmailAttachmentCandidates] = useState<AttachmentCandidate[]>([]);
  const [emailSearchMessages, setEmailSearchMessages] = useState<NormalizedEmailMessage[]>([]);
  const [summaryOutputFilename, setSummaryOutputFilename] = useState("mindos-summary.md");
  const [summaryFilenameWasEdited, setSummaryFilenameWasEdited] = useState(false);
  const [summaryOutputFormat, setSummaryOutputFormat] = useState<"markdown" | "text">("markdown");
  const [summaryStyle, setSummaryStyle] = useState<DocumentSummaryStyle>("detailed");
  const [cloudSummaryWarning, setCloudSummaryWarning] = useState<CloudSummaryWarning>(null);
  const [scanSource, setScanSource] = useState<ScanSource>("backend_path");
  const [browserFolder, setBrowserFolder] = useState<BrowserPickedFolder | null>(null);
  const [scanLoading, setScanLoading] = useState(false);
  const [prepareLoading, setPrepareLoading] = useState(false);
  const [prepareStatus, setPrepareStatus] = useState<string | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);
  const [prepareError, setPrepareError] = useState<string | null>(null);
  const [pathIsStale, setPathIsStale] = useState(false);
  const [folderPickerMessage, setFolderPickerMessage] = useState<string | null>(null);
  const [isChoosingFolder, setIsChoosingFolder] = useState(false);
  const [executionPhase, setExecutionPhase] = useState<ExecutionPhase>("idle");
  const [executionMessage, setExecutionMessage] = useState<string | null>(null);
  const [executionProgress, setExecutionProgress] = useState<BrowserExecutionProgress | null>(null);
  const [executionResult, setExecutionResult] = useState<BrowserExecutionResult | null>(null);
  const [undoResult, setUndoResult] = useState<BrowserUndoResult | null>(null);
  const [summarySaveLoading, setSummarySaveLoading] = useState(false);
  const [summarySaveMessage, setSummarySaveMessage] = useState<string | null>(null);
  const [recentTasks, setRecentTasks] = useState<RecentTaskItem[]>(() => loadRecentTasks());
  const [clearTaskHistoryLoading, setClearTaskHistoryLoading] = useState(false);
  const [clearTaskHistoryMessage, setClearTaskHistoryMessage] = useState<string | null>(null);
  const [showClearTaskHistoryConfirm, setShowClearTaskHistoryConfirm] = useState(false);
  const pathInputRef = useRef<HTMLInputElement>(null);

  const visiblePath = browserFolder?.name || rootPath || inferredPathFromCommand(command) || "D:\\Downloads";
  const detectedIntent = useMemo(() => classifyFileTaskIntent(command.trim()), [command]);
  const detectedAction = useMemo(() => classifyTaskAction(command.trim()), [command]);
  const activeAction = preparedAction?.actionType ?? detectedAction.actionType;
  const isFolderAction = activeAction === "file.organize" || activeAction === "document.summary";
  const hasMeaningfulCommand = command.trim().split(/\s+/).filter(Boolean).length >= 2;
  const showIntentHint = isFolderAction && (uiState === "typing" || (uiState === "context" && command.trim().length > 0)) && !hasMeaningfulCommand;
  const showDetectedIntent = (uiState === "typing" || uiState === "context" || uiState === "action_preview") && hasMeaningfulCommand;
  const showContext = isFolderAction && (uiState === "context" || uiState === "document_options" || uiState === "plan");
  const commandValue = command.trim();
  const categories = useMemo(() => buildCategorySummary(scanResult?.files ?? []), [scanResult]);

  useEffect(() => {
    saveRecentTaskHistory(recentTasks);
  }, [recentTasks]);

  function addRecentTask(item: Omit<RecentTaskItem, "id" | "createdAt">) {
    setClearTaskHistoryMessage(null);
    setRecentTasks((current) => [
      {
        ...item,
        id: `task-${Date.now()}-${Math.random().toString(16).slice(2)}`,
        createdAt: new Date().toISOString(),
      },
      ...current,
    ].slice(0, 20));
  }

  async function handleClearTaskHistory() {
    setClearTaskHistoryLoading(true);
    setClearTaskHistoryMessage(null);
    try {
      await clearTaskHistory();
      clearRecentTaskHistoryStorage();
      setRecentTasks([]);
      setShowClearTaskHistoryConfirm(false);
      setClearTaskHistoryMessage("No recent tasks yet.");
    } catch (error) {
      setClearTaskHistoryMessage(getErrorMessage(error));
    } finally {
      setClearTaskHistoryLoading(false);
    }
  }

  function resetPlan() {
    setFilePlan(null);
    setDocumentSelection(null);
    setDocumentSummary(null);
    setDocumentSummarySource("browser_folder");
    setDocumentReadResult(null);
    setFileSearchSelection(null);
    setLogAnalysisReport(null);
    setLogReportOutputFilename("log-error-analysis-report.md");
    setTaskIntentPlan(null);
    setPreparedAction(null);
    setActionApprovalPhase("idle");
    setActionExecutionResult(null);
    setGmailDraftResult(null);
    setGmailDraftMessage(null);
    setGmailAttachmentCandidates([]);
    setEmailSearchMessages([]);
    setCloudSummaryWarning(null);
    setSummarySaveMessage(null);
    setPrepareError(null);
    setPrepareStatus(null);
    resetExecution();
  }

  function resetExecution() {
    setExecutionPhase("idle");
    setExecutionMessage(null);
    setExecutionProgress(null);
    setExecutionResult(null);
    setUndoResult(null);
    setSummarySaveLoading(false);
  }

  function handleCommandChange(value: string) {
    setCommand(value);
    setScanError(null);
    setFolderPickerMessage(null);
    resetPlan();
    if (value.trim()) {
      setUiState("typing");
      return;
    }
    setUiState(scanResult || rootPath ? "typing" : "resting");
  }

  function handleCommandKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key !== "Enter") return;
    event.preventDefault();
    const pathFromCommand = extractPathLikeCommand(command);
    if (pathFromCommand) {
      setBrowserFolder(null);
      setScanSource("backend_path");
      setRootPath(pathFromCommand);
      setFolderPickerMessage(null);
      void handleScan(pathFromCommand);
      return;
    }
    void continueFromCommand();
  }

  async function continueFromCommand() {
    const action = classifyTaskAction(command.trim());
    if (!isFolderTaskAction(action.actionType)) {
      await prepareGeneralAction(action);
      return;
    }
    const nextPath = rootPath || inferredPathFromCommand(command);
    if (nextPath) {
      setBrowserFolder(null);
      setScanSource("backend_path");
      setRootPath(nextPath);
    }
    setUiState("context");
  }

  function handleSuggestionClick(suggestion: string) {
    const nextCommand = suggestion.toLowerCase();
    const action = classifyTaskAction(nextCommand);
    setCommand(nextCommand);
    setScanError(null);
    setFolderPickerMessage(null);
    resetPlan();
    if (suggestion === "Organize Downloads" && !rootPath) {
      setRootPath("D:\\Downloads");
      setBrowserFolder(null);
      setScanSource("backend_path");
    }
    setUiState(isFolderTaskAction(action.actionType) ? "context" : "typing");
  }

  function handleFolderSelect(path: string) {
    setRootPath(path);
    setBrowserFolder(null);
    setScanSource("backend_path");
    setScanResult(null);
    setPathIsStale(false);
    setScanError(null);
    setFolderPickerMessage(null);
    resetPlan();
    setUiState("context");
  }

  async function handleChooseFolder() {
    setFolderPickerMessage(null);
    setScanError(null);
    setPrepareError(null);

    if (!isBrowserFolderPickerSupported()) {
      setFolderPickerMessage("Your browser does not support folder picking. Paste the folder path manually.");
      pathInputRef.current?.focus();
      setUiState("context");
      return;
    }

    setIsChoosingFolder(true);
    try {
      const selectedFolder = await chooseBrowserFolder();
      if (!selectedFolder) return;
      setBrowserFolder(selectedFolder);
      setScanSource("browser_handle");
      setRootPath("");
      setScanResult(null);
      setPathIsStale(false);
      resetPlan();
      setUiState("context");
      await handleBrowserScan(selectedFolder);
    } catch (error) {
      setFolderPickerMessage(getErrorMessage(error));
      pathInputRef.current?.focus();
    } finally {
      setIsChoosingFolder(false);
    }
  }

  async function handleBrowserScan(folder = browserFolder, options: { clearPlan?: boolean } = {}): Promise<BrowserFolderScanResult | null> {
    const clearPlan = options.clearPlan ?? true;
    if (!folder) {
      setScanError("Choose a folder before scanning.");
      setUiState("context");
      return null;
    }
    setScanLoading(true);
    setScanSource("browser_handle");
    setScanResult(null);
    setPathIsStale(false);
    setScanError(null);
    setFolderPickerMessage(null);
    if (clearPlan) {
      resetPlan();
    } else {
      setPrepareError(null);
    }
    setUiState("context");
    try {
      const result = await scanBrowserFolder(folder.handle, { maxDepth: 2, maxFiles: 500, includeHidden: false });
      setScanResult(result);
      return result;
    } catch (error) {
      setScanError(getErrorMessage(error));
      return null;
    } finally {
      setScanLoading(false);
    }
  }

  async function handleScan(path = visiblePath): Promise<FileSnapshotResponse | null> {
    if (scanSource === "browser_handle" && browserFolder) {
      return handleBrowserScan(browserFolder);
    }
    const scanPath = path.trim();
    if (!scanPath) {
      setScanError("Enter a folder path to scan.");
      setUiState("context");
      return null;
    }
    setRootPath(scanPath);
    setBrowserFolder(null);
    setScanSource("backend_path");
    setScanResult(null);
    setPathIsStale(false);
    setScanError(null);
    setFolderPickerMessage(null);
    resetPlan();
    setScanLoading(true);
    setUiState("context");
    try {
      const result = await scanFileTask({ root_path: scanPath, max_depth: 2, max_files: 500, include_hidden: false });
      setScanResult(result);
      setRootPath(result.root_path ?? scanPath);
      setPathIsStale(false);
      return result;
    } catch (error) {
      setScanError(toTaskErrorMessage(error));
      return null;
    } finally {
      setScanLoading(false);
    }
  }

  async function handlePrepare() {
    if (scanSource === "browser_handle") {
      await handlePrepareBrowserPlan();
      return;
    }

    const preparePath = (pathIsStale ? visiblePath : scanResult?.root_path || visiblePath).trim();
    if (detectedIntent.intent === "document_summary") {
      setPrepareError("For this POC, choose the folder with the Choose button so MindOS can read and save files safely.");
      return;
    }
    if (!preparePath) {
      setPrepareError("Enter a folder path before preparing a plan.");
      return;
    }
    setPrepareError(null);
    setPrepareLoading(true);
    try {
      if (!scanResult || pathIsStale) {
        const scan = await handleScan(preparePath);
        if (!scan) {
          setPrepareError("Scan the folder successfully before preparing a plan.");
          return;
        }
      }
      const plan = await prepareFileTaskPlan({
        root_path: preparePath,
        instruction: command.trim() || "Organize this folder by file type",
        max_depth: 2,
        max_files: 500,
        include_hidden: false,
        mode: "organize",
        dry_run: true,
      });
      setFilePlan(plan);
      setRootPath(plan.root_path);
      setUiState("plan");
    } catch (error) {
      setPrepareError(toTaskErrorMessage(error));
    } finally {
      setPrepareLoading(false);
    }
  }

  async function collectGmailAttachmentCandidates(attachmentIntent: ReturnType<typeof detectAttachmentIntent>, history: RecentTaskItem[]) {
    if (!attachmentIntent.attachment_intent) return { candidates: [], status: "" };
    const localCandidates = findAttachmentCandidates({
      query: attachmentIntent.file_query,
      extensionPreference: attachmentIntent.extension_preference,
      latestPreference: attachmentIntent.latest_preference,
      recentTaskOutputs: history,
      selectedFolderScan: scanSource === "browser_handle" && scanResult && !pathIsStale ? (scanResult as BrowserFolderScanResult) : null,
      memoryFileEvents: [],
    });
    const hydrated = await hydrateAttachmentCandidateFiles(localCandidates, browserFolder);
    let indexedCandidates: AttachmentCandidate[] = [];
    let status = "";
    try {
      const tracked = await getTrackedFolders();
      const indexedFolders = tracked.folders.filter((folder) => folder.enabled && folder.indexing_enabled && (folder.inventory_count || folder.indexed_count) > 0);
      const indexingPending = tracked.folders.some((folder) => folder.enabled && folder.indexing_enabled && ["queued", "indexing"].includes(folder.index_status));
      if (indexingPending) {
        status = "Connected folders are still being indexed. File results may be incomplete.";
      } else if (!indexedFolders.length) {
        status = "No connected File System folders are indexed yet. Choose files manually or connect a folder.";
      }
      if (indexedFolders.length) {
        const response = await searchIndexedFiles({
          query: attachmentIntent.file_query,
          search_filename: true,
          search_content: true,
          extensions: attachmentIntent.extension_preference.length ? attachmentIntent.extension_preference : [".pdf", ".docx", ".doc", ".txt", ".md"],
          connected_sources_only: true,
          attachable_only: true,
          limit: 20,
        });
        const resolved = await resolveIndexedAttachments(
          response.matches.map((match) => ({ source_id: match.source_id, relative_path: match.relative_path })),
        );
        const resolvedByKey = new Map(resolved.attachments.map((item) => [`${item.source_id}:${item.relative_path}`, item]));
        indexedCandidates = response.matches.map((match) => {
          const resolvedMatch = resolvedByKey.get(`${match.source_id}:${match.relative_path}`);
          return {
            id: `file_index:${match.source_id}:${match.relative_path}`,
            name: match.file_name,
            source_id: match.source_id,
            relative_path: match.relative_path,
            size_bytes: resolvedMatch?.size_bytes ?? match.size_bytes,
            extension: (resolvedMatch?.extension || match.extension || "").toLowerCase(),
            source: "file_index",
            modified_at: match.modified_at ?? undefined,
            score: 20 + match.score * 20,
            reason: `${readableMatchReason(match.match_reason)} ${match.content_index_status === "failed" ? "Content extraction failed, but filename metadata matched." : "Connected folder file."}`,
            selected: false,
            unavailableReason: resolvedMatch && !resolvedMatch.attachable ? resolvedMatch.reason || "File cannot be attached." : undefined,
          } satisfies AttachmentCandidate;
        });
      }
    } catch (error) {
      status = getErrorMessage(error);
    }
    const combined = rankAttachmentCandidates([...indexedCandidates, ...hydrated], attachmentIntent.latest_preference);
    return { candidates: combined, status };
  }

  async function prepareGeneralAction(action = classifyTaskAction(command.trim())) {
    setPrepareError(null);
    setPrepareStatus(null);
    setFilePlan(null);
    setDocumentSelection(null);
    setDocumentSummary(null);
    setGmailDraftResult(null);
    setGmailDraftMessage(null);
    setFileSearchSelection(null);
    setLogAnalysisReport(null);
    setTaskIntentPlan(null);
    if (shouldTryHybridPlanner(command.trim())) {
      try {
        const selectedModel = await getSelectedChatModel();
        const plan = await prepareTaskIntent({
          instruction: command.trim(),
          model_id: selectedModel?.id ?? null,
          use_llm_planner: true,
        });
        if (isLogAnalysisPlan(plan)) {
          await prepareLogSearchFromTaskPlan(plan);
          return;
        }
        if (isDocumentSearchSummaryPlan(plan)) {
          await prepareDocumentSearchFromTaskPlan(plan);
          return;
        }
        if (isFileSearchThenGmailPlan(plan)) {
          await prepareFileSearchFromTaskPlan(plan);
          return;
        }
        if (plan.primary_action === "file.organize") {
          action = { actionType: "file.organize", label: "Organize folder", supported: true };
        } else if (plan.primary_action === "unsupported") {
          setPreparedAction(actionFromUnsupportedPlan(plan));
          setUiState("action_preview");
          return;
        }
      } catch (error) {
        // Keep the existing deterministic UI paths if the planner endpoint/model is unavailable.
        setPrepareStatus(null);
      }
    }
    if (action.actionType === "multi_step") {
      await prepareFileSearchFromTaskPlan(frontendMultiStepFallbackPlan(command.trim()));
      return;
    }
    if (action.actionType === "log.analyzeFromSearch") {
      await prepareLogSearchFromTaskPlan(frontendLogAnalysisFallbackPlan(command.trim()));
      return;
    }
    if (isIndexedFileSearchAction(action.actionType)) {
      setPrepareLoading(true);
      try {
        const query = extractFileSearchQuery(command.trim());
        const tracked = await getTrackedFolders();
        const indexedFolders = tracked.folders.filter((folder) => folder.enabled && folder.indexing_enabled && (folder.inventory_count || folder.indexed_count) > 0);
        if (!indexedFolders.length) {
          setFileSearchSelection({
            query,
            matches: [],
            selectedKeys: [],
            emailRecipient: extractEmailAddress(command) || "",
            style: action.actionType === "document.reportFromSearch" ? "report" : "detailed",
            statusMessage: "No connected File System folders are indexed yet.",
          });
        } else {
          const response = await searchIndexedFiles({
            query,
            search_filename: true,
            search_content: true,
            connected_sources_only: true,
            attachable_only: false,
            readable_only: false,
            limit: 20,
          });
          const readableMatches = response.matches.filter((match) => Boolean(match.readable));
          const selected =
            readableMatches.length === 1 && readableMatches[0].score >= 0.6
              ? [`${readableMatches[0].source_id}:${readableMatches[0].relative_path}`]
              : [];
          setFileSearchSelection({
            query,
            matches: response.matches,
            selectedKeys: selected,
            emailRecipient: extractEmailAddress(command) || "",
            style: action.actionType === "document.reportFromSearch" ? "report" : "detailed",
            statusMessage: `Searched connected folders for "${query}".`,
          });
        }
        setPreparedAction({
          id: `action-${Date.now()}-${Math.random().toString(16).slice(2)}`,
          ...action,
          title: action.label,
          summary: `Searched connected folders for "${query}".`,
          riskLevel: action.actionType === "gmail.sendGeneratedReport" ? "high" : "low",
          requiresConfirmation: action.actionType !== "file.search",
          canExecute: false,
          blockedReasons: [],
          missingRequirements: [],
          sources: [{ type: "file_search", status: "available" }],
          preview: {
            note: `Searched connected folders for "${query}".`,
          },
        });
        setUiState("action_preview");
      } catch (error) {
        setPrepareError(getErrorMessage(error));
      } finally {
        setPrepareLoading(false);
      }
      return;
    }
    if (isEmailWriteAction(action.actionType)) {
      setPrepareLoading(true);
      let status: GmailStatusResponse | null = null;
      try {
        const capabilities = await getTaskActionCapabilities();
        setActionCapabilities(capabilities);
        const capabilityKey = capabilityKeyForAction(action.actionType);
        const actionCapability = capabilities.capabilities[capabilityKey];
        status = await getGmailStatus();
        setGmailStatus(status);
        const draftCapability = capabilities.capabilities["gmail.createDraft"];
        const sendCapability = capabilities.capabilities["gmail.sendEmail"];
        const wantsSend = action.actionType === "gmail.sendEmail";
        const sendAvailable = Boolean(sendCapability?.available);
        const draftAvailable = Boolean(draftCapability?.available);
        const executionActionType: TaskActionType = wantsSend && !sendAvailable && draftAvailable ? "gmail.createDraft" : action.actionType;
        const canExecute = wantsSend ? sendAvailable || draftAvailable : Boolean(actionCapability?.available);
        const blockedReasons = canExecute ? [] : [actionCapability?.reason || "Email action is not available."];
        const missingRequirements = canExecute ? [] : [capabilityKey];
        const fallbackMessage =
          wantsSend && !sendAvailable && draftAvailable
            ? "Gmail send is not connected yet. You can create a draft instead."
            : "";
        const history = recentTasksFromLastDays(recentTasks, 7);
        const attachmentIntent = detectAttachmentIntent(command.trim());
        const { candidates: attachmentCandidates, status: attachmentSearchStatus } = await collectGmailAttachmentCandidates(attachmentIntent, history);
        setGmailAttachmentCandidates(attachmentCandidates);
        const selectedModel = await getSelectedChatModel();
        const planned = await prepareGmailDraft({
          instruction: command.trim(),
          connected_email: status.email_address ?? null,
          recent_tasks: history.map(toGmailDraftSourceItem),
          attachment_filenames: selectedAttachmentCandidates(attachmentCandidates).map((candidate) => candidate.name),
          model_id: selectedModel?.id ?? null,
        });
        const recipient = extractEmailAddress(command) || planned.to || "";
        const draft = {
          to: recipient,
          cc: "",
          bcc: "",
          subject: planned.subject,
          body: planned.body,
          message_id: "",
        };
        setGmailDraft(draft);
        setPreparedAction({
          id: `action-${Date.now()}-${Math.random().toString(16).slice(2)}`,
          ...action,
          title: emailActionTitle(action.actionType),
          summary: emailActionSummary(action.actionType, draft.subject),
          supported: canExecute,
          riskLevel: executionActionType === "gmail.sendEmail" ? "high" : "medium",
          requiresConfirmation: true,
          executionActionType,
          canExecute,
          blockedReasons,
          missingRequirements,
          sources: [
            { type: "gmail", status: status.connected ? "connected" : "disconnected" },
            { type: "task_history", status: history.length ? "available" : "missing" },
            { type: "memory", status: "available" },
          ],
          preview: {
            ...draft,
            note: history.length ? "Based on task history from the last 7 days." : "I can draft the email, but I did not find task history from the last 7 days.",
            warning: [fallbackMessage, planned.planner_warning, ...planned.warnings].filter(Boolean).join(" "),
            sourceSummary: planned.source_summary,
            attachmentIntent: attachmentIntent.attachment_intent,
            attachmentQuery: attachmentIntent.file_query,
            attachmentSearchStatus,
          },
        });
      } catch (error) {
        const history = recentTasksFromLastDays(recentTasks, 7);
        const attachmentIntent = detectAttachmentIntent(command.trim());
        const { candidates: attachmentCandidates, status: attachmentSearchStatus } = await collectGmailAttachmentCandidates(attachmentIntent, history);
        setGmailAttachmentCandidates(attachmentCandidates);
        const draft = buildGmailDraftPreview(command.trim(), history);
        const nextDraft = ensureAttachmentMention(
          { ...draft, to: extractEmailAddress(command) || draft.to, cc: "", bcc: "", message_id: "" },
          selectedAttachmentCandidates(attachmentCandidates).map((candidate) => candidate.name),
        );
        setGmailDraft(nextDraft);
        setPreparedAction({
          id: `action-${Date.now()}-${Math.random().toString(16).slice(2)}`,
          ...action,
          title: emailActionTitle(action.actionType),
          summary: emailActionSummary(action.actionType, nextDraft.subject),
          supported: true,
          riskLevel: action.actionType === "gmail.sendEmail" ? "high" : "medium",
          requiresConfirmation: true,
          executionActionType: action.actionType,
          canExecute: Boolean(status?.connected && action.actionType !== "gmail.sendEmail"),
          blockedReasons: status?.connected
            ? action.actionType === "gmail.sendEmail"
              ? ["Gmail send capability was not detected."]
              : []
            : ["Gmail is not connected. Open Connectors -> Gmail and connect it."],
          missingRequirements: status?.connected && action.actionType !== "gmail.sendEmail" ? [] : [capabilityKeyForAction(action.actionType)],
          sources: [
            { type: "gmail", status: status?.connected ? "connected" : "disconnected" },
            { type: "task_history", status: history.length ? "available" : "missing" },
          ],
          preview: {
            ...draft,
            note: history.length ? "Based on task history from the last 7 days." : "I can draft the email, but I did not find task history from the last 7 days.",
            warning: `AI drafting was unavailable, so MindOS used a safe basic draft. ${getErrorMessage(error)}`,
            sourceSummary: history.length ? `Used ${history.length} task history items from the last 7 days.` : "No recent task history was available.",
            attachmentIntent: attachmentIntent.attachment_intent,
            attachmentQuery: attachmentIntent.file_query,
            attachmentSearchStatus,
          },
        });
      } finally {
        setPrepareLoading(false);
        setUiState("action_preview");
      }
      return;
    }

    if (action.actionType === "gmail.searchEmails" || action.actionType === "gmail.summarizeEmails") {
      setPrepareLoading(true);
      try {
        const capabilities = await getTaskActionCapabilities();
        setActionCapabilities(capabilities);
        const capabilityKey = capabilityKeyForAction(action.actionType);
        const actionCapability = capabilities.capabilities[capabilityKey];
        const response = actionCapability?.available ? await getGmailRecentEmails(10) : { emails: [], total: 0 };
        const messages = response.emails.map((email) => ({
          id: email.id,
          thread_id: email.thread_id ?? null,
          subject: email.subject,
          from: email.from_address,
          to: [],
          cc: [],
          date: email.date ?? null,
          snippet: email.snippet,
          body_excerpt: email.snippet,
          labels: ["GMAIL"],
          folder: "Gmail",
          has_attachments: false,
          attachments: [],
          url: null,
        }));
        setEmailSearchMessages(messages);
        setPreparedAction({
          id: `action-${Date.now()}-${Math.random().toString(16).slice(2)}`,
          ...action,
          title: action.label,
          summary: action.actionType === "gmail.summarizeEmails" ? `Summarize ${response.total} recent Gmail emails.` : `Show ${response.total} recent Gmail emails.`,
          riskLevel: "low",
          requiresConfirmation: false,
          canExecute: false,
          blockedReasons: actionCapability?.available ? [] : [actionCapability?.reason || "Gmail is not connected. Open Connectors -> Gmail and connect it."],
          missingRequirements: actionCapability?.available ? [] : [capabilityKey],
          sources: [{ type: "gmail", status: actionCapability?.available ? "available" : "missing" }],
          preview: {
            note: action.actionType === "gmail.summarizeEmails" ? summarizeEmailMessages(messages) : "Recent Gmail messages are shown below. No messages are modified.",
          },
        });
      } catch (error) {
        setPreparedAction({
          id: `action-${Date.now()}-${Math.random().toString(16).slice(2)}`,
          ...action,
          title: action.label,
          summary: "Email lookup failed.",
          riskLevel: "low",
          requiresConfirmation: false,
          canExecute: false,
          blockedReasons: [getErrorMessage(error)],
          missingRequirements: [capabilityKeyForAction(action.actionType)],
          sources: [{ type: "gmail", status: "missing" }],
          preview: { note: getErrorMessage(error) },
        });
      } finally {
        setPrepareLoading(false);
        setUiState("action_preview");
      }
      return;
    }

    if (action.actionType === "memory.report" || action.actionType === "github.lookup") {
      setPreparedAction({
        id: `action-${Date.now()}-${Math.random().toString(16).slice(2)}`,
        ...action,
        title: action.label,
        summary: previewNoteFor(action.actionType),
        riskLevel: "low",
        requiresConfirmation: false,
        canExecute: false,
        blockedReasons: [],
        missingRequirements: [],
        sources: actionSourcesFor(action.actionType, recentTasks),
        preview: {
          note: previewNoteFor(action.actionType),
        },
      });
      setUiState("action_preview");
      return;
    }

    setPreparedAction({
      id: `action-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      ...action,
      title: action.label,
      summary: action.reason || "MindOS cannot safely prepare this task yet.",
      riskLevel: "low",
      requiresConfirmation: false,
      canExecute: false,
      blockedReasons: action.reason ? [action.reason] : [],
      missingRequirements: [],
      sources: [],
      reason: action.reason || "MindOS cannot safely prepare this task yet.",
    });
    setUiState("action_preview");
  }

  async function handlePrepareBrowserPlan() {
    setPrepareError(null);
    setPrepareLoading(true);
    setPrepareStatus("Creating safe plan...");
    try {
      const currentScan = scanResult && !pathIsStale ? (scanResult as BrowserFolderScanResult) : await handleBrowserScan();
      if (!currentScan) {
        setPrepareError("Scan the folder successfully before preparing a plan.");
        return;
      }
      const instruction = command.trim() || "Organize this folder by file type";
      const intent = classifyFileTaskIntent(instruction);
      if (intent.intent === "document_summary") {
        await handlePrepareDocumentSummary(currentScan, instruction);
        setUiState("document_options");
        return;
      }
      if (shouldUseLlmFilePlanning(instruction, intent)) {
        setPrepareStatus("Asking model to prepare a plan...");
        try {
          const llmPlan = await createLlmAssistedBrowserFilePlan(currentScan, instruction);
          setPrepareStatus("Validating plan...");
          setFilePlan(llmPlan);
        } catch (error) {
          setPrepareStatus("Using exact-intent fallback...");
          const fallback = buildExactIntentFallbackPlan(currentScan, instruction, `AI planner failed, so MindOS used a safe exact-intent fallback. ${getErrorMessage(error)}`);
          setFilePlan(validateBrowserFilePlan(fallback, currentScan));
        }
      } else {
        const deterministicPlan = buildExactIntentFallbackPlan(currentScan, instruction);
        setFilePlan(validateBrowserFilePlan(deterministicPlan, currentScan));
      }
      setUiState("plan");
    } catch (error) {
      setPrepareError(getErrorMessage(error));
    } finally {
      setPrepareLoading(false);
      setPrepareStatus(null);
    }
  }

  async function handleCreateGmailDraft() {
    if (!preparedAction || !isEmailWriteAction(preparedAction.actionType)) return;
    const effectiveActionType = preparedAction.executionActionType ?? preparedAction.actionType;
    if (!preparedAction.canExecute) {
      setGmailDraftMessage(preparedAction.blockedReasons[0] || "This email action is not available.");
      return;
    }
    if (!gmailDraft.to.trim()) {
      setGmailDraftMessage(effectiveActionType === "gmail.sendEmail" ? "Add a recipient before sending." : "Add a recipient before creating the draft.");
      return;
    }
    if (!gmailDraft.subject.trim()) {
      setGmailDraftMessage(effectiveActionType === "gmail.sendEmail" ? "Add a subject before sending." : "Add a subject before creating the draft.");
      return;
    }
    if (!gmailDraft.body.trim()) {
      setGmailDraftMessage(effectiveActionType === "gmail.sendEmail" ? "Add an email body before sending." : "Add an email body before creating the draft.");
      return;
    }
    if (effectiveActionType === "gmail.replyDraft" && !gmailDraft.message_id.trim()) {
      setGmailDraftMessage("Choose or enter the original message id before creating a reply draft.");
      return;
    }
    const attachmentValidation = validateAttachments(gmailAttachmentCandidates);
    if (!attachmentValidation.ok) {
      setGmailDraftMessage(attachmentValidation.warnings[0]);
      return;
    }
    setActionApprovalPhase("confirming");
    setGmailDraftMessage(null);
  }

  async function prepareFileSearchFromTaskPlan(plan: TaskIntentPrepareResponse) {
    setPrepareLoading(true);
    setTaskIntentPlan(plan);
    try {
      const query = fileSearchQueryFromPlan(plan);
      const emailStep = gmailStepFromPlan(plan);
      const tracked = await getTrackedFolders();
      const indexedFolders = tracked.folders.filter((folder) => folder.enabled && folder.indexing_enabled && (folder.inventory_count || folder.indexed_count) > 0);
      if (!indexedFolders.length) {
        setFileSearchSelection({
          query,
          matches: [],
          selectedKeys: [],
          emailRecipient: emailStep?.to[0] || plan.entities.recipients[0] || extractEmailAddress(command) || "",
          style: "detailed",
          statusMessage: "No connected File System folders are indexed yet.",
        });
      } else {
        const response = await searchIndexedFiles({
          query,
          search_filename: true,
          search_content: true,
          connected_sources_only: true,
          attachable_only: true,
          readable_only: false,
          limit: 20,
        });
        const attachableMatches = response.matches.filter((match) => Boolean(match.attachable));
        const selected =
          attachableMatches.length === 1 || (attachableMatches.length > 0 && attachableMatches[0].score >= 0.75)
            ? [`${attachableMatches[0].source_id}:${attachableMatches[0].relative_path}`]
            : [];
        setFileSearchSelection({
          query,
          matches: response.matches,
          selectedKeys: selected,
          emailRecipient: emailStep?.to[0] || plan.entities.recipients[0] || extractEmailAddress(command) || "",
          style: "detailed",
          statusMessage: `Searched connected folders for "${query}".`,
        });
      }
      const wantsSend = emailStep?.type === "gmail.send_email_after_confirmation";
      setPreparedAction({
        id: `action-${Date.now()}-${Math.random().toString(16).slice(2)}`,
        actionType: "multi_step",
        label: wantsSend ? "Find file + Gmail send" : "Find file + Gmail draft",
        supported: true,
        title: wantsSend ? "Find file and prepare Gmail send" : "Find file and create Gmail draft",
        summary: plan.explanation || `MindOS will search connected folders for "${query}", ask you to choose a file, then prepare Gmail.`,
        riskLevel: wantsSend ? "high" : "medium",
        requiresConfirmation: true,
        executionActionType: wantsSend ? "gmail.sendEmail" : "gmail.createDraft",
        canExecute: false,
        blockedReasons: [],
        missingRequirements: [],
        sources: [
          { type: "file_system", status: "available" },
          { type: "gmail", status: "available" },
        ],
        preview: {
          note: plan.explanation || "MindOS will search connected folders first, then prepare Gmail with your selected attachment.",
          sourceSummary: `Searched connected folders for ${query}.`,
          attachmentIntent: true,
          attachmentQuery: query,
          attachmentSearchStatus: plan.warnings.join(" "),
        },
      });
      setUiState("action_preview");
    } catch (error) {
      setPrepareError(getErrorMessage(error));
    } finally {
      setPrepareLoading(false);
    }
  }

  async function prepareDocumentSearchFromTaskPlan(plan: TaskIntentPrepareResponse) {
    setPrepareLoading(true);
    setTaskIntentPlan(plan);
    setPrepareStatus("Searching connected files...");
    try {
      const query = fileSearchQueryFromPlan(plan);
      const isReport = plan.primary_action === "document.reportFromSearch" || plan.steps.some((step) => step.type === "document.create_report_from_files");
      const tracked = await getTrackedFolders();
      const indexedFolders = tracked.folders.filter((folder) => folder.enabled && folder.indexing_enabled && (folder.inventory_count || folder.indexed_count) > 0);
      let matches: IndexedFileSearchMatch[] = [];
      let selectedKeys: string[] = [];
      let statusMessage = "No connected File System folders are indexed yet.";
      if (indexedFolders.length) {
        const response = await searchIndexedFiles({
          query,
          search_filename: true,
          search_content: true,
          connected_sources_only: true,
          attachable_only: false,
          readable_only: true,
          extensions: plan.entities.extensions,
          limit: 20,
        });
        matches = response.matches.filter(isLogLikeSearchMatch);
        const readableMatches = matches.filter((match) => Boolean(match.readable));
        selectedKeys =
          readableMatches.length === 1 && readableMatches[0].score >= 0.6
            ? [`${readableMatches[0].source_id}:${readableMatches[0].relative_path}`]
            : [];
        statusMessage = `Searched connected folders for files related to "${query}".`;
      }
      setFileSearchSelection({
        query,
        matches,
        selectedKeys,
        emailRecipient: "",
        style: isReport ? "report" : "detailed",
        statusMessage,
      });
      setPreparedAction({
        id: `action-${Date.now()}-${Math.random().toString(16).slice(2)}`,
        actionType: isReport ? "document.reportFromSearch" : "document.summaryFromSearch",
        label: isReport ? "Report from connected files" : "Summary from connected files",
        supported: true,
        title: isReport ? "Create report from connected files" : "Summarize connected files",
        summary: plan.user_facing_summary || plan.explanation || `Search connected folders for "${query}", then summarize selected files.`,
        riskLevel: "low",
        requiresConfirmation: true,
        canExecute: false,
        blockedReasons: [],
        missingRequirements: [],
        sources: [{ type: "file_search", status: "available" }],
        preview: {
          note: plan.user_facing_summary || plan.explanation || "MindOS will summarize only the files you select.",
          sourceSummary: `Searched connected folders for files related to "${query}".`,
          attachmentQuery: query,
          attachmentSearchStatus: [...plan.warnings, ...plan.validation_repairs].join(" "),
        },
      });
      setUiState("action_preview");
    } catch (error) {
      setPrepareError(getErrorMessage(error));
    } finally {
      setPrepareLoading(false);
      setPrepareStatus(null);
    }
  }

  async function prepareLogSearchFromTaskPlan(plan: TaskIntentPrepareResponse) {
    setPrepareLoading(true);
    setTaskIntentPlan(plan);
    setPrepareStatus("Searching connected log files...");
    try {
      const query = logSearchQueryFromPlan(plan);
      const extensions = logSearchExtensionsFromPlan(plan);
      const latestPreference = logLatestPreferenceFromPlan(plan);
      const exactHint = logExactFileHintFromPlan(plan);
      const tracked = await getTrackedFolders();
      const indexedFolders = tracked.folders.filter((folder) => folder.enabled && folder.indexing_enabled && (folder.inventory_count || folder.indexed_count) > 0);
      let matches: IndexedFileSearchMatch[] = [];
      let selectedKeys: string[] = [];
      let statusMessage = "No connected File System folders are indexed yet.";
      if (indexedFolders.length) {
        const response = await searchIndexedFiles({
          query,
          search_filename: true,
          search_content: true,
          connected_sources_only: true,
          attachable_only: false,
          readable_only: true,
          latest_preference: latestPreference,
          extensions,
          limit: 20,
        });
        matches = response.matches;
        const readableMatches = matches.filter((match) => Boolean(match.readable));
        if (exactHint) {
          const normalizedHint = exactHint.toLowerCase();
          selectedKeys = readableMatches
            .filter((match) => match.file_name.toLowerCase().includes(normalizedHint) || match.relative_path.toLowerCase().includes(normalizedHint))
            .map((match) => `${match.source_id}:${match.relative_path}`)
            .slice(0, 5);
        } else if (latestPreference) {
          selectedKeys = readableMatches.slice(0, 3).map((match) => `${match.source_id}:${match.relative_path}`);
        } else if (readableMatches.length === 1 || (readableMatches.length > 0 && readableMatches[0].score >= 0.75)) {
          selectedKeys = [`${readableMatches[0].source_id}:${readableMatches[0].relative_path}`];
        }
        statusMessage = matches.length
          ? `Searched connected folders for log files related to "${query}".`
          : "No log-like files found in connected folders. Choose files manually or connect a logs folder.";
      }
      setFileSearchSelection({
        query,
        matches,
        selectedKeys,
        emailRecipient: "",
        style: "report",
        statusMessage,
      });
      setPreparedAction({
        id: `action-${Date.now()}-${Math.random().toString(16).slice(2)}`,
        actionType: "log.analyzeFromSearch",
        label: "Analyze logs",
        supported: true,
        title: "Analyze connected logs",
        summary: plan.explanation || `Find relevant log files and create an error analysis report for "${query}".`,
        riskLevel: "medium",
        requiresConfirmation: true,
        canExecute: false,
        blockedReasons: [],
        missingRequirements: [],
        sources: [{ type: "file_search", status: "available" }],
        preview: {
          note: "MindOS will analyze only the selected connected log files and save a separate report.",
          sourceSummary: `Searched connected folders for "${query}".`,
          attachmentQuery: query,
          attachmentSearchStatus: plan.warnings.join(" "),
        },
      });
      setUiState("action_preview");
    } catch (error) {
      setPrepareError(getErrorMessage(error));
    } finally {
      setPrepareLoading(false);
      setPrepareStatus(null);
    }
  }

  async function handleContinueFromFileSearch() {
    if (!fileSearchSelection || !taskIntentPlan) {
      await handlePrepareIndexedFileSummary();
      return;
    }
    const emailStep = gmailStepFromPlan(taskIntentPlan);
    if (!emailStep) {
      await handlePrepareIndexedFileSummary();
      return;
    }
    const selectedMatches = fileSearchSelection.matches.filter((match) =>
      fileSearchSelection.selectedKeys.includes(`${match.source_id}:${match.relative_path}`),
    );
    if (!selectedMatches.length) {
      setPrepareError("Select at least one file before preparing Gmail.");
      return;
    }
    setPrepareError(null);
    setPrepareLoading(true);
    try {
      const resolved = await resolveIndexedAttachments(
        selectedMatches.map((match) => ({ source_id: match.source_id, relative_path: match.relative_path })),
      );
      const resolvedByKey = new Map(resolved.attachments.map((item) => [`${item.source_id}:${item.relative_path}`, item]));
      const candidates = selectedMatches.map((match) => {
        const resolvedMatch = resolvedByKey.get(`${match.source_id}:${match.relative_path}`);
        return {
          id: `file_index:${match.source_id}:${match.relative_path}`,
          name: match.file_name,
          source_id: match.source_id,
          relative_path: match.relative_path,
          size_bytes: resolvedMatch?.size_bytes ?? match.size_bytes,
          extension: (resolvedMatch?.extension || match.extension || "").toLowerCase(),
          source: "file_index",
          modified_at: match.modified_at ?? undefined,
          score: 100,
          reason: `${readableMatchReason(match.match_reason)} Connected folder file.`,
          selected: Boolean(resolvedMatch?.attachable ?? match.attachable),
          unavailableReason: resolvedMatch && !resolvedMatch.attachable ? resolvedMatch.reason || "File cannot be attached." : undefined,
        } satisfies AttachmentCandidate;
      });
      setGmailAttachmentCandidates(candidates);
      const capabilities = await getTaskActionCapabilities();
      const status = await getGmailStatus();
      setActionCapabilities(capabilities);
      setGmailStatus(status);
      const wantsSend = emailStep.type === "gmail.send_email_after_confirmation";
      const executionActionType: TaskActionType = wantsSend ? "gmail.sendEmail" : "gmail.createDraft";
      const sendAvailable = Boolean(capabilities.capabilities["gmail.sendEmail"]?.available || status.capabilities?.send_email);
      const draftAvailable = Boolean(capabilities.capabilities["gmail.createDraft"]?.available || (status.connected && status.capabilities?.create_draft));
      const canExecute = wantsSend ? sendAvailable : draftAvailable;
      const selectedNames = candidates.filter((candidate) => candidate.selected).map((candidate) => candidate.name);
      const selectedModel = await getSelectedChatModel();
      const planned = await prepareGmailDraft({
        instruction: command.trim(),
        connected_email: status.email_address ?? null,
        recent_tasks: [],
        attachment_filenames: selectedNames,
        model_id: selectedModel?.id ?? null,
      });
      const fallbackDraft = buildAttachmentEmailDraft(taskIntentPlan, selectedNames);
      const useFallbackBody = planned.warnings.some((warning) => warning.toLowerCase().includes("ai drafting was unavailable"));
      const draft = {
        to: fileSearchSelection.emailRecipient || emailStep.to[0] || planned.to || "",
        cc: "",
        bcc: "",
        subject: planned.subject && !useFallbackBody ? planned.subject : fallbackDraft.subject,
        body: planned.body && !useFallbackBody ? planned.body : fallbackDraft.body,
        message_id: "",
      };
      setGmailDraft(ensureAttachmentMention(draft, selectedNames));
      setPreparedAction({
        id: `action-${Date.now()}-${Math.random().toString(16).slice(2)}`,
        actionType: executionActionType,
        label: wantsSend ? "Send Gmail" : "Create Gmail draft",
        supported: canExecute,
        title: wantsSend ? "Gmail send preview" : "Gmail draft preview",
        summary: wantsSend ? "Send a Gmail email with selected attachment after confirmation." : "Create a Gmail draft with the selected attachment.",
        riskLevel: wantsSend ? "high" : "medium",
        requiresConfirmation: true,
        executionActionType,
        canExecute,
        blockedReasons: canExecute ? [] : [status.connected ? "Required Gmail capability is not available." : "Gmail is not connected. Open Connectors -> Gmail and connect it."],
        missingRequirements: canExecute ? [] : [wantsSend ? "gmail.sendEmail" : "gmail.createDraft"],
        sources: [
          { type: "file_search", status: "available" },
          { type: "gmail", status: status.connected ? "connected" : "disconnected" },
        ],
        preview: {
          ...draft,
          note: wantsSend ? "Review this email and selected attachment before sending." : "Review this draft and selected attachment before creating it in Gmail.",
          warning: planned.warnings.join(" "),
          sourceSummary: `Searched connected folders for ${fileSearchSelection.query}.`,
          attachmentIntent: true,
          attachmentQuery: fileSearchSelection.query,
        },
      });
      setUiState("action_preview");
    } catch (error) {
      setPrepareError(getErrorMessage(error));
    } finally {
      setPrepareLoading(false);
    }
  }

  function updateGmailAttachmentCandidates(nextCandidates: AttachmentCandidate[]) {
    setGmailAttachmentCandidates(nextCandidates);
    setGmailDraft((current) => ensureAttachmentMention(current, selectedAttachmentCandidates(nextCandidates).map((candidate) => candidate.name)));
    setGmailDraftMessage(null);
  }

  function handleManualGmailAttachmentFiles(files: FileList | null) {
    if (!files?.length) return;
    const manualCandidates = candidatesFromManualFiles(Array.from(files));
    setGmailAttachmentCandidates((current) => {
      const existingIds = new Set(current.map((candidate) => candidate.id));
      return [...current, ...manualCandidates.filter((candidate) => !existingIds.has(candidate.id))];
    });
    setGmailDraft((current) => ensureAttachmentMention(current, manualCandidates.map((candidate) => candidate.name)));
    setGmailDraftMessage(null);
  }

  async function handleConfirmActionExecution() {
    if (!preparedAction) return;
    setGmailDraftLoading(true);
    setActionApprovalPhase("running");
    setGmailDraftMessage(null);
    try {
      const executionActionType = preparedAction.executionActionType ?? preparedAction.actionType;
      const selectedAttachments = selectedAttachmentCandidates(gmailAttachmentCandidates);
      const selectedManualFiles = selectedAttachmentFiles(gmailAttachmentCandidates);
      const selectedIndexedRefs = selectedIndexedAttachments(gmailAttachmentCandidates);
      const attachmentValidation = validateAttachments(gmailAttachmentCandidates);
      if (!attachmentValidation.ok) {
        setGmailDraftMessage(attachmentValidation.warnings[0]);
        setActionApprovalPhase("idle");
        return;
      }
      let result: TaskActionExecuteResponse;
      let draftId = "";
      let messageId: string | null = null;
      if (selectedAttachments.length && (executionActionType === "gmail.createDraft" || executionActionType === "gmail.sendEmail")) {
        const attachmentFiles = selectedManualFiles.map((candidate) => candidate.file as File);
        if (executionActionType === "gmail.sendEmail") {
          const sent = await sendGmailMessageWithAttachments({
            to: splitRecipients(gmailDraft.to),
            cc: splitRecipients(gmailDraft.cc),
            bcc: splitRecipients(gmailDraft.bcc),
            subject: gmailDraft.subject,
            body: gmailDraft.body,
            confirmation: true,
            attachments: attachmentFiles,
            indexed_attachments: selectedIndexedRefs,
          });
          messageId = sent.message_id ?? null;
          result = {
            ok: true,
            status: "completed",
            result: { provider: "gmail", message_id: messageId || "", sent: true },
            message: sent.message,
          };
          setGmailDraftResult({ status: sent.status, draft_id: "", message_id: sent.message_id ?? null, message: sent.message });
        } else {
          const draftResponse = await createGmailDraftWithAttachments({
            to: gmailDraft.to,
            cc: splitRecipients(gmailDraft.cc),
            bcc: splitRecipients(gmailDraft.bcc),
            subject: gmailDraft.subject,
            body: gmailDraft.body,
            attachments: attachmentFiles,
            indexed_attachments: selectedIndexedRefs,
          });
          draftId = draftResponse.draft_id;
          messageId = draftResponse.message_id ?? null;
          result = {
            ok: true,
            status: "completed",
            result: { provider: "gmail", draft_id: draftId, message_id: messageId || "", sent: false },
            message: draftResponse.message,
          };
          setGmailDraftResult(draftResponse);
        }
      } else {
        result = await executeTaskAction({
          action_id: preparedAction.id,
          action_type:
            executionActionType === "gmail.createDraft" || executionActionType === "gmail.sendEmail" || executionActionType === "gmail.replyDraft"
              ? executionActionType
              : "unsupported",
          preview: gmailDraft,
          confirmation: true,
        });
        draftId = String(result.result.draft_id || "");
        messageId = typeof result.result.message_id === "string" ? result.result.message_id : null;
        setGmailDraftResult({
          status: result.status,
          draft_id: draftId,
          message_id: messageId,
          message: result.message,
        });
      }
      setActionExecutionResult(result);
      setGmailDraftMessage(result.message || (executionActionType === "gmail.sendEmail" ? "Email sent." : "Draft created. Nothing was sent."));
      setActionApprovalPhase("completed");
      const attachmentNames = selectedAttachments.map((candidate) => candidate.name);
      addRecentTask({
        type: executionActionType === "gmail.sendEmail" ? "gmail_sent" : "gmail_draft",
        title: executionActionType === "gmail.sendEmail" ? "Sent Gmail email" : executionActionType === "gmail.replyDraft" ? "Created Gmail reply draft" : "Created Gmail draft",
        summary: `To ${gmailDraft.to} · ${gmailDraft.subject}${attachmentNames.length ? ` · ${attachmentNames.length} attachment${attachmentNames.length === 1 ? "" : "s"}` : ""}`,
        status: "completed",
        contextName: gmailStatus?.email_address || String(result.result.provider || "Gmail"),
        details: {
          draft_id: draftId,
          message_id: messageId || "",
          attachment_count: attachmentNames.length,
          attachment_names: attachmentNames.join(", "),
        },
      });
    } catch (error) {
      setGmailDraftMessage(getErrorMessage(error));
      setActionApprovalPhase("idle");
    } finally {
      setGmailDraftLoading(false);
    }
  }

  async function handlePrepareDocumentSummary(currentScan: BrowserFolderScanResult, instruction: string) {
    if (!browserFolder) {
      setPrepareError("For this POC, choose the folder with the Choose button so MindOS can read and save files safely.");
      return;
    }
    setFilePlan(null);
    setDocumentSummary(null);
    setDocumentReadResult(null);
    setCloudSummaryWarning(null);
    const readable = getReadableFilesFromScan(currentScan, instruction);
    const warnings = readable.warning ? [`${readable.warning} I can currently summarize txt, md, log, json, csv, PDF, and DOCX files.`] : [];
    setDocumentSelection({
      instruction,
      scan: currentScan,
      candidates: readable.candidates,
      selectedPaths: readable.candidates.slice(0, 20).map((file) => file.relative_path),
      skipped: readable.skipped,
      warnings,
    });
    if (!readable.candidates.length) {
      setDocumentSummary({
        task_id: `doc-summary-empty-${Date.now()}`,
        status: "empty",
        summary_title: "No readable documents found",
        summary_markdown: warnings.find((warning) => warning.includes("PDF reading")) ?? "I couldn't find readable documents in this folder.",
        files_used: [],
        files_skipped: readable.skipped,
        warnings,
        output_filename_suggestion: summaryOutputFilename,
        output_format: summaryOutputFormat,
        summary_style: summaryStyle,
      });
    }
  }

  async function handlePrepareSelectedDocumentSummary(cloudConfirmed = false) {
    if (!browserFolder || !documentSelection) return;
    const selectedFiles = documentSelection.candidates.filter((file) => documentSelection.selectedPaths.includes(file.relative_path));
    if (!selectedFiles.length) {
      setPrepareError("Select at least one readable file.");
      return;
    }
    setPrepareError(null);
    setPrepareLoading(true);
    setCloudSummaryWarning(null);
    try {
      const selectedModel = await getSelectedChatModel();
      if (selectedModel?.type === "cloud" && !cloudConfirmed) {
        setCloudSummaryWarning({ provider: selectedModel.provider, displayName: selectedModel.display_name });
        return;
      }
      setPrepareStatus("Reading selected files...");
      const readResult = await readDocumentsForSummary(browserFolder.handle, documentSelection.scan, {
        instruction: documentSelection.instruction,
        selectedFiles,
        onProgress: setPrepareStatus,
      });
      setDocumentReadResult(readResult);
      if (!readResult.files_read.length) {
        setDocumentSummary({
          task_id: `doc-summary-empty-${Date.now()}`,
          status: "empty",
          summary_title: "No readable documents found",
          summary_markdown: "I couldn't find readable documents in the selected files.",
          files_used: [],
          files_skipped: readResult.skipped,
          warnings: readResult.warnings,
          output_filename_suggestion: normalizedSummaryFilename(summaryOutputFilename, summaryOutputFormat),
          output_format: summaryOutputFormat,
          summary_style: summaryStyle,
        });
        return;
      }
      setPrepareStatus("Preparing summary with selected model...");
      const summary = await prepareBrowserDocumentSummary(documentSelection.instruction, documentSelection.scan.display_name || documentSelection.scan.root_name, readResult, {
        outputFormat: summaryOutputFormat,
        outputFilename: summaryFilenameWasEdited ? normalizedSummaryFilename(summaryOutputFilename, summaryOutputFormat) : undefined,
        summaryStyle,
      });
      setPrepareStatus("Finalizing preview...");
      setDocumentSummary(summary);
      if (!summaryFilenameWasEdited) {
        setSummaryOutputFilename(normalizedSummaryFilename(summary.output_filename_suggestion, summaryOutputFormat));
      }
      setUiState("plan");
    } catch (error) {
      setPrepareError(getErrorMessage(error));
    } finally {
      setPrepareLoading(false);
      setPrepareStatus(null);
    }
  }

  async function handlePrepareIndexedFileSummary() {
    if (!fileSearchSelection) return;
    const selectedMatches = fileSearchSelection.matches.filter((match) =>
      fileSearchSelection.selectedKeys.includes(`${match.source_id}:${match.relative_path}`),
    );
    if (!selectedMatches.length) {
      setPrepareError("Select at least one readable file.");
      return;
    }
    setPrepareError(null);
    setPrepareLoading(true);
    setPrepareStatus("Preparing summary from selected files...");
    try {
      const selectedModel = await getSelectedChatModel();
      const outputFilename = summaryFilenameWasEdited
        ? normalizedSummaryFilename(summaryOutputFilename, "markdown")
        : normalizedSummaryFilename(
            `${fileSearchSelection.query}-${fileSearchSelection.style === "report" ? "report" : "summary"}.md`,
            "markdown",
          );
      const summary = await prepareIndexedDocumentSummary({
        query: fileSearchSelection.query,
        style: fileSearchSelection.style,
        output_format: "markdown",
        output_filename: outputFilename,
        files: selectedMatches.map((match) => ({
          source_id: match.source_id,
          relative_path: match.relative_path,
        })),
        model_id: selectedModel?.id ?? null,
      });
      setDocumentSummarySource("indexed_search");
      setDocumentSummary(summary);
      setDocumentReadResult(null);
      if (!summaryFilenameWasEdited) {
        setSummaryOutputFilename(normalizedSummaryFilename(summary.output_filename_suggestion, "markdown"));
      }
      setUiState("plan");
    } catch (error) {
      setPrepareError(getErrorMessage(error));
    } finally {
      setPrepareLoading(false);
      setPrepareStatus(null);
    }
  }

  async function handlePrepareLogAnalysisReport() {
    if (!fileSearchSelection) return;
    const selectedMatches = fileSearchSelection.matches.filter((match) =>
      fileSearchSelection.selectedKeys.includes(`${match.source_id}:${match.relative_path}`),
    );
    if (!selectedMatches.length) {
      setPrepareError("Select at least one log file before analyzing.");
      return;
    }
    setPrepareError(null);
    setPrepareLoading(true);
    setPrepareStatus("Analyzing selected logs...");
    try {
      setDocumentSummary(null);
      setDocumentReadResult(null);
      const selectedModel = await getSelectedChatModel();
      const report = await prepareLogAnalysisReport({
        query: fileSearchSelection.query,
        output_format: "markdown",
        output_filename: logReportOutputFilename,
        files: selectedMatches.map((match) => ({
          source_id: match.source_id,
          relative_path: match.relative_path,
        })),
        model_id: selectedModel?.id ?? null,
      });
      setLogAnalysisReport(report);
      setLogReportOutputFilename(normalizedSummaryFilename(report.output_filename_suggestion || logReportOutputFilename, "markdown"));
      setUiState("plan");
    } catch (error) {
      setPrepareError(getErrorMessage(error));
    } finally {
      setPrepareLoading(false);
      setPrepareStatus(null);
    }
  }

  async function handleSaveLogAnalysisReport() {
    if (!logAnalysisReport || logAnalysisReport.status !== "preview") return;
    setSummarySaveLoading(true);
    setSummarySaveMessage(null);
    try {
      const finalOutputFilename = normalizedSummaryFilename(logReportOutputFilename || logAnalysisReport.output_filename_suggestion, "markdown");
      const saved = await saveLogAnalysisReport({
        task_id: logAnalysisReport.task_id,
        output_filename: finalOutputFilename,
        report_markdown: logAnalysisReport.report_markdown,
      });
      addRecentTask({
        type: "log_analysis_report",
        title: logAnalysisReport.report_title || "Created log analysis report",
        summary: `Analyzed ${logAnalysisReport.files_used.length} log file${logAnalysisReport.files_used.length === 1 ? "" : "s"} - saved ${saved.output_file.file_name}`,
        status: "completed",
        contextName: "MindOS outputs",
        outputFileName: saved.output_file.file_name,
        details: {
          files_used_count: logAnalysisReport.files_used.length,
          files_skipped_count: logAnalysisReport.files_skipped.length,
          warnings_count: logAnalysisReport.warnings.length,
          provider: logAnalysisReport.provider || "",
          model: logAnalysisReport.model_display_name || logAnalysisReport.model || "",
        },
      });
      setSummarySaveMessage(`Saved report: ${saved.output_file.file_name}. Original log files were not changed.`);
    } catch (error) {
      setSummarySaveMessage(getErrorMessage(error));
    } finally {
      setSummarySaveLoading(false);
    }
  }

  async function handleSaveSummary() {
    if (!browserFolder || !documentSummary || documentSummary.status !== "preview") return;
    setSummarySaveLoading(true);
    setSummarySaveMessage(null);
    try {
      const finalOutputFilename = normalizedSummaryFilename(summaryOutputFilename || documentSummary.output_filename_suggestion, documentSummary.output_format ?? summaryOutputFormat);
      const saved = await writeSummaryFile(browserFolder.handle, finalOutputFilename, documentSummary.summary_markdown);
      let message = `Saved summary: ${saved.filename}. Original files were not changed.`;
      const fileTypesUsed = uniqueFileTypes(documentReadResult);
      try {
        const completion = await completeDocumentSummary({
          task_id: documentSummary.task_id,
          folder_name: browserFolder.name,
          output_file_name: saved.filename,
          files_used_count: documentSummary.files_used.length,
          files_skipped_count: documentSummary.files_skipped.length,
          summary_style: documentSummary.summary_style ?? summaryStyle,
          output_format: documentSummary.output_format ?? summaryOutputFormat,
          file_types_used: fileTypesUsed,
          summary_title: documentSummary.summary_title,
          topic: documentSummary.topic,
          naming_confidence: documentSummary.naming_confidence ?? "low",
        });
        if (completion.warning) {
          message = `${message} ${completion.warning}`;
        }
      } catch (memoryError) {
        message = `${message} MindOS could not record the memory event: ${getErrorMessage(memoryError)}`;
      }
      addRecentTask({
        type: "document_summary",
        title: documentSummary.summary_title || "Created document summary",
        summary: `Used ${documentSummary.files_used.length} files · skipped ${documentSummary.files_skipped.length} · saved ${saved.filename}`,
        status: "completed",
        folderName: browserFolder.name,
        outputFileName: saved.filename,
        details: {
          files_used_count: documentSummary.files_used.length,
          files_skipped_count: documentSummary.files_skipped.length,
          output_format: documentSummary.output_format ?? summaryOutputFormat,
          summary_style: documentSummary.summary_style ?? summaryStyle,
          file_types_used: fileTypesUsed.join(", "),
          topic: documentSummary.topic || "",
          naming_confidence: documentSummary.naming_confidence ?? "low",
        },
      });
      setSummarySaveMessage(message);
    } catch (error) {
      setSummarySaveMessage(getErrorMessage(error));
    } finally {
      setSummarySaveLoading(false);
    }
  }

  async function handleSaveSummaryUnified() {
    if (!documentSummary || documentSummary.status !== "preview") return;
    if (documentSummarySource === "browser_folder") {
      await handleSaveSummary();
      return;
    }
    setSummarySaveLoading(true);
    setSummarySaveMessage(null);
    try {
      const finalOutputFilename = normalizedSummaryFilename(summaryOutputFilename || documentSummary.output_filename_suggestion, documentSummary.output_format ?? summaryOutputFormat);
      const response = await saveGeneratedSummaryOutput({
        task_id: documentSummary.task_id,
        output_filename: finalOutputFilename,
        content: documentSummary.summary_markdown,
      });
      const savedFileName = response.output_file.file_name;
      let message = `Saved summary: ${savedFileName}. Original files were not changed.`;
      try {
        const completion = await completeDocumentSummary({
          task_id: documentSummary.task_id,
          folder_name: "MindOS outputs",
          output_file_name: savedFileName,
          files_used_count: documentSummary.files_used.length,
          files_skipped_count: documentSummary.files_skipped.length,
          summary_style: documentSummary.summary_style ?? summaryStyle,
          output_format: documentSummary.output_format ?? summaryOutputFormat,
          file_types_used: fileTypesFromPaths(documentSummary.files_used),
          summary_title: documentSummary.summary_title,
          topic: documentSummary.topic,
          naming_confidence: documentSummary.naming_confidence ?? "low",
        });
        if (completion.warning) message = `${message} ${completion.warning}`;
      } catch (memoryError) {
        message = `${message} MindOS could not record the memory event: ${getErrorMessage(memoryError)}`;
      }
      addRecentTask({
        type: "document_summary",
        title: documentSummary.summary_title || "Created document summary",
        summary: `Used ${documentSummary.files_used.length} files - skipped ${documentSummary.files_skipped.length} - saved ${savedFileName}`,
        status: "completed",
        folderName: "MindOS outputs",
        outputFileName: savedFileName,
        details: {
          files_used_count: documentSummary.files_used.length,
          files_skipped_count: documentSummary.files_skipped.length,
          output_format: documentSummary.output_format ?? summaryOutputFormat,
          summary_style: documentSummary.summary_style ?? summaryStyle,
          file_types_used: fileTypesFromPaths(documentSummary.files_used).join(", "),
          topic: documentSummary.topic || "",
          naming_confidence: documentSummary.naming_confidence ?? "low",
        },
      });
      setSummarySaveMessage(message);
      if (fileSearchSelection?.emailRecipient) {
        await prepareGeneratedSummaryEmail(savedFileName, documentSummary.summary_markdown, fileSearchSelection.emailRecipient);
      }
    } catch (error) {
      setSummarySaveMessage(getErrorMessage(error));
    } finally {
      setSummarySaveLoading(false);
    }
  }

  async function prepareGeneratedSummaryEmail(fileName: string, content: string, recipient: string) {
    const file = new File([content], fileName, { type: fileName.endsWith(".txt") ? "text/plain" : "text/markdown" });
    const capabilities = await getTaskActionCapabilities();
    const status = await getGmailStatus();
    setActionCapabilities(capabilities);
    setGmailStatus(status);
    const sendAvailable = Boolean(capabilities.capabilities["gmail.sendEmail"]?.available || status.capabilities?.send_email);
    const draftAvailable = Boolean(capabilities.capabilities["gmail.createDraft"]?.available || (status.connected && status.capabilities?.create_draft));
    const executionActionType: TaskActionType = sendAvailable ? "gmail.sendEmail" : "gmail.createDraft";
    const subject = documentSummary?.summary_title || `Summary: ${fileSearchSelection?.query || "selected files"}`;
    const draft = {
      to: recipient,
      cc: "",
      bcc: "",
      subject,
      body: `Hi,\n\nI attached the generated summary file: ${fileName}.\n\nBest,\nMindOS`,
      message_id: "",
    };
    setGmailDraft(draft);
    setGmailAttachmentCandidates([
      {
        id: `generated:${fileName}:${Date.now()}`,
        name: fileName,
        size_bytes: file.size,
        extension: fileName.endsWith(".txt") ? ".txt" : ".md",
        source: "manual_picker",
        score: 100,
        reason: "Generated summary output.",
        selected: true,
        file,
      },
    ]);
    setPreparedAction({
      id: `action-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      actionType: "gmail.sendEmail",
      label: "Send generated report",
      supported: true,
      title: "Gmail send preview",
      summary: `Send generated summary to ${recipient}.`,
      riskLevel: "high",
      requiresConfirmation: true,
      executionActionType,
      canExecute: sendAvailable || draftAvailable,
      blockedReasons: sendAvailable || draftAvailable ? [] : ["Gmail is not connected. You can still use the saved summary file."],
      missingRequirements: sendAvailable || draftAvailable ? [] : ["gmail.sendEmail"],
      sources: [
        { type: "file_search", status: "available" },
        { type: "gmail", status: status.connected ? "connected" : "disconnected" },
      ],
      preview: {
        ...draft,
        note: "Review this Gmail preview. The generated summary file is attached.",
        sourceSummary: `Generated from ${documentSummary?.files_used.length || 0} selected file(s).`,
      },
    });
    setUiState("action_preview");
  }

  function handleEdit() {
    setUiState(documentSummarySource === "indexed_search" && fileSearchSelection ? "action_preview" : "context");
  }

  function handleRunPlanRequest() {
    setExecutionMessage(null);
    if (!filePlan) return;
    if (scanSource !== "browser_handle" || !browserFolder) {
      setExecutionMessage("Execution is currently available only for browser-selected folders. Choose a folder first.");
      return;
    }
    if (filePlan.blocked_reasons.length > 0) {
      setExecutionMessage("This plan is blocked and cannot run.");
      return;
    }
    if (filePlan.total_operations === 0) {
      setExecutionMessage("There are no file operations to run.");
      return;
    }
    setExecutionPhase("confirming");
  }

  async function handleExecuteBrowserPlan() {
    if (!filePlan || !browserFolder) return;
    setExecutionMessage(null);
    setExecutionProgress(null);
    setExecutionResult(null);
    setUndoResult(null);
    setExecutionPhase("running");
    try {
      const result = await executeBrowserFilePlan(browserFolder.handle, filePlan, {
        onProgress: setExecutionProgress,
      });
      setExecutionResult(result);
      setExecutionPhase("completed");
      addRecentTask({
        type: "file_organize",
        title: result.status === "completed" ? "Organized folder" : result.status === "partial" ? "Partially organized folder" : "File task failed",
        summary: `Created ${result.createdFolders} folders · moved ${result.movedFiles} files · skipped ${result.skipped.length}`,
        status: result.status,
        folderName: browserFolder.name,
        details: {
          created_folders: result.createdFolders,
          moved_files: result.movedFiles,
          skipped_count: result.skipped.length,
          errors_count: result.errors.length,
          undo_available: result.undoAvailable,
        },
      });
      await handleBrowserScan(browserFolder, { clearPlan: false });
    } catch (error) {
      setExecutionMessage(getErrorMessage(error));
      setExecutionPhase("idle");
    }
  }

  async function handleUndoBrowserPlan() {
    if (!browserFolder || !executionResult?.undoOperations.length) return;
    setExecutionMessage(null);
    setExecutionPhase("undoing");
    try {
      const result = await undoBrowserFilePlan(browserFolder.handle, executionResult.undoOperations);
      setUndoResult(result);
      setExecutionPhase("undone");
      await handleBrowserScan(browserFolder, { clearPlan: false });
    } catch (error) {
      setExecutionMessage(getErrorMessage(error));
      setExecutionPhase("completed");
    }
  }

  return (
    <div>
      <main className="mx-auto max-w-3xl">
        <Card className="space-y-4 p-4 md:p-5">
          <div>
            <p className="text-sm font-medium text-app-text">Ask MindOS</p>
            <p className="mt-1 text-xs text-app-muted">Preview actions before MindOS touches anything.</p>
          </div>

          <TaskCommandBar
            value={command}
            state={uiState}
            onChange={handleCommandChange}
            onFocus={() => {
              if (uiState !== "typing") setUiState("typing");
            }}
            onKeyDown={handleCommandKeyDown}
            onPrepare={() => void continueFromCommand()}
          />

          {uiState === "resting" ? (
            <div className="space-y-2">
              <p className="text-xs text-app-muted">Suggested actions</p>
              <TaskSuggestionChips suggestions={commandSuggestions} onSelect={handleSuggestionClick} />
            </div>
          ) : null}

          {showIntentHint ? (
            <TaskActionHint
              onSelect={() => {
                setPrepareError(null);
                setUiState("context");
              }}
            />
          ) : null}
          {showDetectedIntent ? <DetectedActionChip action={detectedAction} fileIntent={detectedIntent} /> : null}

          {showContext ? (
            <TaskContextPicker
              path={visiblePath}
              source={scanSource}
              inputRef={pathInputRef}
              scanLoading={scanLoading}
              choosingFolder={isChoosingFolder}
              onPathChange={(path) => {
                setBrowserFolder(null);
                setScanSource("backend_path");
                setRootPath(path);
                setPathIsStale(Boolean(scanResult && path !== scanResult.root_path));
                setScanError(null);
                setFolderPickerMessage(null);
                resetPlan();
              }}
              onPathKeyDown={(event) => {
                if (event.key !== "Enter") return;
                event.preventDefault();
                void handleScan(visiblePath);
              }}
              onFolderSelect={handleFolderSelect}
              onChooseFolder={() => void handleChooseFolder()}
              onScan={() => void handleScan(visiblePath)}
            />
          ) : null}

          {scanLoading ? <p className="rounded-md border border-violet-500/30 bg-violet-500/10 px-3 py-2 text-xs text-violet-100">Scanning folder...</p> : null}
          {folderPickerMessage ? <p className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">{folderPickerMessage}</p> : null}
          {scanError ? <p className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-100">{scanError}</p> : null}
          {prepareError ? <p className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-100">{prepareError}</p> : null}
          {prepareStatus ? <p className="rounded-md border border-violet-500/30 bg-violet-500/10 px-3 py-2 text-xs text-violet-100">{prepareStatus}</p> : null}
          {isFolderAction && scanResult ? <ScanSummary result={scanResult} categories={categories} stale={pathIsStale} source={scanSource} /> : null}

          {uiState === "typing" && commandValue ? (
            <div className="flex justify-end">
              <Button type="button" variant="primary" className="h-9 px-3" onClick={() => void continueFromCommand()} loading={prepareLoading}>
                <ChevronRight size={15} />
                Prepare
              </Button>
            </div>
          ) : null}

          {uiState === "context" && isFolderAction ? (
            <div className="flex justify-end">
              <Button type="button" variant="primary" className="h-9 px-3" onClick={() => void handlePrepare()} loading={prepareLoading} disabled={scanLoading}>
                <ListChecks size={15} />
                {pathIsStale ? "Scan & Prepare" : "Prepare"}
              </Button>
            </div>
          ) : null}

          {uiState === "document_options" && documentSelection ? (
            <DocumentSelectionCard
              selection={documentSelection}
              outputFilename={summaryOutputFilename}
              outputFormat={summaryOutputFormat}
              summaryStyle={summaryStyle}
              loading={prepareLoading}
              cloudWarning={cloudSummaryWarning}
              onSelectedPathsChange={(selectedPaths) => setDocumentSelection((current) => current ? { ...current, selectedPaths } : current)}
              onOutputFilenameChange={(filename) => {
                setSummaryFilenameWasEdited(true);
                setSummaryOutputFilename(filename);
              }}
              onOutputFormatChange={(format) => {
                setSummaryOutputFormat(format);
                setSummaryOutputFilename((current) => normalizedSummaryFilename(current, format));
              }}
              onSummaryStyleChange={setSummaryStyle}
              onCancelCloudWarning={() => {
                setCloudSummaryWarning(null);
                setPrepareLoading(false);
              }}
              onContinueCloudWarning={() => void handlePrepareSelectedDocumentSummary(true)}
              onEdit={handleEdit}
              onPrepare={() => void handlePrepareSelectedDocumentSummary(false)}
            />
          ) : null}

          {uiState === "plan" && filePlan ? (
            <TaskPlanCard
              plan={filePlan}
              source={scanSource}
              executionPhase={executionPhase}
              onEdit={handleEdit}
              onRun={handleRunPlanRequest}
            />
          ) : null}
          {uiState === "plan" && documentSummary ? (
            <DocumentSummaryPreviewCard
              summary={documentSummary}
              readResult={documentReadResult}
              outputFilename={summaryOutputFilename}
              saving={summarySaveLoading}
              saveMessage={summarySaveMessage}
              onOutputFilenameChange={(filename) => {
                setSummaryFilenameWasEdited(true);
                setSummaryOutputFilename(filename);
              }}
              onEdit={handleEdit}
              onSave={() => void handleSaveSummaryUnified()}
            />
          ) : null}
          {uiState === "plan" && logAnalysisReport ? (
            <LogAnalysisPreviewCard
              report={logAnalysisReport}
              outputFilename={logReportOutputFilename}
              saving={summarySaveLoading}
              saveMessage={summarySaveMessage}
              onOutputFilenameChange={setLogReportOutputFilename}
              onEdit={handleEdit}
              onSave={() => void handleSaveLogAnalysisReport()}
            />
          ) : null}
          {uiState === "action_preview" && preparedAction ? (
            <ActionPreviewRenderer
              action={preparedAction}
              capabilities={actionCapabilities}
              gmailStatus={gmailStatus}
              gmailDraft={gmailDraft}
              gmailDraftResult={gmailDraftResult}
              gmailDraftLoading={gmailDraftLoading}
              gmailDraftMessage={gmailDraftMessage}
              gmailAttachmentCandidates={gmailAttachmentCandidates}
              emailSearchMessages={emailSearchMessages}
              fileSearchSelection={fileSearchSelection}
              recentTasks={recentTasks}
              onGmailDraftChange={setGmailDraft}
              onGmailAttachmentsChange={updateGmailAttachmentCandidates}
              onManualGmailAttachmentFiles={handleManualGmailAttachmentFiles}
              onFileSearchSelectionChange={setFileSearchSelection}
              onPrepareIndexedFileSummary={() => {
                if (preparedAction.actionType === "log.analyzeFromSearch") {
                  void handlePrepareLogAnalysisReport();
                } else {
                  void handleContinueFromFileSearch();
                }
              }}
              onChooseFilesManually={() => {
                setUiState("context");
                pathInputRef.current?.focus();
              }}
              onCreateGmailDraft={() => void handleCreateGmailDraft()}
              onEdit={() => setUiState("typing")}
              onCancel={() => {
                setPreparedAction(null);
                setUiState(command.trim() ? "typing" : "resting");
              }}
            />
          ) : null}
          {actionApprovalPhase === "confirming" && preparedAction ? (
            <ActionConfirmationCard
              action={preparedAction}
              draft={gmailDraft}
              attachments={selectedAttachmentCandidates(gmailAttachmentCandidates)}
              onCancel={() => setActionApprovalPhase("idle")}
              onConfirm={() => void handleConfirmActionExecution()}
            />
          ) : null}
          {executionMessage ? <p className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">{executionMessage}</p> : null}
          {executionPhase === "confirming" && filePlan ? (
            <RunConfirmationCard plan={filePlan} onCancel={() => setExecutionPhase("idle")} onConfirm={() => void handleExecuteBrowserPlan()} />
          ) : null}
          {executionPhase === "running" && executionProgress ? <ExecutionProgressCard progress={executionProgress} /> : null}
          {executionResult && executionPhase !== "running" ? (
            <ExecutionResultCard
              result={executionResult}
              undoResult={undoResult}
              undoing={executionPhase === "undoing"}
              onUndo={() => void handleUndoBrowserPlan()}
            />
          ) : null}
        </Card>
        <RecentTasksCard
          tasks={recentTasks}
          message={clearTaskHistoryMessage}
          clearing={clearTaskHistoryLoading}
          onClearHistory={() => setShowClearTaskHistoryConfirm(true)}
        />
        {showClearTaskHistoryConfirm ? (
          <ClearTaskHistoryDialog
            clearing={clearTaskHistoryLoading}
            onCancel={() => setShowClearTaskHistoryConfirm(false)}
            onConfirm={() => void handleClearTaskHistory()}
          />
        ) : null}
      </main>
    </div>
  );
}

function TaskCommandBar({
  value,
  state,
  onChange,
  onFocus,
  onKeyDown,
  onPrepare,
}: {
  value: string;
  state: TaskUiState;
  onChange: (value: string) => void;
  onFocus: () => void;
  onKeyDown: (event: KeyboardEvent<HTMLInputElement>) => void;
  onPrepare: () => void;
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-app-border bg-zinc-950 px-3 py-2 shadow-sm shadow-black/10 focus-within:border-violet-500/60 focus-within:ring-2 focus-within:ring-violet-900/40">
      <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-violet-500/10 text-violet-200">
        <Sparkles size={16} />
      </span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onFocus={onFocus}
        onKeyDown={onKeyDown}
        placeholder="Ask MindOS to do something..."
        className="min-w-0 flex-1 bg-transparent text-sm text-app-text outline-none placeholder:text-zinc-600"
      />
      <button
        type="button"
        onClick={onPrepare}
        className="hidden rounded-md border border-app-border px-2.5 py-1.5 text-xs text-app-muted transition hover:border-violet-500/50 hover:text-violet-200 sm:inline-flex"
      >
        {state === "resting" ? "Safe mode" : "Prepare"}
      </button>
    </div>
  );
}

function TaskSuggestionChips({ suggestions, onSelect }: { suggestions: string[]; onSelect: (suggestion: string) => void }) {
  return (
    <div className="flex flex-wrap gap-2">
      {suggestions.map((suggestion) => (
        <button
          key={suggestion}
          type="button"
          onClick={() => onSelect(suggestion)}
          className="rounded-full border border-app-border bg-zinc-950 px-3 py-1 text-xs text-app-muted transition hover:border-violet-500/50 hover:bg-violet-500/10 hover:text-violet-200"
        >
          {suggestion}
        </button>
      ))}
    </div>
  );
}

function TaskActionHint({ onSelect }: { onSelect: () => void }) {
  return (
    <div className="rounded-lg border border-app-border bg-zinc-950/80 p-2">
      <button
        type="button"
        onClick={onSelect}
        className="flex w-full items-center justify-between rounded-md px-3 py-2 text-left transition hover:bg-violet-500/10"
      >
        <span className="flex items-center gap-3">
          <span className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-violet-500/10 text-violet-200">
            <FolderOpen size={16} />
          </span>
          <span>
            <span className="block text-sm font-medium text-app-text">Organize a folder</span>
            <span className="mt-1 flex flex-wrap items-center gap-2">
              <span className="text-xs text-app-muted">file.scan &rarr; sort &rarr; move</span>
              <span className="rounded-full border border-app-border px-2 py-0.5 text-[11px] text-app-muted">Local file task</span>
            </span>
          </span>
        </span>
        <ChevronRight size={16} className="text-app-muted" />
      </button>
    </div>
  );
}

function DetectedIntentChip({ intent }: { intent: FileTaskIntent }) {
  const detail =
    intent.intent === "move_category"
      ? intent.targetCategory
      : intent.intent === "document_summary"
        ? "Readable files"
      : intent.intent === "create_folders"
        ? intent.folderNames.length ? intent.folderNames.join(", ") : "Folders"
        : intent.intent === "rename_files"
          ? "Not connected"
          : intent.intent === "organize_by_type"
            ? "By type"
            : "Safe preview";
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-app-border bg-zinc-950/80 px-3 py-2 text-xs">
      <span className={intent.supported ? "text-violet-200" : "text-amber-200"}>{intent.label}</span>
      <span className="text-app-muted">·</span>
      <span className="text-app-muted">{detail}</span>
    </div>
  );
}

function DetectedActionChip({ action, fileIntent }: { action: ClassifiedTaskAction; fileIntent: FileTaskIntent }) {
  const detail =
    action.actionType === "file.organize"
      ? fileIntent.intent === "move_category"
        ? fileIntent.targetCategory
        : fileIntent.intent === "create_folders"
          ? fileIntent.folderNames.length ? fileIntent.folderNames.join(", ") : "Folders"
          : fileIntent.intent === "rename_files"
            ? "Not connected"
            : "By type"
      : action.actionType === "document.summary"
        ? "Readable files"
        : action.actionType === "file.search"
          ? "Connected folders"
          : action.actionType === "log.analyzeFromSearch"
            ? "Connected logs"
          : action.actionType === "document.summaryFromSearch"
            ? "Selected indexed files"
            : action.actionType === "document.reportFromSearch"
              ? "Report"
          : action.actionType === "gmail.sendGeneratedReport"
                ? "Gmail after confirmation"
                : action.actionType === "multi_step"
                  ? "File search first"
        : isEmailWriteAction(action.actionType)
          ? action.actionType === "gmail.sendEmail"
            ? "Send with confirmation"
            : "Draft only"
          : action.actionType === "gmail.searchEmails" || action.actionType === "gmail.summarizeEmails"
            ? "Email context"
            : action.actionType === "memory.report"
              ? "Memory context"
              : action.actionType === "github.lookup"
                ? "GitHub context"
                : "Safe preview";
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-app-border bg-zinc-950/80 px-3 py-2 text-xs">
      <span className={action.supported ? "text-violet-200" : "text-amber-200"}>{action.label}</span>
      <span className="text-app-muted">-</span>
      <span className="text-app-muted">{detail}</span>
    </div>
  );
}

function ActionPreviewRenderer({
  action,
  capabilities,
  gmailStatus,
  gmailDraft,
  gmailDraftResult,
  gmailDraftLoading,
  gmailDraftMessage,
  gmailAttachmentCandidates,
  emailSearchMessages,
  fileSearchSelection,
  recentTasks,
  onGmailDraftChange,
  onGmailAttachmentsChange,
  onManualGmailAttachmentFiles,
  onFileSearchSelectionChange,
  onPrepareIndexedFileSummary,
  onChooseFilesManually,
  onCreateGmailDraft,
  onEdit,
  onCancel,
}: {
  action: PreparedAction;
  capabilities: ActionCapabilityRegistry | null;
  gmailStatus: GmailStatusResponse | null;
  gmailDraft: { to: string; cc: string; bcc: string; subject: string; body: string; message_id: string };
  gmailDraftResult: GmailDraftResponse | null;
  gmailDraftLoading: boolean;
  gmailDraftMessage: string | null;
  gmailAttachmentCandidates: AttachmentCandidate[];
  emailSearchMessages: NormalizedEmailMessage[];
  fileSearchSelection: FileSearchSelection | null;
  recentTasks: RecentTaskItem[];
  onGmailDraftChange: (draft: { to: string; cc: string; bcc: string; subject: string; body: string; message_id: string }) => void;
  onGmailAttachmentsChange: (candidates: AttachmentCandidate[]) => void;
  onManualGmailAttachmentFiles: (files: FileList | null) => void;
  onFileSearchSelectionChange: (selection: FileSearchSelection | null) => void;
  onPrepareIndexedFileSummary: () => void;
  onChooseFilesManually: () => void;
  onCreateGmailDraft: () => void;
  onEdit: () => void;
  onCancel: () => void;
}) {
  if (isEmailWriteAction(action.actionType)) {
    return (
      <GmailDraftPreview
        action={action}
        capabilities={capabilities}
        gmailStatus={gmailStatus}
        draft={gmailDraft}
        result={gmailDraftResult}
        loading={gmailDraftLoading}
        message={gmailDraftMessage}
        attachments={gmailAttachmentCandidates}
        onDraftChange={onGmailDraftChange}
        onAttachmentsChange={onGmailAttachmentsChange}
        onManualAttachmentFiles={onManualGmailAttachmentFiles}
        onCreateDraft={onCreateGmailDraft}
        onEdit={onEdit}
        onCancel={onCancel}
      />
    );
  }
  if (action.actionType === "gmail.searchEmails" || action.actionType === "gmail.summarizeEmails") {
    return <EmailSearchPreview action={action} messages={emailSearchMessages} onEdit={onEdit} onCancel={onCancel} />;
  }
  if (action.actionType === "memory.report") {
    return <ReportPreview action={action} recentTasks={recentTasks} onEdit={onEdit} onCancel={onCancel} />;
  }
  if (action.actionType === "github.lookup") {
    return <LookupPreview icon={<Github size={16} />} action={action} title="Look up GitHub context" onEdit={onEdit} onCancel={onCancel} />;
  }
  if (isIndexedFileSearchAction(action.actionType) || action.actionType === "multi_step" || action.actionType === "log.analyzeFromSearch") {
    return (
      <FileSearchResultsPreview
        action={action}
        selection={fileSearchSelection}
        onSelectionChange={onFileSearchSelectionChange}
        onContinue={onPrepareIndexedFileSummary}
        onChooseFilesManually={onChooseFilesManually}
        onEdit={onEdit}
        onCancel={onCancel}
      />
    );
  }
  return <UnsupportedPreview action={action} onEdit={onEdit} onCancel={onCancel} />;
}

function FileSearchResultsPreview({
  action,
  selection,
  onSelectionChange,
  onContinue,
  onChooseFilesManually,
  onEdit,
  onCancel,
}: {
  action: PreparedAction;
  selection: FileSearchSelection | null;
  onSelectionChange: (selection: FileSearchSelection | null) => void;
  onContinue: () => void;
  onChooseFilesManually: () => void;
  onEdit: () => void;
  onCancel: () => void;
}) {
  const readableMatches = selection?.matches.filter((match) => Boolean(match.readable)) ?? [];
  const selectableMatches = selection?.matches.filter((match) => (action.actionType === "multi_step" ? Boolean(match.attachable) : Boolean(match.readable))) ?? [];
  const selectedCount = selection?.selectedKeys.length ?? 0;
  const canContinue = action.actionType !== "file.search" && selectedCount > 0;
  const isLogAnalysis = action.actionType === "log.analyzeFromSearch";

  function toggle(match: IndexedFileSearchMatch, checked: boolean) {
    if (!selection) return;
    const selectable = action.actionType === "multi_step" ? Boolean(match.attachable) : Boolean(match.readable);
    if (!selectable) return;
    const key = `${match.source_id}:${match.relative_path}`;
    const selectedKeys = checked
      ? Array.from(new Set([...selection.selectedKeys, key]))
      : selection.selectedKeys.filter((item) => item !== key);
    onSelectionChange({ ...selection, selectedKeys });
  }

  return (
    <div className="rounded-lg border border-app-border bg-zinc-950 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-violet-500/10 text-violet-200">
            <Search size={16} />
          </span>
          <div>
            <h2 className="text-sm font-semibold text-app-text">{isLogAnalysis ? "Log files found" : "Files found"}</h2>
            <p className="mt-1 text-xs text-app-muted">
              MindOS searched your connected folders{selection?.query ? ` for "${selection.query}"` : ""}
              {isLogAnalysis ? ". Choose the logs to analyze." : "."}
            </p>
          </div>
        </div>
        <Badge variant={selectableMatches.length ? "success" : "warning"}>
          {action.actionType === "multi_step" ? `${selectableMatches.length} attachable` : `${readableMatches.length} readable`}
        </Badge>
      </div>
      {selection?.statusMessage ? <p className="mt-3 text-xs text-app-muted">{selection.statusMessage}</p> : null}
      <div className="mt-3 space-y-2">
        {selection?.matches.length ? (
          selection.matches.map((match) => {
            const key = `${match.source_id}:${match.relative_path}`;
            const checked = selection.selectedKeys.includes(key);
            const selectable = action.actionType === "multi_step" ? Boolean(match.attachable) : Boolean(match.readable);
            return (
              <label key={key} className="flex gap-3 rounded-md border border-app-border bg-zinc-900/60 px-3 py-2 text-xs">
                <input
                  type="checkbox"
                  checked={checked}
                  disabled={!selectable || action.actionType === "file.search"}
                  onChange={(event) => toggle(match, event.target.checked)}
                  className="mt-1 h-4 w-4 accent-violet-500"
                />
                <FileText size={15} className="mt-1 shrink-0 text-app-muted" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium text-app-text">{match.file_name}</span>
                  <span className="mt-1 block truncate text-app-muted">
                    {match.source_name || "Connected folder"} - {match.relative_path}
                  </span>
                  <span className="mt-1 block text-app-muted">{readableMatchReason(match.match_reason)}</span>
                  {match.matched_excerpt ? <span className="mt-1 block line-clamp-2 text-zinc-400">{match.matched_excerpt}</span> : null}
                </span>
                <span className="shrink-0 space-y-1 text-right">
                  <Badge variant={selectable ? "success" : "warning"}>
                    {action.actionType === "multi_step" ? (selectable ? "Attachable" : "Blocked") : match.readable ? "Readable" : "Inventory only"}
                  </Badge>
                  <span className="block text-[11px] text-app-muted">{formatBytes(match.size_bytes)}</span>
                  <span className="block text-[11px] text-app-muted">{match.modified_at ? formatShortDate(match.modified_at) : ""}</span>
                </span>
              </label>
            );
          })
        ) : (
          <div className="rounded-md border border-app-border bg-zinc-900/60 px-3 py-3">
            <p className="text-xs font-medium text-app-text">{isLogAnalysis ? "No matching log files found in connected folders." : "No matching readable files found in connected folders."}</p>
            <p className="mt-1 text-xs text-app-muted">{isLogAnalysis ? "Try another log filename, error term, or connected folder search." : "You can choose files manually or try another search."}</p>
          </div>
        )}
      </div>
      <div className="mt-3 flex flex-wrap justify-end gap-2">
        <Button type="button" variant="secondary" className="h-9 px-3" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="button" variant="secondary" className="h-9 px-3" onClick={onEdit}>
          Try another search
        </Button>
        {!isLogAnalysis ? (
          <Button type="button" variant="secondary" className="h-9 px-3" onClick={onChooseFilesManually}>
            Choose files manually
          </Button>
        ) : null}
        {action.actionType !== "file.search" ? (
          <Button type="button" variant="primary" className="h-9 px-3" disabled={!canContinue} onClick={onContinue}>
            {isLogAnalysis ? "Analyze selected logs" : "Continue with selected files"}
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function GmailDraftPreview({
  action,
  capabilities,
  gmailStatus,
  draft,
  result,
  loading,
  message,
  attachments,
  onDraftChange,
  onAttachmentsChange,
  onManualAttachmentFiles,
  onCreateDraft,
  onEdit,
  onCancel,
}: {
  action: PreparedAction;
  capabilities: ActionCapabilityRegistry | null;
  gmailStatus: GmailStatusResponse | null;
  draft: { to: string; cc: string; bcc: string; subject: string; body: string; message_id: string };
  result: GmailDraftResponse | null;
  loading: boolean;
  message: string | null;
  attachments: AttachmentCandidate[];
  onDraftChange: (draft: { to: string; cc: string; bcc: string; subject: string; body: string; message_id: string }) => void;
  onAttachmentsChange: (candidates: AttachmentCandidate[]) => void;
  onManualAttachmentFiles: (files: FileList | null) => void;
  onCreateDraft: () => void;
  onEdit: () => void;
  onCancel: () => void;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const gmailConnected = Boolean(gmailStatus?.connected);
  const sendAvailable = Boolean(capabilities?.capabilities["gmail.sendEmail"]?.available || gmailStatus?.capabilities?.send_email);
  const draftAvailable = Boolean(
    capabilities?.capabilities["gmail.createDraft"]?.available ||
      (gmailStatus?.connected && gmailStatus.capabilities?.create_draft)
  );
  const effectiveActionType = action.executionActionType ?? action.actionType;
  const isSendAction = effectiveActionType === "gmail.sendEmail";
  const isDraftFallback = action.actionType === "gmail.sendEmail" && effectiveActionType === "gmail.createDraft";
  const disabledReason = getEmailActionDisabledReason({
    action,
    effectiveActionType,
    gmailConnected,
    sendAvailable,
    draftAvailable,
    draft,
  });
  const attachmentValidation = validateAttachments(attachments);
  const finalDisabledReason = disabledReason || attachmentValidation.warnings[0] || "";
  const title =
    effectiveActionType === "gmail.sendEmail"
      ? "Gmail send preview"
      : effectiveActionType === "gmail.replyDraft"
        ? "Gmail reply draft preview"
        : isDraftFallback
          ? "Gmail draft fallback preview"
          : "Gmail draft preview";
  const buttonLabel = effectiveActionType === "gmail.sendEmail" ? "Send Email" : effectiveActionType === "gmail.replyDraft" ? "Create Reply Draft" : "Create Gmail Draft";
  return (
    <div className="rounded-lg border border-app-border bg-zinc-950 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-violet-500/10 text-violet-200">
            <Mail size={16} />
          </span>
          <div>
            <h2 className="text-sm font-semibold text-app-text">{title}</h2>
            <p className="mt-1 text-xs text-app-muted">{action.preview?.note || "Review this draft before creating it in Gmail."}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={gmailConnected ? "success" : "warning"}>
            {gmailConnected ? `Gmail connected${gmailStatus?.email_address ? ` as ${gmailStatus.email_address}` : ""}` : "Gmail disconnected"}
          </Badge>
        </div>
      </div>

      {!gmailConnected ? (
        <p className="mt-3 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
          Gmail is not connected. Open Connectors &gt; Gmail and connect it.
        </p>
      ) : null}
      {isDraftFallback ? (
        <p className="mt-3 rounded-md border border-violet-500/30 bg-violet-500/10 px-3 py-2 text-xs text-violet-100">
          Gmail send is not connected yet. You can create a draft instead.
        </p>
      ) : null}
      {action.preview?.warning ? <p className="mt-3 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">{action.preview.warning}</p> : null}
      {action.preview?.sourceSummary ? <p className="mt-3 text-xs text-app-muted">Source: {action.preview.sourceSummary}</p> : null}

      <div className="mt-3 grid gap-3">
        {effectiveActionType === "gmail.replyDraft" ? (
          <label className="space-y-1 text-xs text-app-muted">
            <span>Original message id</span>
            <input
              value={draft.message_id}
              onChange={(event) => onDraftChange({ ...draft, message_id: event.target.value })}
              placeholder="message id from search result"
              className="h-9 w-full rounded-md border border-app-border bg-zinc-900 px-3 text-xs text-app-text outline-none focus:border-violet-500/60"
            />
          </label>
        ) : null}
        <label className="space-y-1 text-xs text-app-muted">
          <span>To</span>
          <input
            value={draft.to}
            onChange={(event) => onDraftChange({ ...draft, to: event.target.value })}
            placeholder={gmailStatus?.email_address || "recipient@example.com"}
            className="h-9 w-full rounded-md border border-app-border bg-zinc-900 px-3 text-xs text-app-text outline-none focus:border-violet-500/60"
          />
        </label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="space-y-1 text-xs text-app-muted">
            <span>Cc</span>
            <input
              value={draft.cc}
              onChange={(event) => onDraftChange({ ...draft, cc: event.target.value })}
              placeholder="optional"
              className="h-9 w-full rounded-md border border-app-border bg-zinc-900 px-3 text-xs text-app-text outline-none focus:border-violet-500/60"
            />
          </label>
          <label className="space-y-1 text-xs text-app-muted">
            <span>Bcc</span>
            <input
              value={draft.bcc}
              onChange={(event) => onDraftChange({ ...draft, bcc: event.target.value })}
              placeholder="optional"
              className="h-9 w-full rounded-md border border-app-border bg-zinc-900 px-3 text-xs text-app-text outline-none focus:border-violet-500/60"
            />
          </label>
        </div>
        <label className="space-y-1 text-xs text-app-muted">
          <span>Subject</span>
          <input
            value={draft.subject}
            onChange={(event) => onDraftChange({ ...draft, subject: event.target.value })}
            className="h-9 w-full rounded-md border border-app-border bg-zinc-900 px-3 text-xs text-app-text outline-none focus:border-violet-500/60"
          />
        </label>
        <label className="space-y-1 text-xs text-app-muted">
          <span>Body</span>
          <textarea
            value={draft.body}
            onChange={(event) => onDraftChange({ ...draft, body: event.target.value })}
            rows={8}
            className="w-full resize-none rounded-md border border-app-border bg-zinc-900 px-3 py-2 text-xs leading-5 text-app-text outline-none focus:border-violet-500/60"
          />
        </label>
      </div>

      <div className="mt-3 rounded-md border border-app-border bg-zinc-900/60 p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Paperclip size={14} className="text-violet-200" />
            <div>
              <p className="text-xs font-medium text-app-text">Attachments</p>
              <p className="mt-0.5 text-[11px] text-app-muted">
                {attachmentValidation.selected.length
                  ? `${attachmentValidation.selected.length} selected · ${formatBytes(attachmentValidation.totalBytes)}`
                  : action.preview?.attachmentIntent
                    ? attachments.length
                      ? "Found possible attachment files from connected folders. Select the file(s) to attach."
                      : "No attachment selected yet."
                    : "Choose files if this email needs attachments."}
              </p>
            </div>
          </div>
          <div className="flex gap-2">
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={(event) => {
                onManualAttachmentFiles(event.target.files);
                event.target.value = "";
              }}
            />
            {attachmentValidation.selected.length ? (
              <Button type="button" variant="secondary" className="h-8 px-2.5" onClick={() => onAttachmentsChange(attachments.map((candidate) => ({ ...candidate, selected: false })))}>
                Clear
              </Button>
            ) : null}
            <Button type="button" variant="secondary" className="h-8 px-2.5" onClick={() => fileInputRef.current?.click()}>
              Choose files
            </Button>
          </div>
        </div>
        {attachments.length ? (
          <div className="mt-3 space-y-2">
            {action.preview?.attachmentIntent ? <p className="text-[11px] font-medium uppercase tracking-wide text-app-muted">Possible files found</p> : null}
            {attachments.map((candidate) => (
              <div key={candidate.id} className="flex items-center gap-2 rounded-md border border-app-border bg-zinc-950/70 px-2 py-2 text-xs">
                <input
                  type="checkbox"
                  checked={candidate.selected}
                  disabled={!isAttachmentCandidateSelectable(candidate)}
                  onChange={(event) =>
                    onAttachmentsChange(
                      attachments.map((item) => (item.id === candidate.id ? { ...item, selected: event.target.checked } : item)),
                    )
                  }
                  className="h-4 w-4 accent-violet-500"
                />
                <FileText size={14} className="shrink-0 text-app-muted" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-app-text">{candidate.name}</p>
                  <p className="truncate text-[11px] text-app-muted">
                    {attachmentSourceLabel(candidate.source)} - {candidate.reason}
                    {candidate.size_bytes ? ` - ${formatBytes(candidate.size_bytes)}` : ""}
                    {candidate.modified_at ? ` - ${formatShortDate(candidate.modified_at)}` : ""}
                    {candidate.unavailableReason ? ` · ${candidate.unavailableReason}` : ""}
                  </p>
                </div>
                {candidate.source === "manual_picker" ? (
                  <button
                    type="button"
                    onClick={() => onAttachmentsChange(attachments.filter((item) => item.id !== candidate.id))}
                    className="rounded p-1 text-app-muted transition hover:bg-zinc-800 hover:text-app-text"
                    aria-label={`Remove ${candidate.name}`}
                  >
                    <X size={14} />
                  </button>
                ) : null}
              </div>
            ))}
          </div>
        ) : action.preview?.attachmentIntent ? (
          <p className="mt-3 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
            No matching files found in connected folders. Choose files manually.
          </p>
        ) : null}
        {typeof action.preview?.attachmentSearchStatus === "string" && action.preview.attachmentSearchStatus ? (
          <p className="mt-3 text-xs text-amber-200">{action.preview.attachmentSearchStatus}</p>
        ) : null}
        {attachmentValidation.warnings.length ? <p className="mt-3 text-xs text-amber-200">{attachmentValidation.warnings[0]}</p> : null}
      </div>

      <SourceStatusList sources={action.sources} />
      {finalDisabledReason ? <p className="mt-3 text-xs text-amber-200">{finalDisabledReason}</p> : null}
      {message ? <p className="mt-3 rounded-md border border-violet-500/30 bg-violet-500/10 px-3 py-2 text-xs text-violet-100">{message}</p> : null}
      {result ? (
        <p className="mt-2 text-xs text-app-muted">
          {isSendAction ? `Message id: ${result.message_id || "sent"}` : `Draft id: ${result.draft_id}`}
        </p>
      ) : null}

      <div className="mt-3 flex justify-end gap-2">
        <Button type="button" variant="secondary" className="h-9 px-3" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="button" variant="secondary" className="h-9 px-3" onClick={onEdit}>
          Edit request
        </Button>
        <Button type="button" variant="primary" className="h-9 px-3" loading={loading} disabled={Boolean(finalDisabledReason)} onClick={onCreateDraft}>
          {buttonLabel}
        </Button>
      </div>
    </div>
  );
}

function ActionConfirmationCard({
  action,
  draft,
  attachments,
  onCancel,
  onConfirm,
}: {
  action: PreparedAction;
  draft: { to: string; subject: string };
  attachments: AttachmentCandidate[];
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const effectiveActionType = action.executionActionType ?? action.actionType;
  if (effectiveActionType === "gmail.sendEmail") {
    return (
      <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="text-sm font-medium text-app-text">Send this Gmail email?</p>
            <p className="mt-1 text-xs text-app-muted">This will send the email from your connected Gmail account.</p>
          </div>
          <Badge variant="danger">high risk</Badge>
        </div>
        <div className="mt-3 rounded-md border border-app-border bg-zinc-950/70 px-3 py-2 text-xs">
          <p className="text-app-muted">
            To: <span className="text-app-text">{draft.to}</span>
          </p>
          <p className="mt-1 text-app-muted">
            Subject: <span className="text-app-text">{draft.subject}</span>
          </p>
          {attachments.length ? (
            <p className="mt-1 text-app-muted">
              Attachments: <span className="text-app-text">{attachments.map((attachment) => attachment.name).join(", ")}</span>
            </p>
          ) : null}
        </div>
        <p className="mt-3 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-100">
          This will send the email from your connected Gmail account.
        </p>
        <div className="mt-3 flex justify-end gap-2">
          <Button type="button" variant="secondary" className="h-8 px-3" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="button" variant="primary" className="h-8 px-3" onClick={onConfirm}>
            Confirm Send
          </Button>
        </div>
      </div>
    );
  }
  const isHighRisk = action.riskLevel === "high";
  const bullets = safetyBulletsForAction(action);
  return (
    <div className={`rounded-lg border p-3 ${isHighRisk ? "border-red-500/40 bg-red-500/10" : "border-violet-500/30 bg-violet-500/10"}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-medium text-app-text">Confirm action</p>
          <p className="mt-1 text-xs text-app-muted">MindOS will do the following: {action.summary}</p>
        </div>
        <Badge variant={isHighRisk ? "danger" : "warning"}>{action.riskLevel} risk</Badge>
      </div>
      <div className="mt-3 rounded-md border border-app-border bg-zinc-950/70 px-3 py-2">
        <p className="text-xs font-medium text-app-text">Safety</p>
        <ul className="mt-2 space-y-1 text-xs text-app-muted">
          {bullets.map((bullet) => (
            <li key={bullet}>- {bullet}</li>
          ))}
        </ul>
      </div>
      <div className="mt-3 flex justify-end gap-2">
        <Button type="button" variant="secondary" className="h-8 px-3" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="button" variant="primary" className="h-8 px-3" onClick={onConfirm}>
          Confirm and run
        </Button>
      </div>
    </div>
  );
}

function EmailSearchPreview({
  action,
  messages,
  onEdit,
  onCancel,
}: {
  action: PreparedAction;
  messages: NormalizedEmailMessage[];
  onEdit: () => void;
  onCancel: () => void;
}) {
  return (
    <DetectedActionCard icon={<Mail size={16} />} action={action} title={action.actionType === "gmail.summarizeEmails" ? "Email summary preview" : "Email search preview"} onEdit={onEdit} onCancel={onCancel}>
      {action.blockedReasons.length ? <p className="text-xs text-amber-100">{action.blockedReasons[0]}</p> : null}
      {action.preview?.note ? <p className="text-xs text-app-muted">{action.preview.note}</p> : null}
      <div className="mt-3 space-y-2">
        {messages.length ? (
          messages.slice(0, 8).map((message) => (
            <div key={message.id} className="rounded-md border border-app-border bg-zinc-900/70 px-3 py-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs font-medium text-app-text">{message.subject || "(no subject)"}</p>
                <span className="text-[11px] text-app-muted">{message.date ? formatTimestamp(message.date) : ""}</span>
              </div>
              <p className="mt-1 text-xs text-app-muted">From: {message.from || "unknown"}</p>
              <p className="mt-1 text-xs text-app-muted">{message.body_excerpt || message.snippet || "No excerpt available."}</p>
            </div>
          ))
        ) : (
          <p className="rounded-md border border-app-border bg-zinc-900/70 px-3 py-2 text-xs text-app-muted">No email messages to show.</p>
        )}
      </div>
    </DetectedActionCard>
  );
}

function LookupPreview({ icon, action, title, onEdit, onCancel }: { icon: ReactNode; action: PreparedAction; title: string; onEdit: () => void; onCancel: () => void }) {
  return (
    <DetectedActionCard icon={icon} action={action} title={title} onEdit={onEdit} onCancel={onCancel}>
      <p className="text-xs text-app-muted">{action.preview?.note}</p>
      <p className="mt-2 text-xs text-app-muted">This is a context lookup preview. MindOS will use connected memory/context instead of asking for a folder.</p>
    </DetectedActionCard>
  );
}

function ReportPreview({ action, recentTasks, onEdit, onCancel }: { action: PreparedAction; recentTasks: RecentTaskItem[]; onEdit: () => void; onCancel: () => void }) {
  const lastWeek = recentTasksFromLastDays(recentTasks, 7);
  return (
    <DetectedActionCard icon={<FileText size={16} />} action={action} title="Prepare memory report" onEdit={onEdit} onCancel={onCancel}>
      <p className="text-xs text-app-muted">{action.preview?.note}</p>
      <div className="mt-3 rounded-md border border-app-border bg-zinc-900/70 px-3 py-2">
        <p className="text-xs font-medium text-app-text">Sources</p>
        <p className="mt-1 text-xs text-app-muted">
          {lastWeek.length ? `${lastWeek.length} recent task items found from the last 7 days.` : "No task history found from the last 7 days. MindOS can still use Memory when the report flow is connected."}
        </p>
      </div>
    </DetectedActionCard>
  );
}

function UnsupportedPreview({ action, onEdit, onCancel }: { action: PreparedAction; onEdit: () => void; onCancel: () => void }) {
  return (
    <DetectedActionCard icon={<Search size={16} />} action={action} title={action.label} onEdit={onEdit} onCancel={onCancel}>
      <p className="text-xs text-amber-100">{action.reason || "MindOS cannot safely prepare this request yet."}</p>
    </DetectedActionCard>
  );
}

function DetectedActionCard({
  icon,
  action,
  title,
  children,
  onEdit,
  onCancel,
}: {
  icon: ReactNode;
  action: PreparedAction;
  title: string;
  children: ReactNode;
  onEdit: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="rounded-lg border border-app-border bg-zinc-950 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-violet-500/10 text-violet-200">{icon}</span>
          <div>
            <h2 className="text-sm font-semibold text-app-text">{title}</h2>
            <p className="mt-1 text-xs text-app-muted">{action.requiresConfirmation ? "Preview first. Confirmation required." : "Preview only for now."}</p>
          </div>
        </div>
        <Badge variant={action.supported ? "info" : "warning"}>{action.label}</Badge>
      </div>
      <div className="mt-3">{children}</div>
      <SourceStatusList sources={action.sources} />
      <div className="mt-3 flex justify-end gap-2">
        <Button type="button" variant="secondary" className="h-9 px-3" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="button" variant="secondary" className="h-9 px-3" onClick={onEdit}>
          Edit request
        </Button>
      </div>
    </div>
  );
}

function SourceStatusList({ sources }: { sources: PreparedAction["sources"] }) {
  if (!sources.length) return null;
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {sources.map((source) => (
        <span key={`${source.type}:${source.status}`} className="rounded-full border border-app-border px-2.5 py-1 text-[11px] text-app-muted">
          {source.type.replace(/_/g, " ")}: <span className={source.status === "missing" || source.status === "disconnected" ? "text-amber-200" : "text-violet-200"}>{source.status}</span>
        </span>
      ))}
    </div>
  );
}

function TaskContextPicker({
  path,
  source,
  inputRef,
  scanLoading,
  choosingFolder,
  onPathChange,
  onPathKeyDown,
  onFolderSelect,
  onChooseFolder,
  onScan,
}: {
  path: string;
  source: ScanSource;
  inputRef: RefObject<HTMLInputElement>;
  scanLoading: boolean;
  choosingFolder: boolean;
  onPathChange: (path: string) => void;
  onPathKeyDown: (event: KeyboardEvent<HTMLInputElement>) => void;
  onFolderSelect: (path: string) => void;
  onChooseFolder: () => void;
  onScan: () => void;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 rounded-lg border border-app-border bg-zinc-950 px-3 py-2">
        <span className="shrink-0 rounded-full border border-violet-500/30 bg-violet-500/10 px-2.5 py-1 text-xs text-violet-200">
          Organize folder
        </span>
        <input
          ref={inputRef}
          value={path}
          onChange={(event) => onPathChange(event.target.value)}
          onKeyDown={onPathKeyDown}
          className="min-w-0 flex-1 bg-transparent font-mono text-sm text-app-text outline-none"
          aria-label="Folder path"
          readOnly={source === "browser_handle"}
        />
        <Button type="button" variant="secondary" className="h-8 px-3" loading={choosingFolder} onClick={onChooseFolder}>
          <FolderOpen size={14} />
          Choose
        </Button>
        <Button type="button" variant="secondary" className="h-8 px-3" loading={scanLoading} onClick={onScan}>
          Scan
        </Button>
      </div>
      <div className="flex flex-wrap gap-2">
        {folderSuggestions.map((folder) => (
          <button
            key={folder.path}
            type="button"
            onClick={() => onFolderSelect(folder.path)}
            className="rounded-md border border-app-border bg-zinc-950 px-2.5 py-1 text-xs text-app-muted transition hover:border-violet-500/50 hover:text-violet-200"
          >
            {folder.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function ScanSummary({ result, categories, stale, source }: { result: FileSnapshotResponse; categories: CategorySummary[]; stale: boolean; source: ScanSource }) {
  const displayName = result.display_name || result.root_name || result.root_path || "Selected folder";
  return (
    <div className="rounded-lg border border-app-border bg-zinc-950 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-mono text-sm text-app-text">{displayName}</p>
          <p className="mt-1 text-xs text-app-muted">
            {result.total_files} files - {result.total_folders} folders - {formatBytes(result.total_size_bytes)}
          </p>
          {source === "browser_handle" ? <p className="mt-1 text-xs text-violet-200">Browser-selected folder</p> : null}
        </div>
        {stale ? <Badge variant="warning">Scan needs refresh</Badge> : result.truncated ? <Badge variant="warning">Limited to {result.max_files} files</Badge> : <Badge variant="success">Scan ready</Badge>}
      </div>
      {stale ? <p className="mt-2 text-xs text-amber-200">Folder path changed. Scan again before preparing a fresh plan.</p> : null}
      {categories.length ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {categories.map((category) => (
            <span key={category.label} className="rounded-full border border-app-border bg-zinc-900 px-2.5 py-1 text-xs text-app-muted">
              {category.label}: {category.count}
            </span>
          ))}
        </div>
      ) : null}
      {result.warnings.length ? <CompactList title="Warnings" items={result.warnings.map((warning) => ({ label: warning }))} tone="warning" /> : null}
    </div>
  );
}

function TaskPlanCard({
  plan,
  source,
  executionPhase,
  onEdit,
  onRun,
}: {
  plan: FileTaskPlan;
  source: ScanSource;
  executionPhase: ExecutionPhase;
  onEdit: () => void;
  onRun: () => void;
}) {
  const canRun = source === "browser_handle" && plan.status === "awaiting_confirmation" && plan.total_operations > 0 && plan.blocked_reasons.length === 0 && executionPhase !== "running";
  const statusLabel = plan.status === "unsupported" ? "unsupported" : plan.status === "empty" ? "no operations" : `${plan.total_operations} operations`;
  return (
    <div className="rounded-lg border border-app-border bg-zinc-950 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-app-text">Plan for {plan.root_path}</h2>
        <div className="flex flex-wrap gap-2">
          <Badge variant={plan.status === "blocked" || plan.status === "unsupported" ? "danger" : plan.status === "empty" ? "default" : "info"}>
            {statusLabel}
          </Badge>
          <Badge variant={plan.planner_provider ? "success" : isFallbackPlan(plan) ? "warning" : "default"}>
            {plan.planner_provider ? "AI-assisted plan" : isFallbackPlan(plan) ? "Fallback plan" : "Deterministic plan"}
          </Badge>
        </div>
      </div>
      <p className="mt-2 text-sm text-app-muted">{plan.summary}</p>
      {plan.planner_warning ? <p className="mt-1 text-xs text-amber-200">{plan.planner_warning}</p> : null}
      {plan.status === "empty" ? <EmptyPlanState plan={plan} /> : null}
      {plan.status === "unsupported" ? <UnsupportedPlanState plan={plan} /> : null}

      {plan.blocked_reasons.length ? <CompactList title="Blocked" items={plan.blocked_reasons.map((reason) => ({ label: reason }))} tone="danger" /> : null}
      {plan.warnings.length ? <CompactList title="Warnings" items={plan.warnings.map((warning) => ({ label: warning }))} tone="warning" /> : null}

      {plan.status === "awaiting_confirmation" ? <OperationPreview plan={plan} /> : null}

      <div className="mt-3 flex justify-end gap-2">
        <Button type="button" variant="secondary" className="h-9 px-3" onClick={onEdit}>
          Edit
        </Button>
        <Button type="button" variant="primary" className="h-9 px-3" disabled={!canRun} onClick={onRun} title={canRun ? "Run this browser-selected folder plan." : "Execution currently requires a browser-selected folder with runnable operations."}>
          <Play size={15} />
          Run plan
        </Button>
      </div>
    </div>
  );
}

function EmptyPlanState({ plan }: { plan: FileTaskPlan }) {
  return (
    <div className="mt-3 rounded-md border border-app-border bg-zinc-900/70 px-3 py-2">
      <p className="text-xs font-medium text-app-text">No matching files found</p>
      <p className="mt-1 text-xs text-app-muted">{plan.summary}</p>
      {Object.keys(plan.category_counts).length ? (
        <div className="mt-2 flex flex-wrap gap-2">
          {Object.entries(plan.category_counts)
            .sort((a, b) => b[1] - a[1])
            .map(([category, count]) => (
              <span key={category} className="rounded-full border border-app-border px-2 py-0.5 text-[11px] text-app-muted">
                {category}: {count}
              </span>
            ))}
        </div>
      ) : null}
    </div>
  );
}

function UnsupportedPlanState({ plan }: { plan: FileTaskPlan }) {
  return (
    <div className="mt-3 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2">
      <p className="text-xs font-medium text-amber-100">This task is not supported safely yet.</p>
      {plan.blocked_reasons[0] ? <p className="mt-1 text-xs text-amber-100">{plan.blocked_reasons[0]}</p> : null}
    </div>
  );
}

function DocumentSelectionCard({
  selection,
  outputFilename,
  outputFormat,
  summaryStyle,
  loading,
  cloudWarning,
  onSelectedPathsChange,
  onOutputFilenameChange,
  onOutputFormatChange,
  onSummaryStyleChange,
  onCancelCloudWarning,
  onContinueCloudWarning,
  onEdit,
  onPrepare,
}: {
  selection: DocumentSummarySelection;
  outputFilename: string;
  outputFormat: "markdown" | "text";
  summaryStyle: DocumentSummaryStyle;
  loading: boolean;
  cloudWarning: CloudSummaryWarning;
  onSelectedPathsChange: (paths: string[]) => void;
  onOutputFilenameChange: (filename: string) => void;
  onOutputFormatChange: (format: "markdown" | "text") => void;
  onSummaryStyleChange: (style: DocumentSummaryStyle) => void;
  onCancelCloudWarning: () => void;
  onContinueCloudWarning: () => void;
  onEdit: () => void;
  onPrepare: () => void;
}) {
  const [showSkipped, setShowSkipped] = useState(false);
  const selected = new Set(selection.selectedPaths);
  const markdownFiles = selection.candidates.filter((file) => file.extension.toLowerCase() === ".md").map((file) => file.relative_path);
  const textFiles = selection.candidates
    .filter((file) => [".txt", ".log", ".csv", ".json"].includes(file.extension.toLowerCase()))
    .map((file) => file.relative_path);

  function toggle(path: string) {
    const next = new Set(selected);
    if (next.has(path)) {
      next.delete(path);
    } else {
      next.add(path);
    }
    onSelectedPathsChange([...next]);
  }

  return (
    <div className="rounded-lg border border-app-border bg-zinc-950 p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-app-text">Documents to summarize</h2>
          <p className="mt-1 text-xs text-app-muted">
            {selection.selectedPaths.length} readable files selected - {selection.candidates.length} readable - {selection.skipped.length} skipped
          </p>
        </div>
        <Badge variant={selection.candidates.length ? "success" : "default"}>{selection.candidates.length} readable</Badge>
      </div>

      {selection.warnings.length ? <CompactList title="Notes" items={selection.warnings.map((warning) => ({ label: warning }))} tone="warning" /> : null}

      {selection.candidates.length ? (
        <>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button type="button" variant="secondary" className="h-8 px-3" onClick={() => onSelectedPathsChange(selection.candidates.map((file) => file.relative_path))}>
              Select all
            </Button>
            <Button type="button" variant="secondary" className="h-8 px-3" onClick={() => onSelectedPathsChange([])}>
              Clear
            </Button>
            <Button type="button" variant="secondary" className="h-8 px-3" onClick={() => onSelectedPathsChange(textFiles)}>
              Select text files
            </Button>
            <Button type="button" variant="secondary" className="h-8 px-3" onClick={() => onSelectedPathsChange(markdownFiles)}>
              Select markdown
            </Button>
          </div>

          <div className="mt-3 max-h-56 space-y-1 overflow-y-auto rounded-md border border-app-border bg-zinc-900/50 p-2">
            {selection.candidates.map((file) => (
              <label key={file.relative_path} className="flex cursor-pointer items-center gap-3 rounded-md px-2 py-2 text-xs transition hover:bg-violet-500/10">
                <input
                  type="checkbox"
                  checked={selected.has(file.relative_path)}
                  onChange={() => toggle(file.relative_path)}
                  className="h-4 w-4 accent-violet-500"
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-app-text">{file.name}</span>
                  <span className="mt-0.5 block truncate text-app-muted">{file.relative_path}</span>
                </span>
                <span className="rounded-full border border-app-border px-2 py-0.5 text-[11px] text-app-muted">{file.extension || "file"}</span>
                <span className="w-16 text-right text-[11px] text-app-muted">{formatBytes(file.size_bytes)}</span>
              </label>
            ))}
          </div>
        </>
      ) : (
        <div className="mt-3 rounded-md border border-app-border bg-zinc-900/70 px-3 py-2">
          <p className="text-xs font-medium text-app-text">I couldn't find readable documents in this folder.</p>
          <p className="mt-1 text-xs text-app-muted">MindOS can currently summarize txt, md, log, json, csv, PDF, and DOCX files.</p>
        </div>
      )}

      {selection.skipped.length ? (
        <div className="mt-3">
          <button type="button" className="text-xs text-violet-300 hover:text-violet-200" onClick={() => setShowSkipped((current) => !current)}>
            {showSkipped ? "Hide skipped files" : `Show ${selection.skipped.length} skipped files`}
          </button>
          {showSkipped ? (
            <CompactList
              title="Skipped"
              items={selection.skipped.slice(0, 20).map((file) => ({ label: file.relative_path, detail: file.reason }))}
              tone="muted"
            />
          ) : null}
        </div>
      ) : null}

      <div className="mt-3 grid gap-3 md:grid-cols-[1fr_150px_150px]">
        <label className="space-y-1 text-xs text-app-muted">
          <span>Output filename</span>
          <input
            value={outputFilename}
            onChange={(event) => onOutputFilenameChange(event.target.value)}
            className="h-9 w-full rounded-md border border-app-border bg-zinc-900 px-3 font-mono text-xs text-app-text outline-none focus:border-violet-500/60"
          />
          <span className="block text-[11px] text-app-muted">MindOS will suggest a filename after reading the documents.</span>
        </label>
        <label className="space-y-1 text-xs text-app-muted">
          <span>Output format</span>
          <select
            value={outputFormat}
            onChange={(event) => onOutputFormatChange(event.target.value as "markdown" | "text")}
            className="h-9 w-full rounded-md border border-app-border bg-zinc-900 px-3 text-xs text-app-text outline-none focus:border-violet-500/60"
          >
            <option value="markdown">Markdown (.md)</option>
            <option value="text">Text (.txt)</option>
          </select>
        </label>
        <label className="space-y-1 text-xs text-app-muted">
          <span>Summary style</span>
          <select
            value={summaryStyle}
            onChange={(event) => onSummaryStyleChange(event.target.value as DocumentSummaryStyle)}
            className="h-9 w-full rounded-md border border-app-border bg-zinc-900 px-3 text-xs text-app-text outline-none focus:border-violet-500/60"
          >
            <option value="brief">Brief</option>
            <option value="detailed">Detailed</option>
            <option value="file_by_file">File-by-file</option>
          </select>
        </label>
      </div>

      {cloudWarning ? (
        <div className="mt-3 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2">
          <p className="text-xs font-medium text-amber-100">Selected document text, including extracted PDF/DOCX text, will be sent to {cloudWarning.provider} to generate the summary.</p>
          <p className="mt-1 text-xs text-amber-100">{cloudWarning.displayName}</p>
          <div className="mt-3 flex justify-end gap-2">
            <Button type="button" variant="secondary" className="h-8 px-3" onClick={onCancelCloudWarning}>
              Cancel
            </Button>
            <Button type="button" variant="primary" className="h-8 px-3" onClick={onContinueCloudWarning}>
              Continue
            </Button>
          </div>
        </div>
      ) : null}

      <div className="mt-3 flex justify-end gap-2">
        <Button type="button" variant="secondary" className="h-9 px-3" onClick={onEdit}>
          Edit
        </Button>
        <Button type="button" variant="primary" className="h-9 px-3" loading={loading} disabled={!selection.candidates.length || loading} onClick={onPrepare}>
          Prepare Summary
        </Button>
      </div>
    </div>
  );
}

function DocumentSummaryPreviewCard({
  summary,
  readResult,
  outputFilename,
  saving,
  saveMessage,
  onOutputFilenameChange,
  onEdit,
  onSave,
}: {
  summary: DocumentSummaryPrepareResponse;
  readResult: BrowserDocumentReadResult | null;
  outputFilename: string;
  saving: boolean;
  saveMessage: string | null;
  onOutputFilenameChange: (filename: string) => void;
  onEdit: () => void;
  onSave: () => void;
}) {
  const canSave = summary.status === "preview" && summary.summary_markdown.trim().length > 0;
  return (
    <div className="rounded-lg border border-app-border bg-zinc-950 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-app-text">Summary preview</h2>
        <Badge variant={summary.status === "preview" ? "success" : summary.status === "empty" ? "default" : "danger"}>
          {summary.status}
        </Badge>
      </div>
      {summary.provider && summary.provider !== "ollama" && summary.provider !== "fake" ? (
        <p className="mt-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
          Selected document text was sent to the cloud model provider for this preview.
        </p>
      ) : null}
      <div className="mt-3 grid gap-2 text-xs text-app-muted sm:grid-cols-3">
        <span>Files used: {summary.files_used.length}</span>
        <span>Skipped: {summary.files_skipped.length}</span>
        <span>Output: {outputFilename}</span>
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-[1fr_220px]">
        <label className="space-y-1 text-xs text-app-muted">
          <span>Summary title</span>
          <div className="rounded-md border border-app-border bg-zinc-900 px-3 py-2 text-xs text-app-text">
            {summary.summary_title || "Created document summary"}
          </div>
        </label>
        <label className="space-y-1 text-xs text-app-muted">
          <span>Output filename</span>
          <input
            value={outputFilename}
            onChange={(event) => onOutputFilenameChange(event.target.value)}
            className="h-9 w-full rounded-md border border-app-border bg-zinc-900 px-3 font-mono text-xs text-app-text outline-none focus:border-violet-500/60"
          />
        </label>
      </div>
      {summary.topic ? (
        <p className="mt-2 text-xs text-app-muted">
          Topic: <span className="text-app-text">{summary.topic}</span>
          {summary.naming_confidence ? ` · ${summary.naming_confidence} confidence` : ""}
        </p>
      ) : null}
      {summary.files_used.length ? (
        <CompactList title="Files used" items={summary.files_used.slice(0, 8).map((file) => ({ label: file }))} />
      ) : null}
      {summary.files_skipped.length ? (
        <CompactList
          title="Skipped"
          items={summary.files_skipped.slice(0, 8).map((file) => ({ label: file.relative_path, detail: file.reason }))}
          tone="muted"
        />
      ) : null}
      {summary.warnings.length ? <CompactList title="Warnings" items={summary.warnings.map((warning) => ({ label: warning }))} tone="warning" /> : null}
      {readResult ? (
        <p className="mt-3 text-xs text-app-muted">
          Read {readResult.files_read.length} files · {readResult.total_chars.toLocaleString()} characters extracted
        </p>
      ) : null}
      <div className="mt-3 max-h-80 overflow-y-auto rounded-md border border-app-border bg-zinc-900/70 p-3">
        <pre className="whitespace-pre-wrap break-words text-xs leading-5 text-app-text">{summary.summary_markdown}</pre>
      </div>
      {saveMessage ? <p className="mt-3 rounded-md border border-violet-500/30 bg-violet-500/10 px-3 py-2 text-xs text-violet-100">{saveMessage}</p> : null}
      <div className="mt-3 flex justify-end gap-2">
        <Button type="button" variant="secondary" className="h-9 px-3" onClick={onEdit}>
          Edit
        </Button>
        <Button type="button" variant="primary" className="h-9 px-3" loading={saving} disabled={!canSave} onClick={onSave}>
          Save summary
        </Button>
      </div>
    </div>
  );
}

function LogAnalysisPreviewCard({
  report,
  outputFilename,
  saving,
  saveMessage,
  onOutputFilenameChange,
  onEdit,
  onSave,
}: {
  report: LogAnalysisPrepareResponse;
  outputFilename: string;
  saving: boolean;
  saveMessage: string | null;
  onOutputFilenameChange: (filename: string) => void;
  onEdit: () => void;
  onSave: () => void;
}) {
  const canSave = report.status === "preview" && report.report_markdown.trim().length > 0;
  const statusVariant = report.status === "preview" ? "success" : report.status === "empty" ? "default" : "danger";
  return (
    <div className="rounded-lg border border-app-border bg-zinc-950 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-app-text">Log analysis preview</h2>
          <p className="mt-1 text-xs text-app-muted">Secrets are redacted before analysis. Original logs are not changed.</p>
        </div>
        <Badge variant={statusVariant}>{report.status}</Badge>
      </div>
      {report.provider && report.provider !== "ollama" && report.provider !== "fake" ? (
        <p className="mt-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
          Redacted log excerpts were sent to the cloud model provider for this preview.
        </p>
      ) : null}
      <div className="mt-3 grid gap-2 text-xs text-app-muted sm:grid-cols-3">
        <span>Files analyzed: {report.files_used.length}</span>
        <span>Skipped: {report.files_skipped.length}</span>
        <span>Output: {outputFilename}</span>
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-[1fr_240px]">
        <label className="space-y-1 text-xs text-app-muted">
          <span>Report title</span>
          <div className="rounded-md border border-app-border bg-zinc-900 px-3 py-2 text-xs text-app-text">
            {report.report_title || "Log analysis report"}
          </div>
        </label>
        <label className="space-y-1 text-xs text-app-muted">
          <span>Output filename</span>
          <input
            value={outputFilename}
            onChange={(event) => onOutputFilenameChange(event.target.value)}
            className="h-9 w-full rounded-md border border-app-border bg-zinc-900 px-3 font-mono text-xs text-app-text outline-none focus:border-violet-500/60"
          />
        </label>
      </div>
      {report.files_used.length ? <CompactList title="Logs analyzed" items={report.files_used.slice(0, 8).map((file) => ({ label: file }))} /> : null}
      {report.evidence.length ? (
        <CompactList
          title="Evidence captured"
          items={report.evidence.slice(0, 6).map((file) => ({
            label: file.relative_path,
            detail: `${file.error_lines.length} error lines - ${file.repeated_patterns.length} repeated patterns`,
          }))}
          tone="muted"
        />
      ) : null}
      {report.files_skipped.length ? (
        <CompactList
          title="Skipped"
          items={report.files_skipped.slice(0, 8).map((file) => ({ label: file.relative_path, detail: file.reason }))}
          tone="muted"
        />
      ) : null}
      {report.warnings.length ? <CompactList title="Warnings" items={report.warnings.map((warning) => ({ label: warning }))} tone="warning" /> : null}
      {report.planner_warning ? <p className="mt-3 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">{report.planner_warning}</p> : null}
      <div className="mt-3 max-h-80 overflow-y-auto rounded-md border border-app-border bg-zinc-900/70 p-3">
        <pre className="whitespace-pre-wrap break-words text-xs leading-5 text-app-text">{report.report_markdown}</pre>
      </div>
      {saveMessage ? <p className="mt-3 rounded-md border border-violet-500/30 bg-violet-500/10 px-3 py-2 text-xs text-violet-100">{saveMessage}</p> : null}
      <div className="mt-3 flex justify-end gap-2">
        <Button type="button" variant="secondary" className="h-9 px-3" onClick={onEdit}>
          Edit
        </Button>
        <Button type="button" variant="primary" className="h-9 px-3" loading={saving} disabled={!canSave} onClick={onSave}>
          Save report
        </Button>
      </div>
    </div>
  );
}

function RunConfirmationCard({ plan, onCancel, onConfirm }: { plan: FileTaskPlan; onCancel: () => void; onConfirm: () => void }) {
  return (
    <div className="rounded-lg border border-violet-500/30 bg-violet-500/10 p-3">
      <p className="text-sm font-medium text-app-text">Run this plan?</p>
      <p className="mt-1 text-xs text-app-muted">
        MindOS will create {plan.create_folder_count} folders and move {plan.move_file_count} files inside the selected folder. No overwrites are allowed.
      </p>
      <div className="mt-3 flex justify-end gap-2">
        <Button type="button" variant="secondary" className="h-8 px-3" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="button" variant="primary" className="h-8 px-3" onClick={onConfirm}>
          Run safely
        </Button>
      </div>
    </div>
  );
}

function ExecutionProgressCard({ progress }: { progress: BrowserExecutionProgress }) {
  return (
    <div className="rounded-lg border border-app-border bg-zinc-950 p-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-app-text">Running plan</p>
          <p className="mt-1 text-xs text-app-muted">{progress.message}</p>
        </div>
        <Badge variant="info">{progress.percent}%</Badge>
      </div>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-zinc-900">
        <div className="h-full rounded-full bg-violet-400 transition-all" style={{ width: `${progress.percent}%` }} />
      </div>
      <div className="mt-3 grid gap-2 text-xs text-app-muted sm:grid-cols-2">
        <span>Created folders: {progress.createdFolders}/{progress.totalFolders}</span>
        <span>Moved files: {progress.movedFiles}/{progress.totalMoves}</span>
      </div>
      {progress.errors.length ? <CompactList title="Errors so far" items={progress.errors.map((error) => ({ label: error }))} tone="danger" /> : null}
    </div>
  );
}

function ExecutionResultCard({
  result,
  undoResult,
  undoing,
  onUndo,
}: {
  result: BrowserExecutionResult;
  undoResult: BrowserUndoResult | null;
  undoing: boolean;
  onUndo: () => void;
}) {
  const statusVariant = result.status === "completed" ? "success" : result.status === "partial" ? "warning" : "danger";
  return (
    <div className="rounded-lg border border-app-border bg-zinc-950 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium text-app-text">{result.status === "completed" ? "Completed" : result.status === "partial" ? "Partially completed" : "Failed"}</p>
        <Badge variant={statusVariant}>{result.status}</Badge>
      </div>
      <div className="mt-3 grid gap-2 text-xs text-app-muted sm:grid-cols-4">
        <span>Created folders: {result.createdFolders}</span>
        <span>Moved files: {result.movedFiles}</span>
        <span>Skipped: {result.skipped.length}</span>
        <span>Errors: {result.errors.length}</span>
      </div>
      {result.errors.length ? <CompactList title="Errors" items={result.errors.map((error) => ({ label: error }))} tone="danger" /> : null}
      {undoResult ? (
        <div className="mt-3 rounded-md border border-app-border bg-zinc-900/70 px-3 py-2 text-xs text-app-muted">
          Undo status: <span className="text-app-text">{undoResult.status}</span> - operations undone: {undoResult.undoneOperations}
          {undoResult.errors.length ? <CompactList title="Undo errors" items={undoResult.errors.map((error) => ({ label: error }))} tone="danger" /> : null}
        </div>
      ) : result.undoAvailable ? (
        <div className="mt-3 flex items-center justify-between gap-3 rounded-md border border-app-border bg-zinc-900/70 px-3 py-2">
          <span className="text-xs text-app-muted">Undo available for completed moves and created folders.</span>
          <Button type="button" variant="secondary" className="h-8 px-3" loading={undoing} onClick={onUndo}>
            Undo all
          </Button>
        </div>
      ) : null}
    </div>
  );
}

function RecentTasksCard({
  tasks,
  message,
  clearing,
  onClearHistory,
}: {
  tasks: RecentTaskItem[];
  message: string | null;
  clearing: boolean;
  onClearHistory: () => void;
}) {
  function taskBadge(task: RecentTaskItem) {
    if (task.type === "document_summary") return "Summary";
    if (task.type === "log_analysis_report") return "Log report";
    if (task.type === "gmail_sent") return "Email sent";
    if (task.type === "gmail_draft") return "Gmail draft";
    return "File task";
  }

  return (
    <Card className="mt-4 space-y-3 p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-app-text">Recent Tasks</p>
          <p className="mt-1 text-xs text-app-muted">Local task history only. Operational file tasks are not added to Memory.</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="default">{tasks.length}</Badge>
          {tasks.length ? (
            <Button type="button" variant="secondary" className="h-8 px-3 text-xs" loading={clearing} onClick={onClearHistory}>
              Clear history
            </Button>
          ) : null}
        </div>
      </div>
      {!tasks.length ? <p className="rounded-md border border-app-border bg-zinc-950 px-3 py-2 text-xs text-app-muted">{message || "No recent tasks yet."}</p> : null}
      <div className="space-y-2">
        {tasks.slice(0, 6).map((task) => (
          <div key={task.id} className="rounded-md border border-app-border bg-zinc-950 px-3 py-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-xs font-medium text-app-text">{task.title}</p>
                <p className="mt-1 text-xs text-app-muted">{task.summary}</p>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant={task.type === "document_summary" || task.type === "log_analysis_report" ? "success" : task.type === "gmail_draft" || task.type === "gmail_sent" ? "info" : "default"}>
                  {taskBadge(task)}
                </Badge>
                <Badge variant={task.status === "completed" ? "success" : task.status === "partial" ? "warning" : "danger"}>
                  {task.status}
                </Badge>
              </div>
            </div>
            <p className="mt-2 text-[11px] text-app-muted">
              {task.folderName || task.contextName || "Task"}
              {task.outputFileName ? ` · ${task.outputFileName}` : ""}
              {" · "}
              {formatTimestamp(task.createdAt)}
            </p>
          </div>
        ))}
      </div>
    </Card>
  );
}

function ClearTaskHistoryDialog({
  clearing,
  onCancel,
  onConfirm,
}: {
  clearing: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
      <div className="w-full max-w-md rounded-xl border border-app-border bg-zinc-950 p-5 shadow-xl shadow-black/40">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-app-text">Clear task history?</p>
            <p className="mt-2 text-sm leading-6 text-app-muted">
              This will remove local task history items from the Recent Tasks list. It will not delete Memory, Gmail drafts/emails,
              connector data, or files.
            </p>
          </div>
          <button type="button" className="rounded-md p-1 text-app-muted hover:bg-zinc-900 hover:text-app-text" onClick={onCancel} aria-label="Close">
            <X size={16} />
          </button>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onCancel} disabled={clearing}>
            Cancel
          </Button>
          <Button type="button" variant="danger" loading={clearing} onClick={onConfirm}>
            Clear task history
          </Button>
        </div>
      </div>
    </div>
  );
}

function OperationPreview({ plan }: { plan: FileTaskPlan }) {
  const [showAll, setShowAll] = useState(false);
  const visibleMoves = showAll ? plan.files_to_move : plan.files_to_move.slice(0, 8);
  const hiddenMoves = plan.files_to_move.length - visibleMoves.length;
  const visibleSkipped = showAll ? plan.skipped : plan.skipped.slice(0, 8);
  const hiddenSkipped = plan.skipped.length - visibleSkipped.length;

  return (
    <div className="mt-3 space-y-3">
      {plan.folders_to_create.length ? (
        <CompactList
          title="Folders to create"
          items={plan.folders_to_create.map((operation) => ({
            label: operation.relative_to ?? operation.path ?? "",
            detail: operation.reason,
          }))}
        />
      ) : null}

      {plan.files_to_move.length ? (
        <CompactList
          title="Files to move"
          items={visibleMoves.map((operation) => ({
            label: `${operation.relative_from ?? operation.from_path} -> ${operation.relative_to ?? operation.to_path}`,
            detail: operation.reason,
          }))}
        />
      ) : null}

      {plan.skipped.length ? (
        <CompactList
          title="Skipped"
          items={visibleSkipped.map((item) => ({
            label: item.relative_path ?? item.path,
            detail: item.reason,
          }))}
          tone="muted"
        />
      ) : null}

      {hiddenMoves > 0 || hiddenSkipped > 0 ? (
        <button type="button" onClick={() => setShowAll(true)} className="text-xs text-violet-300 hover:text-violet-200">
          + {hiddenMoves + hiddenSkipped} more
        </button>
      ) : showAll && (plan.files_to_move.length > 8 || plan.skipped.length > 8) ? (
        <button type="button" onClick={() => setShowAll(false)} className="text-xs text-violet-300 hover:text-violet-200">
          Show fewer
        </button>
      ) : null}
    </div>
  );
}

function isFallbackPlan(plan: FileTaskPlan) {
  const warning = plan.planner_warning?.toLowerCase() ?? "";
  return warning.includes("fallback") || warning.includes("unavailable") || warning.includes("invalid json");
}

function CompactList({
  title,
  items,
  tone = "default",
}: {
  title: string;
  items: Array<{ label: string; detail?: string }>;
  tone?: "default" | "warning" | "danger" | "muted";
}) {
  const toneClass =
    tone === "danger"
      ? "border-red-500/30 bg-red-500/10"
      : tone === "warning"
        ? "border-amber-500/30 bg-amber-500/10"
        : "border-app-border bg-zinc-900/70";
  return (
    <div className={`mt-3 rounded-md border px-3 py-2 ${toneClass}`}>
      <p className="text-xs font-medium text-app-text">{title}</p>
      <div className="mt-2 space-y-1">
        {items.map((item, index) => (
          <p key={`${item.label}:${index}`} className="text-xs text-app-muted">
            <span className="text-app-text">{item.label}</span>
            {item.detail ? <span> - {item.detail}</span> : null}
          </p>
        ))}
      </div>
    </div>
  );
}

function classifyTaskAction(instruction: string): ClassifiedTaskAction {
  const text = instruction.toLowerCase().trim();
  if (!text) {
    return { actionType: "file.organize", label: "Organize folder", supported: true };
  }
  if (/\b(delete|remove|erase|wipe|destroy)\b/.test(text)) {
    return {
      actionType: "unsupported",
      label: "Unsupported",
      supported: false,
      reason: "MindOS cannot safely prepare destructive tasks from the Tasks page.",
    };
  }
  if (isLogAnalysisInstruction(text)) {
    return { actionType: "log.analyzeFromSearch", label: "Analyze logs", supported: true };
  }
  if (/\b(summary|summarize|summarise|summarization|summarisation|report|recap)\b/.test(text) && /\b(file|files|document|documents|docs?|pdf|pdfs|docx|markdown|md|txt|text)\b/.test(text)) {
    return { actionType: /\breport\b/.test(text) ? "document.reportFromSearch" : "document.summaryFromSearch", label: /\breport\b/.test(text) ? "Report from connected files" : "Summary from connected files", supported: true };
  }
  if (/\b(search|find|look up|lookup)\b/.test(text) && /\b(file|files|document|documents|notes|pdf|pdfs|docx|markdown|md|txt|text)\b/.test(text)) {
    if (/\b(report)\b/.test(text)) {
      return { actionType: "document.reportFromSearch", label: "Report from connected files", supported: true };
    }
    if (/\b(summary|summarize|recap|send|email|mail|gmail)\b/.test(text) || extractEmailAddress(instruction)) {
      return {
        actionType: extractEmailAddress(instruction) || /\b(send|email|mail|gmail)\b/.test(text) ? "gmail.sendGeneratedReport" : "document.summaryFromSearch",
        label: extractEmailAddress(instruction) || /\b(send|email|mail|gmail)\b/.test(text) ? "Summary email from connected files" : "Summary from connected files",
        supported: true,
      };
    }
    return { actionType: "file.search", label: "Search connected files", supported: true };
  }
  if (/\b(gmail|email|mail|send|draft|compose|write)\b/.test(text) && /\b(find|search|attach|attachment|resume|cv|curriculum vitae|file|document|pdf)\b/.test(text)) {
    return { actionType: "multi_step", label: "Find file + Gmail", supported: true };
  }
  if (/\b(gmail|email|mail)\b/.test(text) && /\b(reply|respond)\b/.test(text)) {
    return { actionType: "gmail.replyDraft", label: "Create reply draft", supported: true };
  }
  if ((/\b(gmail|email|mail)\b/.test(text) || extractEmailAddress(instruction)) && /\b(send|sent)\b/.test(text)) {
    return { actionType: "gmail.sendEmail", label: "Send email", supported: true };
  }
  if ((/\b(gmail|email|mail)\b/.test(text) || extractEmailAddress(instruction)) && /\b(draft|write|compose|create)\b/.test(text)) {
    return { actionType: "gmail.createDraft", label: "Create Gmail draft", supported: true };
  }
  if (/\b(gmail|email|mail|emails|mails)\b/.test(text) && /\b(summarize|summary|recap)\b/.test(text)) {
    return { actionType: "gmail.summarizeEmails", label: "Summarize emails", supported: true };
  }
  if (/\b(gmail|email|mail|emails|mails)\b/.test(text) && /\b(search|find|look up|lookup|recent|unread)\b/.test(text)) {
    return { actionType: "gmail.searchEmails", label: "Search emails", supported: true };
  }
  if (/\b(github|pull request|pr|issue|commit|repo|repository)\b/.test(text)) {
    return { actionType: "github.lookup", label: "GitHub lookup", supported: true };
  }
  if (/\b(report|recap|summary of|summarize my|last 7 days|past week|weekly)\b/.test(text) && /\b(task|tasks|work|memory|activity)\b/.test(text)) {
    return { actionType: "memory.report", label: "Memory report", supported: true };
  }
  if (/\b(summarize|summary|read|notes|report)\b/.test(text) && /\b(document|documents|pdf|pdfs|docx|markdown|md|txt|text files?|files?)\b/.test(text)) {
    return { actionType: "document.summary", label: "Summarize documents", supported: true };
  }
  if (/\b(rename|renaming)\b/.test(text)) {
    return {
      actionType: "unsupported",
      label: "Rename files",
      supported: false,
      reason: "Rename execution is not connected yet. File organization and document summaries are available.",
    };
  }
  if (/\b(folder|file|files|downloads|documents|desktop|project|projects|pdf|pdfs|image|images|installer|installers|move|organize|sort|create folders?)\b/.test(text)) {
    return { actionType: "file.organize", label: "Organize folder", supported: true };
  }
  return {
    actionType: "unsupported",
    label: "Unsupported",
    supported: false,
    reason: "MindOS cannot safely prepare this task yet.",
  };
}

function isFolderTaskAction(actionType: TaskActionType) {
  return actionType === "file.organize" || actionType === "document.summary";
}

function isIndexedFileSearchAction(actionType: TaskActionType) {
  return actionType === "file.search" || actionType === "document.summaryFromSearch" || actionType === "document.reportFromSearch" || actionType === "gmail.sendGeneratedReport";
}

function isEmailWriteAction(actionType: TaskActionType) {
  return actionType === "gmail.createDraft" || actionType === "gmail.sendEmail" || actionType === "gmail.replyDraft";
}

function capabilityKeyForAction(actionType: TaskActionType) {
  if (actionType === "gmail.sendEmail") return "gmail.sendEmail";
  if (actionType === "gmail.replyDraft") return "gmail.replyDraft";
  if (actionType === "gmail.searchEmails") return "gmail.searchEmails";
  if (actionType === "gmail.summarizeEmails") return "gmail.summarizeEmails";
  return "gmail.createDraft";
}

function emailActionTitle(actionType: TaskActionType) {
  if (actionType === "gmail.sendEmail") return "Send email";
  if (actionType === "gmail.replyDraft") return "Create reply draft";
  return "Create Gmail draft";
}

function emailActionSummary(actionType: TaskActionType, subject: string) {
  if (actionType === "gmail.sendEmail") return `Send an email titled "${subject}" after confirmation.`;
  if (actionType === "gmail.replyDraft") return `Create a reply draft titled "${subject}". Nothing will be sent.`;
  return `Create a Gmail draft titled "${subject}". Nothing will be sent.`;
}

function getEmailActionDisabledReason({
  action,
  effectiveActionType,
  gmailConnected,
  sendAvailable,
  draftAvailable,
  draft,
}: {
  action: PreparedAction;
  effectiveActionType: TaskActionType;
  gmailConnected: boolean;
  sendAvailable: boolean;
  draftAvailable: boolean;
  draft: { to: string; subject: string; body: string; message_id: string };
}) {
  if (!gmailConnected) return "Gmail is not connected.";
  if (action.actionType === "gmail.sendEmail" && !sendAvailable && !draftAvailable) {
    return "Gmail draft and send actions are not connected yet.";
  }
  if (effectiveActionType === "gmail.sendEmail" && !sendAvailable) {
    return action.blockedReasons[0] || "Gmail send capability was not detected.";
  }
  if (effectiveActionType === "gmail.createDraft" && !draftAvailable) {
    return action.actionType === "gmail.sendEmail"
      ? "Gmail send is not connected yet. You can create a draft instead."
      : "Gmail draft creation is not connected yet.";
  }
  if (!draft.to.trim()) {
    return effectiveActionType === "gmail.sendEmail" ? "Add a recipient before sending." : "Add a recipient before creating the draft.";
  }
  if (!draft.subject.trim()) {
    return effectiveActionType === "gmail.sendEmail" ? "Add a subject before sending." : "Add a subject before creating the draft.";
  }
  if (!draft.body.trim()) {
    return effectiveActionType === "gmail.sendEmail" ? "Add an email body before sending." : "Add an email body before creating the draft.";
  }
  if (effectiveActionType === "gmail.replyDraft" && !draft.message_id.trim()) {
    return "Add the original message id before creating a reply draft.";
  }
  if (!action.canExecute) return action.blockedReasons[0] || "Preview the email and confirm before sending.";
  return "";
}

function splitRecipients(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function extractEmailAddress(value: string) {
  const match = value.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i);
  return match?.[0] ?? "";
}

function extractFileSearchQuery(value: string) {
  let text = value
    .replace(/\[[^\]]+\]\(mailto:[^)]+\)/gi, " ")
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, " ")
    .toLowerCase();
  text = text
    .replace(/\b(search|find|look up|lookup|files?|documents?|docs?|notes?|about|for|and|give|me|make|create|generate|summary|summarize|summarise|summarization|summarisation|report|send|email|mail|gmail|to|the|a|an|it|this|these|from|of|connected|folders?)\b/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return text || value.trim() || "selected files";
}

function shouldTryHybridPlanner(value: string) {
  const text = value.toLowerCase();
  if (!text.trim()) return false;
  if (/\b(organize|organise|move|sort|clean|rename|copy|summarize|summarise|summary|summarization|report|analy[sz]e|find|search|gmail|email|mail|send|draft|compose|write)\b/.test(text)) return true;
  const hasEmail = /\b(gmail|email|mail|send|draft|compose|write)\b/.test(text) || Boolean(extractEmailAddress(value));
  const hasFile = /\b(find|search|attach|attachment|resume|cv|curriculum vitae|file|files|document|documents|pdf|docx|txt|md|log|logs)\b/.test(text);
  const hasSummarySend = /\b(search|find)\b/.test(text) && /\b(summary|summarize|report)\b/.test(text) && hasEmail;
  return (hasEmail && hasFile) || hasSummarySend;
}

function isLogAnalysisInstruction(value: string) {
  const text = value.toLowerCase();
  const hasLog = /\b(log|logs|logfile|logfiles|app\.log|error log|debug log)\b/.test(text) || /\.(log|txt)\b/.test(text);
  const hasAnalysis = /\b(analy[sz]e|find|diagnose|investigate|report|errors?|exceptions?|failed|failure|traceback|stacktrace|timeout|crash)\b/.test(text);
  return hasLog && hasAnalysis;
}

function isFileSearchThenGmailPlan(plan: TaskIntentPrepareResponse) {
  if (plan.intent !== "multi_step") return false;
  const hasSearch = plan.steps.some((step) => step.type === "file.search_connected_folders");
  const hasDocumentSummary = plan.steps.some((step) => step.type === "document.summarize_selected_files" || step.type === "document.create_report_from_files" || step.type === "document.create_output_file");
  const hasGmail = plan.steps.some((step) => step.type === "gmail.create_draft" || step.type === "gmail.send_email_after_confirmation");
  return hasSearch && hasGmail && !hasDocumentSummary;
}

function isLogAnalysisPlan(plan: TaskIntentPrepareResponse) {
  return plan.primary_action === "log.analyzeFromSearch" || plan.steps.some((step) => step.type === "log.search_connected_logs" || step.type === "log.analyze_selected_files");
}

function isDocumentSearchSummaryPlan(plan: TaskIntentPrepareResponse) {
  return (
    plan.primary_action === "document.summaryFromSearch" ||
    plan.primary_action === "document.reportFromSearch" ||
    (plan.steps.some((step) => step.type === "file.search_connected_folders") &&
      plan.steps.some((step) => step.type === "document.summarize_selected_files" || step.type === "document.create_report_from_files"))
  );
}

function fileSearchQueryFromPlan(plan: TaskIntentPrepareResponse) {
  const fileSearchStep = plan.steps.find((step) => step.type === "file.search_connected_folders");
  return fileSearchStep?.query || plan.entities.file_queries[0] || plan.entities.topic_queries[0] || "selected files";
}

function logSearchQueryFromPlan(plan: TaskIntentPrepareResponse) {
  const fileSearchStep = plan.steps.find((step) => step.type === "log.search_connected_logs" || step.type === "file.search_connected_folders");
  return fileSearchStep?.query || plan.entities.topic_queries[0] || plan.entities.file_queries[0] || "error failure exception";
}

function logSearchExtensionsFromPlan(plan: TaskIntentPrepareResponse) {
  const stepExtensions = plan.steps.find((step) => step.type === "log.search_connected_logs" || step.type === "file.search_connected_folders")?.extensions ?? [];
  const extensions = [...stepExtensions, ...plan.entities.extensions].filter(Boolean);
  return extensions.length ? Array.from(new Set(extensions.map((extension) => (extension.startsWith(".") ? extension : `.${extension}`).toLowerCase()))) : [".log", ".txt", ".out", ".err"];
}

function logLatestPreferenceFromPlan(plan: TaskIntentPrepareResponse) {
  return Boolean(plan.entities.latest_preference || plan.steps.some((step) => step.latest_preference));
}

function logExactFileHintFromPlan(plan: TaskIntentPrepareResponse) {
  return plan.entities.exact_file_hint || plan.steps.find((step) => step.exact_file_hint)?.exact_file_hint || "";
}

function isLogLikeSearchMatch(match: IndexedFileSearchMatch) {
  const extension = (match.extension || "").toLowerCase();
  const haystack = `${match.file_name} ${match.relative_path} ${match.matched_excerpt || ""}`.toLowerCase();
  if (extension === ".log" || extension === ".out" || extension === ".err") return true;
  if (extension !== ".txt") return false;
  return /\b(log|error|app|server|backend|frontend|api|debug|trace|exception|stacktrace|traceback|failed|failure|timeout|refused|500|nullpointerexception|sqlexception)\b/.test(haystack);
}

function actionFromUnsupportedPlan(plan: TaskIntentPrepareResponse): PreparedAction {
  return {
    id: `action-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    actionType: "unsupported",
    label: "Choose action",
    supported: false,
    title: "Choose what MindOS should do",
    summary: plan.user_facing_summary || plan.explanation || "MindOS needs one more hint before preparing this task.",
    riskLevel: "low",
    requiresConfirmation: false,
    canExecute: false,
    blockedReasons: plan.validation_repairs.length ? plan.validation_repairs : ["Planner confidence was too low."],
    missingRequirements: [],
    sources: [],
    preview: {
      note: "Possible actions: search files and summarize them, analyze log files, organize a folder, or draft/send Gmail.",
      warning: [...plan.warnings, ...plan.validation_repairs].join(" "),
    },
  };
}

function exactLogFileHint(value: string) {
  const match = value.match(/(?:^|\s)([\w .()_-]+\.(?:log|txt))\b/i);
  return match?.[1]?.trim() ?? "";
}

function extractLogAnalysisQuery(value: string) {
  const exact = exactLogFileHint(value);
  if (exact) return exact;
  let text = value.toLowerCase();
  text = text
    .replace(/\b(find|analyze|analyse|diagnose|investigate|create|make|generate|report|errors?|exceptions?|latest|recent|newest|last|logs?|logfiles?|log files?|files?|about|for|in|the|a|an|and|from|connected|folders?)\b/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return text || "error failure exception";
}

function gmailStepFromPlan(plan: TaskIntentPrepareResponse) {
  return plan.steps.find((step) => step.type === "gmail.create_draft" || step.type === "gmail.send_email_after_confirmation") ?? null;
}

function buildAttachmentEmailDraft(plan: TaskIntentPrepareResponse, filenames: string[]) {
  const emailStep = gmailStepFromPlan(plan);
  const firstFile = filenames[0] || "the selected file";
  const subject = emailStep?.subject_hint || (fileSearchQueryFromPlan(plan).includes("resume") ? "Resume for your review" : "Requested file");
  const attachmentLine = filenames.length === 1 ? `I have attached ${firstFile} for your review.` : `I have attached ${filenames.length} selected files for your review.`;
  return {
    subject,
    body: `Hi,\n\n${attachmentLine}\n\nBest regards,`,
  };
}

function frontendMultiStepFallbackPlan(instruction: string): TaskIntentPrepareResponse {
  const lower = instruction.toLowerCase();
  const wantsDraft = /\b(draft|compose|write|create a draft)\b/.test(lower);
  const wantsSend = /\b(send|email|mail)\b/.test(lower) && !wantsDraft;
  const query = /\b(resume|cv|curriculum vitae)\b/.test(lower) ? "resume cv curriculum vitae" : extractFileSearchQuery(instruction);
  const recipient = extractEmailAddress(instruction);
  return {
    intent: "multi_step",
    primary_action: wantsSend ? "gmail.sendEmail" : "gmail.createDraft",
    risk_level: wantsSend ? "high" : "medium",
    requires_user_selection: true,
    requires_confirmation: true,
    confidence: 0.78,
    source_type: "connected_files",
    needs_file_search: true,
    needs_user_file_selection: true,
    needs_output_file: false,
    entities: {
      recipients: recipient ? [recipient] : [],
      file_queries: [query],
      topic_queries: [],
      explicit_file_names: [],
      action_words: [],
      connector_words: [],
      attachment_words: [],
      output_words: [],
      risk_words: wantsSend ? ["send"] : [],
      date_range: null,
      output_format: null,
      extensions: [],
      latest_preference: false,
      exact_file_hint: null,
      possible_intents: [wantsSend ? "gmail.sendEmail" : "gmail.createDraft"],
    },
    steps: [
      {
        id: "step_1",
        type: "file.search_connected_folders",
        query,
        purpose: `Find ${query} attachment candidates`,
        requires_user_selection: true,
        requires_confirmation: false,
        to: [],
        subject_hint: null,
        body_hint: null,
        attachments_from_step: null,
        files_from_step: null,
        extensions: [],
        latest_preference: false,
        exact_file_hint: null,
        output_format: null,
        filename_hint: null,
      },
      {
        id: "step_2",
        type: wantsSend ? "gmail.send_email_after_confirmation" : "gmail.create_draft",
        query: null,
        purpose: wantsSend ? "Send Gmail after confirmation" : "Create Gmail draft",
        requires_user_selection: false,
        requires_confirmation: true,
        to: recipient ? [recipient] : [],
        subject_hint: query.includes("resume") ? "Resume for your review" : "Requested file",
        body_hint: "Brief professional email with the selected attachment.",
        attachments_from_step: "step_1",
        files_from_step: null,
        extensions: [],
        latest_preference: false,
        exact_file_hint: null,
        output_format: null,
        filename_hint: null,
      },
    ],
    explanation: wantsSend
      ? `Search connected folders for ${query}, ask you to choose the file, then prepare Gmail send for confirmation.`
      : `Search connected folders for ${query}, ask you to choose the file, then create a Gmail draft.`,
    user_facing_summary: wantsSend
      ? `Search connected folders for ${query}, ask you to choose the file, then prepare Gmail send for confirmation.`
      : `Search connected folders for ${query}, ask you to choose the file, then create a Gmail draft.`,
    planner_method: "fallback",
    warnings: ["Using deterministic multi-step fallback."],
    validation_repairs: [],
  };
}

function frontendLogAnalysisFallbackPlan(instruction: string): TaskIntentPrepareResponse {
  const query = extractLogAnalysisQuery(instruction);
  const exactFileHint = exactLogFileHint(instruction);
  const latestPreference = /\b(latest|recent|newest|last)\b/i.test(instruction);
  const filenameHint = `${query || "log-error-analysis"}-report.md`;
  return {
    intent: "multi_step",
    primary_action: "log.analyzeFromSearch",
    risk_level: "medium",
    requires_user_selection: true,
    requires_confirmation: true,
    confidence: 0.78,
    source_type: "connected_logs",
    needs_file_search: true,
    needs_user_file_selection: true,
    needs_output_file: true,
    entities: {
      recipients: [],
      file_queries: [query],
      topic_queries: [query],
      explicit_file_names: exactFileHint ? [exactFileHint] : [],
      action_words: ["analyze"],
      connector_words: ["logs"],
      attachment_words: [],
      output_words: ["report"],
      risk_words: [],
      date_range: null,
      output_format: "markdown",
      extensions: [".log", ".txt", ".out", ".err"],
      latest_preference: latestPreference,
      exact_file_hint: exactFileHint || null,
      possible_intents: ["log.analyzeFromSearch"],
    },
    steps: [
      {
        id: "step_1",
        type: "log.search_connected_logs",
        query,
        purpose: "Find relevant connected log files",
        requires_user_selection: true,
        requires_confirmation: false,
        to: [],
        subject_hint: null,
        body_hint: null,
        attachments_from_step: null,
        files_from_step: null,
        extensions: [".log", ".txt", ".out", ".err"],
        latest_preference: latestPreference,
        exact_file_hint: exactFileHint || null,
        output_format: null,
        filename_hint: null,
      },
      {
        id: "step_2",
        type: "log.analyze_selected_files",
        query,
        purpose: "Create a safe log analysis report from selected files",
        requires_user_selection: false,
        requires_confirmation: true,
        to: [],
        subject_hint: null,
        body_hint: null,
        attachments_from_step: null,
        files_from_step: "step_1",
        extensions: [],
        latest_preference: false,
        exact_file_hint: null,
        output_format: "markdown",
        filename_hint: filenameHint,
      },
      {
        id: "step_3",
        type: "document.create_output_file",
        query: null,
        purpose: "Save report to MindOS outputs after preview",
        requires_user_selection: false,
        requires_confirmation: true,
        to: [],
        subject_hint: null,
        body_hint: null,
        attachments_from_step: null,
        files_from_step: "step_2",
        extensions: [],
        latest_preference: false,
        exact_file_hint: null,
        output_format: "markdown",
        filename_hint: filenameHint,
      },
    ],
    explanation: `Search connected folders for ${query}, let you choose log files, then create a redacted analysis report.`,
    user_facing_summary: `Search connected folders for log files related to "${query}", then create a redacted analysis report.`,
    planner_method: "fallback",
    warnings: ["Using deterministic log-analysis fallback."],
    validation_repairs: [],
  };
}

function summarizeEmailMessages(messages: NormalizedEmailMessage[]) {
  if (!messages.length) return "No matching emails found.";
  const senders = [...new Set(messages.map((message) => message.from).filter(Boolean))].slice(0, 4);
  const subjects = messages.slice(0, 4).map((message) => message.subject || "(no subject)");
  return [
    `Found ${messages.length} email${messages.length === 1 ? "" : "s"}${senders.length ? ` from ${senders.join(", ")}` : ""}.`,
    `Key subjects: ${subjects.join("; ")}.`,
    "No messages were modified.",
  ].join(" ");
}

function recentTasksFromLastDays(tasks: RecentTaskItem[], days: number) {
  const cutoff = Date.now() - days * 24 * 60 * 60 * 1000;
  return tasks.filter((task) => {
    const created = new Date(task.createdAt).getTime();
    return Number.isFinite(created) && created >= cutoff;
  });
}

function buildGmailDraftPreview(instruction: string, history: RecentTaskItem[]) {
  const grouped = groupRecentTasksForEmail(history);
  const taskText = grouped || "I do not have enough recent task history available here to list specific completed items.";
  return {
    to: "",
    subject: "Summary of my last 7 days of tasks",
    body: `Hi,\n\nHere is a short summary of my work from the last 7 days:\n\n${taskText}\n\nPlease let me know if you need more details.\n\nBest regards,`,
  };
}

function toGmailDraftSourceItem(task: RecentTaskItem) {
  return {
    type: task.type,
    title: task.title,
    summary: task.summary,
    status: task.status,
    created_at: task.createdAt,
    context_name: task.folderName || task.contextName || null,
    output_file_name: task.outputFileName || null,
    details: task.details,
  };
}

function groupRecentTasksForEmail(history: RecentTaskItem[]) {
  if (!history.length) return "";
  const documentSummaries = history.filter((task) => task.type === "document_summary");
  const logReports = history.filter((task) => task.type === "log_analysis_report");
  const fileTasks = history.filter((task) => task.type === "file_organize");
  const gmailDrafts = history.filter((task) => task.type === "gmail_draft");
  const gmailSent = history.filter((task) => task.type === "gmail_sent");
  const lines: string[] = [];
  if (documentSummaries.length) {
    const saved = documentSummaries.map((task) => task.outputFileName).filter(Boolean);
    lines.push(`Document summaries: I created ${documentSummaries.length} summary document${documentSummaries.length === 1 ? "" : "s"}.`);
    if (saved.length) lines.push(`Saved files included ${saved.slice(0, 5).join(", ")}.`);
  }
  if (fileTasks.length) {
    const moved = fileTasks.reduce((sum, task) => sum + Number(task.details.moved_files || 0), 0);
    lines.push(`File organization: I organized ${fileTasks.length} folder task${fileTasks.length === 1 ? "" : "s"}${moved ? ` and moved ${moved} files` : ""}.`);
  }
  if (logReports.length) {
    const saved = logReports.map((task) => task.outputFileName).filter(Boolean);
    lines.push(`Log analysis: I created ${logReports.length} log analysis report${logReports.length === 1 ? "" : "s"}.`);
    if (saved.length) lines.push(`Saved reports included ${saved.slice(0, 5).join(", ")}.`);
  }
  if (gmailDrafts.length) {
    lines.push(`Email workflow: I created ${gmailDrafts.length} Gmail draft${gmailDrafts.length === 1 ? "" : "s"} for review.`);
  }
  if (gmailSent.length) {
    lines.push(`Email workflow: I sent ${gmailSent.length} email${gmailSent.length === 1 ? "" : "s"} after confirmation.`);
  }
  const other = history.filter((task) => !["document_summary", "log_analysis_report", "file_organize", "gmail_draft", "gmail_sent"].includes(task.type));
  for (const task of other.slice(0, 4)) {
    lines.push(`${task.title}: ${task.summary}`);
  }
  return lines.join("\n");
}

function actionSourcesFor(actionType: TaskActionType, recentTasks: RecentTaskItem[]): PreparedAction["sources"] {
  if (actionType === "gmail.searchEmails" || actionType === "gmail.summarizeEmails") {
    return [{ type: "email", status: "available" }];
  }
  if (actionType === "github.lookup") {
    return [{ type: "github", status: "available" }];
  }
  if (actionType === "memory.report") {
    return [
      { type: "memory", status: "available" },
      { type: "task_history", status: recentTasksFromLastDays(recentTasks, 7).length ? "available" : "missing" },
    ];
  }
  return [];
}

function previewNoteFor(actionType: TaskActionType) {
  if (actionType === "gmail.searchEmails") return "Email search is read-only. No messages will be sent or modified.";
  if (actionType === "gmail.summarizeEmails") return "Email summarization is read-only. No messages will be sent or modified.";
  if (actionType === "github.lookup") return "GitHub lookup uses read-only synced repository context. No GitHub write actions are available here.";
  if (actionType === "memory.report") return "MindOS can prepare a report from task history and Memory without asking for a folder.";
  return "MindOS will prepare a safe preview first.";
}

function safetyBulletsForAction(action: PreparedAction) {
  if (action.actionType === "gmail.createDraft") {
    return ["This creates a draft only.", "MindOS will not send the email.", "Draft bodies are stored in Task History only as lightweight metadata."];
  }
  if (action.actionType === "gmail.sendEmail") {
    return ["This will send the email after confirmation.", "MindOS will not delete, archive, or mark any email.", "The sent body is not stored in Memory."];
  }
  if (action.actionType === "gmail.replyDraft") {
    return ["This creates a reply draft only.", "MindOS will not send the reply.", "The reply body is not stored in Memory."];
  }
  if (action.actionType === "gmail.searchEmails" || action.actionType === "gmail.summarizeEmails") {
    return ["This is read-only.", "No emails will be modified."];
  }
  if (action.actionType === "github.lookup") {
    return ["This uses read-only GitHub context.", "No issues, pull requests, comments, or repository changes will be created."];
  }
  return ["MindOS validates the preview before execution.", "No unsupported tool call will run."];
}

function loadRecentTasks(): RecentTaskItem[] {
  try {
    return loadRecentTaskHistory<RecentTaskItem>()
      .filter((item): item is RecentTaskItem => {
        return (
          item &&
          typeof item.id === "string" &&
          (item.type === "file_organize" || item.type === "document_summary" || item.type === "log_analysis_report" || item.type === "gmail_draft" || item.type === "gmail_sent") &&
          typeof item.title === "string" &&
          typeof item.summary === "string" &&
          typeof item.createdAt === "string"
        );
      })
      .slice(0, 20);
  } catch {
    return [];
  }
}

function formatTimestamp(value: string) {
  return new Date(value).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

async function getSelectedChatModel(): Promise<ModelConfig | null> {
  try {
    const settings = await getModelSettings();
    return settings.models.find((model) => model.id === settings.selected_chat_model) ?? null;
  } catch {
    return null;
  }
}

function buildCategorySummary(files: FileSnapshotItem[]): CategorySummary[] {
  const counts: Record<string, number> = {};
  for (const file of files) {
    const category = categoryForExtension(file.extension);
    counts[category] = (counts[category] ?? 0) + 1;
  }
  return Object.entries(counts)
    .map(([label, count]) => ({ label, count }))
    .sort((a, b) => b.count - a.count);
}

function categoryForExtension(extension: string) {
  const normalized = extension.toLowerCase();
  for (const category of extensionCategories) {
    if (category.extensions.includes(normalized)) return category.label;
  }
  return "Other";
}

function formatBytes(size: number) {
  if (size < 1024) return `${size} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = size / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[unitIndex]}`;
}

function formatShortDate(value: string) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function attachmentSourceLabel(source: AttachmentCandidate["source"]) {
  if (source === "manual_picker") return "Manual";
  if (source === "recent_task_output") return "Recent task";
  if (source === "selected_folder_scan") return "Selected folder";
  return "Connected folder";
}

function rankAttachmentCandidates(candidates: AttachmentCandidate[], latestPreference: boolean) {
  const byKey = new Map<string, AttachmentCandidate>();
  for (const candidate of candidates) {
    const key = `${candidate.source}:${candidate.source_id || ""}:${candidate.relative_path || candidate.name}:${candidate.size_bytes}`;
    const existing = byKey.get(key);
    if (!existing || candidate.score > existing.score || (!existing.source_id && candidate.source_id)) {
      byKey.set(key, candidate);
    }
  }
  const ranked = [...byKey.values()].sort((a, b) => {
    if (latestPreference) {
      const timeDiff = timestampForSort(b.modified_at) - timestampForSort(a.modified_at);
      if (timeDiff) return timeDiff;
    }
    return b.score - a.score;
  });
  const visible = ranked.slice(0, 12).map((candidate) => ({ ...candidate, selected: false }));
  const top = visible[0];
  const runnerUp = visible[1];
  if (top && isAttachmentCandidateSelectable(top) && top.score >= 28 && (!runnerUp || top.score - runnerUp.score >= 4)) {
    top.selected = true;
  }
  return visible;
}

function isAttachmentCandidateSelectable(candidate: AttachmentCandidate) {
  if (candidate.unavailableReason) return false;
  if (candidate.file) return true;
  return isIndexedAttachmentCandidate(candidate);
}

function readableMatchReason(reason: string) {
  const normalized = reason.toLowerCase();
  if (normalized.includes("filename")) return "Filename matched.";
  if (normalized.includes("content")) return "Content matched.";
  return reason ? `${reason}.` : "";
}

function timestampForSort(value?: string) {
  if (!value) return 0;
  const parsed = new Date(value).getTime();
  return Number.isFinite(parsed) ? parsed : 0;
}

function ensureAttachmentMention<T extends { body: string }>(draft: T, attachmentNames: string[]): T {
  const names = attachmentNames.filter(Boolean);
  if (!names.length || /\b(attached|attachment|included)\b/i.test(draft.body)) return draft;
  const sentence = names.length === 1 ? `I have attached ${names[0]} for your review.` : `I have attached ${names.length} files for your review.`;
  const parts = draft.body.trimEnd().split("\n\n");
  const body =
    parts.length >= 2 && /^best\b/i.test(parts[parts.length - 1].trim())
      ? [...parts.slice(0, -1), sentence, parts[parts.length - 1]].join("\n\n")
      : `${draft.body.trimEnd()}\n\n${sentence}`;
  return { ...draft, body };
}

function normalizedSummaryFilename(filename: string, format: "markdown" | "text") {
  const extension = format === "text" ? ".txt" : ".md";
  const trimmed = filename.trim() || `mindos-summary${extension}`;
  const withoutKnownExtension = trimmed.replace(/\.(md|txt)$/i, "");
  return `${withoutKnownExtension}${extension}`;
}

function uniqueFileTypes(readResult: BrowserDocumentReadResult | null) {
  if (!readResult) return [];
  return [...new Set(readResult.files_read.map((file) => file.file_type || extensionToFileType(file.extension)))].sort();
}

function fileTypesFromPaths(paths: string[]) {
  return Array.from(
    new Set(
      paths
        .map((path) => {
          const match = path.toLowerCase().match(/\.[a-z0-9]+$/);
          return match ? match[0].replace(".", "") : "";
        })
        .filter(Boolean),
    ),
  );
}

function extensionToFileType(extension: string) {
  const normalized = extension.toLowerCase();
  if (normalized === ".pdf") return "pdf";
  if (normalized === ".docx") return "docx";
  return normalized.replace(/^\./, "") || "text";
}

function buildBrowserFileTaskPlan(scan: BrowserFolderScanResult, instruction: string, warning?: string): FileTaskPlan {
  const includeOther = shouldIncludeOther(instruction);
  const existingFolders = new Set(scan.folders.map((folder) => normalizeRelative(folder.relative_path)));
  const existingFiles = new Set(scan.files.map((file) => normalizeRelative(file.relative_path)));
  const categoryCounts: Record<string, number> = {};
  const skipped: FileTaskPlan["skipped"] = [];
  const destinationFolders = new Set<string>();
  const filesToMove: FileOperation[] = [];

  for (const file of scan.files) {
    const category = categoryForExtension(file.extension);
    if (category === "Other" && !includeOther) {
      skipped.push({ path: file.path, relative_path: file.relative_path, reason: "Unknown file type." });
      continue;
    }

    categoryCounts[category] = (categoryCounts[category] ?? 0) + 1;
    const sourcePath = normalizeRelative(file.relative_path);
    const destinationPath = normalizeRelative(`${category}/${file.name}`);

    if (sourcePath === destinationPath || normalizeRelative(parentPath(sourcePath)) === category) {
      skipped.push({ path: file.path, relative_path: file.relative_path, reason: "Already organized." });
      continue;
    }
    if (existingFiles.has(destinationPath)) {
      skipped.push({ path: file.path, relative_path: file.relative_path, reason: "Destination already exists. No overwrite allowed." });
      continue;
    }

    destinationFolders.add(category);
    filesToMove.push({
      id: "",
      type: "move_file",
      tool: "file.move_file",
      from_path: null,
      to_path: null,
      path: null,
      relative_from: file.relative_path,
      relative_to: destinationPath,
      reason: `${categorySingular(category)} file should be grouped under ${category}.`,
      status: "planned",
    });
  }

  const foldersToCreate: FileOperation[] = [...destinationFolders]
    .sort()
    .filter((folder) => !existingFolders.has(folder))
    .map((folder) => ({
      id: "",
      type: "create_folder",
      tool: "file.create_folder",
      from_path: null,
      to_path: null,
      path: null,
      relative_from: null,
      relative_to: folder,
      reason: `Create ${folder} folder for organized files.`,
      status: "planned",
    }));

  const operations = assignOperationIds([...foldersToCreate, ...filesToMove]);
  const foldersWithIds = operations.filter((operation) => operation.type === "create_folder");
  const movesWithIds = operations.filter((operation) => operation.type === "move_file");
  const categories = Object.keys(categoryCounts).sort();
  const summary = movesWithIds.length
    ? `Organize ${movesWithIds.length} files into ${categories.length} folders by file type: ${categories.slice(0, 5).join(", ")}${categories.length > 5 ? `, and ${categories.length - 5} more` : ""}.`
    : "No file moves are needed for this folder.";

  return {
    task_id: `browser-preview-${Date.now()}`,
    task_type: "file_organize",
    root_path: scan.display_name,
    instruction,
    summary,
    risk_level: operations.length <= 100 ? "low" : "medium",
    requires_confirmation: true,
    operations,
    folders_to_create: foldersWithIds,
    files_to_move: movesWithIds,
    skipped,
    warnings: scan.warnings,
    blocked_reasons: [],
    status: operations.length ? "awaiting_confirmation" : "empty",
    total_operations: operations.length,
    create_folder_count: foldersWithIds.length,
    move_file_count: movesWithIds.length,
    copy_file_count: 0,
    rename_file_count: 0,
    category_counts: categoryCounts,
    preview_only: true,
    planner_model: null,
    planner_provider: null,
    planner_warning: warning ?? null,
  };
}

function assignOperationIds(operations: FileOperation[]) {
  return operations.map((operation, index) => ({ ...operation, id: `op_${String(index + 1).padStart(3, "0")}` }));
}

function normalizeRelative(path: string) {
  return path.replace(/\\/g, "/").replace(/^\/+/, "").replace(/\/+$/, "");
}

function parentPath(path: string) {
  const normalized = normalizeRelative(path);
  const index = normalized.lastIndexOf("/");
  return index === -1 ? "" : normalized.slice(0, index);
}

function shouldIncludeOther(instruction: string) {
  const text = instruction.toLowerCase();
  return text.includes("unknown") || text.includes("others") || text.includes("other files");
}

function categorySingular(category: string) {
  if (category === "PDFs") return "PDF";
  return category.endsWith("s") ? category.slice(0, -1) : category;
}

function toTaskErrorMessage(error: unknown) {
  const message = getErrorMessage(error);
  const lower = message.toLowerCase();
  if (lower.includes("does not exist")) return "Folder not found. Check the path and try again.";
  if (lower.includes("protected") || lower.includes("system") || lower.includes("drive roots")) return "MindOS cannot scan protected system folders.";
  if (lower.includes("directory")) return "That path is not a folder.";
  return message;
}

function inferredPathFromCommand(command: string) {
  const normalized = command.toLowerCase();
  if (normalized.includes("download")) return "D:\\Downloads";
  if (normalized.includes("document")) return "D:\\Documents";
  if (normalized.includes("desktop")) return "D:\\Desktop";
  if (normalized.includes("project")) return "D:\\Projects";
  return "";
}

function extractPathLikeCommand(command: string) {
  const trimmed = command.trim();
  if (/^[a-zA-Z]:[\\/]/.test(trimmed)) return trimmed;
  return "";
}
